import time
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.metrics import record_http_request
from app.core.request_context import reset_request_id, set_request_id

logger = structlog.get_logger("app.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = _request_id_from_header(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started_at = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_seconds = time.perf_counter() - started_at
            duration_ms = round(duration_seconds * 1000, 2)
            # Use the matched route template (e.g. /api/v1/invoices/{invoice_id})
            # rather than the raw path so metric label cardinality stays bounded.
            metric_path = _metric_path(request)
            record_http_request(
                method=request.method,
                path=metric_path,
                status_code=status_code,
                duration_seconds=duration_seconds,
            )
            logger.info(
                "request.completed",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            reset_request_id(token)


def _request_id_from_header(value: str | None) -> str:
    normalized = (value or "").strip()
    return normalized or str(uuid4())


def _metric_path(request: Request) -> str:
    """Return the matched route template so URLs with embedded ids collapse to
    a single low-cardinality label. Falls back to the raw path when no route
    matched (e.g. 404s)."""
    route = request.scope.get("route")
    return getattr(route, "path_format", None) or request.url.path
