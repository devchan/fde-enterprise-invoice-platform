"""Realtime signal-not-payload events, published over Redis pub/sub so the
frontend can invalidate its react-query cache instead of polling.

Each event is deliberately minimal (type + ids, no full serialized records):
the frontend refetches the authoritative REST endpoint on receipt, which
avoids duplicating serialization logic here and any staleness/ordering races
from pushing full objects over the wire.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = structlog.get_logger("app.events")

_CHANNEL_PREFIX = "org"

_redis_client: Redis | None = None


def _get_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis_client


def organization_channel(organization_id: UUID) -> str:
    return f"{_CHANNEL_PREFIX}:{organization_id}:events"


def publish_event(organization_id: UUID, event: dict[str, Any]) -> None:
    """Publish a realtime event to every subscriber for `organization_id`.

    Failure to publish never raises: a live-update signal is a UX nicety, not
    part of the business transaction it's called from (review, reprocess,
    extraction) — the caller's `db.commit()` has already succeeded by the
    time this runs.
    """
    payload = {"occurred_at": datetime.now(UTC).isoformat(), **event}
    try:
        _get_client().publish(organization_channel(organization_id), json.dumps(payload))
    except RedisError as exc:
        logger.warning("events.publish_failed", event_type=event.get("type"), error=str(exc))
