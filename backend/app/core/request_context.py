"""Per-request id storage.

Uses a ContextVar rather than a global so the id is isolated per request/task
(including under async and threads) and cannot bleed across concurrent
requests. Set by middleware, read by logging and error responses."""

from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(request_id: str):
    return _request_id.set(request_id)


# Restore the previous value using the token returned by set_request_id, so
# nested/overlapping scopes unwind cleanly instead of leaking the last id.
def reset_request_id(token) -> None:
    _request_id.reset(token)
