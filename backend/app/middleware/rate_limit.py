from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

import structlog
from redis import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.errors import error_body
from app.core.config import settings
from app.core.request_context import get_request_id

logger = structlog.get_logger("app.rate_limit")

_KEY_PREFIX = "ratelimit"

# Atomic sliding-window log: evict entries older than the window, count what
# remains, and admit the request only if under the limit. Runs entirely in
# Redis so the limit is enforced consistently across every API replica.
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry = 0
  if oldest[2] then
    retry = (tonumber(oldest[2]) + window) - now
  end
  return {0, count, retry}
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window)
return {1, count + 1, 0}
"""


@dataclass(frozen=True)
class _RateRule:
    name: str
    method: str
    path: str
    message: str
    enabled: Callable[[], bool]
    limit: Callable[[], int]
    window: Callable[[], int]


# Settings are read lazily via callables so tests that mutate `settings` at
# runtime (and env overrides) take effect without re-importing this module.
_RULES: tuple[_RateRule, ...] = (
    _RateRule(
        name="upload",
        method="POST",
        path="/api/v1/invoices/upload",
        message="Too many invoice upload attempts. Try again later.",
        enabled=lambda: settings.upload_rate_limit_enabled,
        limit=lambda: settings.upload_rate_limit_requests,
        window=lambda: settings.upload_rate_limit_window_seconds,
    ),
    _RateRule(
        name="login",
        method="POST",
        path="/api/v1/auth/login",
        message="Too many login attempts. Try again later.",
        enabled=lambda: settings.login_rate_limit_enabled,
        limit=lambda: settings.login_rate_limit_requests,
        window=lambda: settings.login_rate_limit_window_seconds,
    ),
)

_redis_client: Redis | None = None
_sliding_window_script = None


def _get_script():
    global _redis_client, _sliding_window_script
    if _sliding_window_script is None:
        _redis_client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _sliding_window_script = _redis_client.register_script(_SLIDING_WINDOW_LUA)
    return _sliding_window_script


class UploadRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rule = _match_rule(request)
        if rule is None:
            return await call_next(request)

        allowed, retry_after = _check_rule(rule, request)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content=error_body(
                    code="rate_limit_exceeded",
                    message=rule.message,
                    details={
                        "limit": rule.limit(),
                        "window_seconds": rule.window(),
                    },
                    request_id=get_request_id(),
                ),
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)


def _check_rule(rule: _RateRule, request: Request) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds). Fails open (allows the request)
    if Redis is unavailable so a cache outage cannot take down the API."""
    window_seconds = rule.window()
    now_ms = int(time.time() * 1000)
    key = _rate_limit_key(rule, request)
    try:
        script = _get_script()
        allowed, _count, retry_ms = script(
            keys=[key],
            args=[now_ms, window_seconds * 1000, rule.limit(), f"{now_ms}-{uuid4().hex}"],
        )
    except RedisError as exc:
        logger.warning("rate_limit.redis_unavailable", rule=rule.name, error=str(exc))
        return True, 0
    if int(allowed) == 1:
        return True, 0
    retry_after = max(1, math.ceil(int(retry_ms) / 1000))
    return False, retry_after


def reset_rate_limits() -> None:
    """Clear all recorded rate-limit windows (used by tests)."""
    try:
        _get_script()
        keys = list(_redis_client.scan_iter(match=f"{_KEY_PREFIX}:*"))
        if keys:
            _redis_client.delete(*keys)
    except RedisError as exc:
        logger.warning("rate_limit.reset_failed", error=str(exc))


# Backwards-compatible alias.
reset_upload_rate_limits = reset_rate_limits


def _match_rule(request: Request) -> _RateRule | None:
    for rule in _RULES:
        if rule.enabled() and request.method == rule.method and request.url.path == rule.path:
            return rule
    return None


def _rate_limit_key(rule: _RateRule, request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    client_id = forwarded_for or host
    return f"{_KEY_PREFIX}:{rule.name}:{client_id}:{request.url.path}"
