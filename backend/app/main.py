"""FastAPI application factory: wires middleware, exception handlers, routes,
and tracing into a single app instance for both the API server and tests."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis as AsyncRedis
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import http_exception_handler, unhandled_exception_handler, validation_exception_handler
from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.tracing import configure_tracing
from app.middleware.rate_limit import UploadRateLimitMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One shared async connection pool for the SSE endpoint's pub/sub subscriptions,
    # opened once at startup rather than per-connection.
    app.state.redis = AsyncRedis.from_url(settings.redis_url)
    try:
        yield
    finally:
        await app.state.redis.aclose()


def create_app() -> FastAPI:
    # Configure structured logging before anything emits logs during startup.
    configure_logging()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Enterprise AI invoice processing platform.",
        lifespan=lifespan,
    )
    # Starlette runs middleware in reverse registration order, so the last one
    # added is outermost. Registering request logging after the rate limiter
    # makes logging the outer layer: every request (including rejected ones) is
    # logged with its request-id context before the rate limiter inspects it.
    app.add_middleware(UploadRateLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    # Normalize all error responses into the platform's `{"error": {...}}` shape:
    # HTTP errors, request-validation (422) failures, and unhandled exceptions.
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(api_router)
    # Instrument the fully assembled app so tracing wraps all routes/middleware.
    configure_tracing(app)
    return app


app = create_app()
