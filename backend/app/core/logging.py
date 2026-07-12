"""Structured (JSON) logging setup via structlog, called once at startup."""

import logging
import sys

import structlog

from app.core.request_context import get_request_id


def configure_logging() -> None:
    # force=True replaces any handlers a library/pytest already installed so our
    # JSON-to-stdout configuration wins regardless of import order.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
        force=True,
    )
    structlog.configure(
        processors=[
            # Order matters: enrich with request_id first, then stamp time and
            # level, then render the final event dict as a single JSON line.
            _add_request_id,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


# structlog processor: attach the current request's id to every log line so
# logs can be correlated per request (omitted when there is no active request).
def _add_request_id(_, __, event_dict: dict) -> dict:
    request_id = get_request_id()
    if request_id is not None:
        event_dict["request_id"] = request_id
    return event_dict
