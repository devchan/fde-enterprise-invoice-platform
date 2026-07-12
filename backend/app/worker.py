"""Standalone background worker process.

Long-running loop that pulls invoice-processing jobs off the Redis queue and
runs extraction for each. Runs as a separate process from the API so slow AI
calls never block request handling.
"""

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
    # Worker runs in its own process, so it must set up structured logging itself.
    configure_logging()
    redis_client = Redis.from_url(settings.redis_url)
    while True:
        processing_job_id = dequeue_processing_job(redis_client)
        # Empty queue: back off briefly rather than busy-spinning on Redis.
        if processing_job_id is None:
            sleep(settings.worker_sleep_seconds)
            continue

        # Fresh session per job keeps one job's failure/rollback from poisoning
        # the next; the finally block below always closes it.
        db = SessionLocal()
        started_at = time.perf_counter()
        job = db.get(ProcessingJob, processing_job_id)
        # Capture invoice_id up front so failure logs stay useful even if the
        # job row is missing or the session is later rolled back.
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
            # Discard the failed transaction before recording the failure, so the
            # bookkeeping write below runs on a clean session.
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
                # Persist the failure and let the service decide whether to
                # retry (re-enqueue) or mark the job permanently failed based on
                # the attempt count vs. the configured max.
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
                # If even recording the failure fails, roll back and re-raise to
                # crash the loop rather than silently drop the job's error state;
                # the process supervisor is expected to restart the worker.
                db.rollback()
                raise
        finally:
            db.close()


if __name__ == "__main__":
    run_worker()
