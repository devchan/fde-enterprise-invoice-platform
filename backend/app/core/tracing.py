from __future__ import annotations

import structlog
from fastapi import FastAPI

from app.core.config import settings

logger = structlog.get_logger("app.tracing")

_instrumented = False


def configure_tracing(app: FastAPI) -> None:
    """Wire OpenTelemetry distributed tracing for FastAPI, SQLAlchemy, and Redis.

    Tracing is opt-in (OTEL_ENABLED). When enabled, spans are exported over OTLP
    if an endpoint is configured, and/or to the console for local debugging. Kept
    fully optional so the default deployment and the test suite are unaffected.
    """
    global _instrumented
    if not settings.otel_enabled or _instrumented:
        return

    # Imported lazily so the OpenTelemetry SDK is only required when enabled.
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "deployment.environment": settings.app_env,
        }
    )
    provider = TracerProvider(resource=resource)

    exporters_configured = False
    if settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
        )
        exporters_configured = True
    if settings.otel_console_export:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        exporters_configured = True

    if not exporters_configured:
        logger.warning("tracing.enabled_without_exporter", detail="Set OTEL exporter endpoint or console export.")

    trace.set_tracer_provider(provider)

    # Import here to avoid a circular import at module load (session imports config).
    from app.db.session import engine

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine)
    RedisInstrumentor().instrument()

    _instrumented = True
    logger.info(
        "tracing.configured",
        service=settings.otel_service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint or None,
        console=settings.otel_console_export,
    )
