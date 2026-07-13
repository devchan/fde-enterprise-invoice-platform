"""Aggregates every feature router into the single router mounted by the app."""

from fastapi import APIRouter

from app.api.audit_logs import router as audit_logs_router
from app.api.auth import router as auth_router
from app.api.extraction import router as extraction_router
from app.api.health import router as health_router
from app.api.invoices import router as invoices_router
from app.api.metrics import router as metrics_router
from app.api.processing_jobs import router as processing_jobs_router
from app.api.users import router as users_router

api_router = APIRouter()
# Health and metrics stay unversioned so infra probes/scrapers have stable
# paths; all business endpoints live under the /api/v1 version prefix.
api_router.include_router(health_router)
api_router.include_router(metrics_router)
api_router.include_router(auth_router, prefix="/api/v1")
api_router.include_router(audit_logs_router, prefix="/api/v1")
api_router.include_router(extraction_router, prefix="/api/v1")
api_router.include_router(invoices_router, prefix="/api/v1")
api_router.include_router(processing_jobs_router, prefix="/api/v1")
api_router.include_router(users_router, prefix="/api/v1")
