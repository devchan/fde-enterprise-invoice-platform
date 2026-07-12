from fastapi import APIRouter, Depends, Response
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.metrics import CONTENT_TYPE, render_prometheus_metrics
from app.db.session import get_db
from app.models.invoice import InvoiceExtraction, InvoiceValidationResult
from app.models.processing import ProcessingJob
from app.services.processing_jobs import ProcessingJobStatus, ProcessingJobType

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)) -> Response:
    queue_depth = _processing_queue_depth()
    return Response(
        content=render_prometheus_metrics(
            queue_depth=queue_depth,
            database_metrics=_database_metrics(db),
        ),
        media_type=CONTENT_TYPE,
    )


def _processing_queue_depth() -> int | None:
    try:
        return int(Redis.from_url(settings.redis_url).llen(settings.processing_queue_name))
    except Exception:
        return None


def _database_metrics(db: Session) -> dict[str, str]:
    failed_jobs = db.scalar(
        select(func.count())
        .select_from(ProcessingJob)
        .where(ProcessingJob.job_type == ProcessingJobType.INVOICE_EXTRACTION.value)
        .where(ProcessingJob.status == ProcessingJobStatus.FAILED.value)
    )
    validation_failures = db.scalar(
        select(func.count())
        .select_from(InvoiceValidationResult)
        .where(InvoiceValidationResult.passed.is_(False))
    )
    completed_job_count = db.scalar(
        select(func.count())
        .select_from(ProcessingJob)
        .where(ProcessingJob.job_type == ProcessingJobType.INVOICE_EXTRACTION.value)
        .where(ProcessingJob.status == ProcessingJobStatus.COMPLETED.value)
    )
    duration_sum = db.scalar(
        select(func.coalesce(func.sum(func.extract("epoch", ProcessingJob.updated_at - ProcessingJob.created_at)), 0))
        .select_from(ProcessingJob)
        .where(ProcessingJob.job_type == ProcessingJobType.INVOICE_EXTRACTION.value)
        .where(ProcessingJob.status == ProcessingJobStatus.COMPLETED.value)
    )
    ai_cost_total = db.scalar(
        select(func.coalesce(func.sum(InvoiceExtraction.estimated_cost), 0))
        .select_from(InvoiceExtraction)
    )

    return {
        "processing_jobs_failed_total": str(failed_jobs or 0),
        "processing_job_duration_seconds_sum": f"{float(duration_sum or 0):.6f}",
        "processing_job_duration_seconds_count": str(completed_job_count or 0),
        "validation_failures_total": str(validation_failures or 0),
        "ai_estimated_cost_total": f"{float(ai_cost_total or 0):.6f}",
    }
