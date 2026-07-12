import time
from time import sleep

import structlog
from redis import Redis

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.processing import ProcessingJob
from app.services.processing_jobs import (
    dequeue_processing_job,
    process_invoice_extraction_job,
    record_processing_job_failure,
)

logger = structlog.get_logger("app.worker")


def run_worker() -> None:
    configure_logging()
    redis_client = Redis.from_url(settings.redis_url)
    while True:
        processing_job_id = dequeue_processing_job(redis_client)
        if processing_job_id is None:
            sleep(settings.worker_sleep_seconds)
            continue

        db = SessionLocal()
        started_at = time.perf_counter()
        job = db.get(ProcessingJob, processing_job_id)
        invoice_id = job.invoice_id if job is not None else None
        logger.info(
            "processing_job.started",
            processing_job_id=str(processing_job_id),
            invoice_id=str(invoice_id) if invoice_id is not None else None,
        )
        try:
            result = process_invoice_extraction_job(db, processing_job_id)
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.info(
                "processing_job.completed",
                processing_job_id=str(result.processing_job_id),
                invoice_id=str(invoice_id) if invoice_id is not None else None,
                status=result.status.value,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            db.rollback()
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.error(
                "processing_job.failed",
                processing_job_id=str(processing_job_id),
                invoice_id=str(invoice_id) if invoice_id is not None else None,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            try:
                result = record_processing_job_failure(
                    db,
                    redis_client,
                    processing_job_id,
                    str(exc),
                    max_attempts=settings.processing_job_max_attempts,
                )
                logger.info(
                    "processing_job.failure_recorded",
                    processing_job_id=str(result.processing_job_id),
                    invoice_id=str(invoice_id) if invoice_id is not None else None,
                    status=result.status.value,
                    max_attempts=settings.processing_job_max_attempts,
                )
            except Exception:
                db.rollback()
                raise
        finally:
            db.close()


if __name__ == "__main__":
    run_worker()
