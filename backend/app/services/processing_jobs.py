from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from .audit_log import (
    invoice_extraction_completed_event,
    invoice_status_changed_event,
    processing_job_retry_scheduled_event,
    processing_job_status_changed_event,
)
from .invoice_workflow import InvoiceStatus, transition_invoice_status


class ProcessingJobType(StrEnum):
    INVOICE_EXTRACTION = "invoice_extraction"


class ProcessingJobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingJobError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessingJobResult:
    processing_job_id: UUID
    job_type: ProcessingJobType
    status: ProcessingJobStatus


@dataclass(frozen=True)
class ProcessingJobPayload:
    invoice_id: UUID
    job_type: ProcessingJobType
    status: ProcessingJobStatus
    attempts: int


def build_invoice_extraction_job_payload(invoice_id: UUID) -> ProcessingJobPayload:
    return ProcessingJobPayload(
        invoice_id=invoice_id,
        job_type=ProcessingJobType.INVOICE_EXTRACTION,
        status=ProcessingJobStatus.QUEUED,
        attempts=0,
    )


def build_invoice_extraction_job(invoice_id: UUID):
    from app.models.processing import ProcessingJob

    payload = build_invoice_extraction_job_payload(invoice_id)
    return ProcessingJob(
        invoice_id=payload.invoice_id,
        job_type=payload.job_type.value,
        status=payload.status.value,
        attempts=payload.attempts,
    )


def enqueue_processing_job(redis_client: Any, processing_job_id: UUID) -> None:
    from app.core.config import settings

    redis_client.rpush(settings.processing_queue_name, str(processing_job_id))


def dequeue_processing_job(redis_client: Any, *, timeout_seconds: int | None = None) -> UUID | None:
    from app.core.config import settings

    timeout = settings.worker_poll_timeout_seconds if timeout_seconds is None else timeout_seconds
    result = redis_client.blpop([settings.processing_queue_name], timeout=timeout)
    if result is None:
        return None

    _, raw_job_id = result
    value = raw_job_id.decode("utf-8") if isinstance(raw_job_id, bytes) else str(raw_job_id)
    return UUID(value)


def process_invoice_extraction_job(db: Any, processing_job_id: UUID) -> ProcessingJobResult:
    from app.models.audit import AuditLog
    from app.models.invoice import Invoice
    from app.models.processing import ProcessingJob
    from app.services.file_storage import read_invoice_file
    from app.services.invoice_extraction import (
        build_invoice_extractor,
        persist_extraction_result,
    )

    job = db.get(ProcessingJob, processing_job_id)
    if job is None:
        raise ProcessingJobError("Processing job was not found.")

    invoice = db.get(Invoice, job.invoice_id)
    if invoice is None:
        _mark_job_failed(db, job=job, error_message="Invoice was not found.")
        raise ProcessingJobError("Invoice was not found for processing job.")

    if ProcessingJobStatus(job.status) not in {ProcessingJobStatus.QUEUED, ProcessingJobStatus.FAILED}:
        return ProcessingJobResult(
            processing_job_id=job.id,
            job_type=ProcessingJobType(job.job_type),
            status=ProcessingJobStatus(job.status),
        )

    _transition_job(db, job=job, invoice=invoice, status=ProcessingJobStatus.PROCESSING)
    _transition_invoice(db, invoice=invoice, status=InvoiceStatus.PROCESSING)
    db.flush()

    invoice_file = invoice.files[0] if invoice.files else None
    if invoice_file is None:
        raise ProcessingJobError("Invoice has no stored file to process.")

    file_bytes = read_invoice_file(storage_key=invoice_file.storage_key)
    extraction_result = build_invoice_extractor().extract(
        invoice=invoice,
        file_bytes=file_bytes,
        mime_type=invoice_file.mime_type,
    )
    previous_invoice_status = InvoiceStatus(invoice.status)
    extraction = persist_extraction_result(db, invoice=invoice, result=extraction_result)
    db.flush()
    extraction_event = invoice_extraction_completed_event(
        invoice_id=invoice.id,
        actor_id=invoice.uploaded_by,
        extraction_id=extraction.id,
        model_name=extraction.model_name,
        prompt_version=extraction.prompt_version,
        confidence_score=str(extraction.confidence_score) if extraction.confidence_score is not None else None,
    )
    db.add(
        AuditLog(
            organization_id=invoice.organization_id,
            actor_user_id=extraction_event.actor_id,
            entity_type=extraction_event.entity_type,
            entity_id=extraction_event.entity_id,
            action=extraction_event.action,
            event_metadata=extraction_event.metadata,
        )
    )
    if InvoiceStatus(invoice.status) != previous_invoice_status:
        invoice_event = invoice_status_changed_event(
            invoice_id=invoice.id,
            actor_id=invoice.uploaded_by,
            previous_status=previous_invoice_status,
            status=InvoiceStatus(invoice.status),
        )
        db.add(
            AuditLog(
                organization_id=invoice.organization_id,
                actor_user_id=invoice_event.actor_id,
                entity_type=invoice_event.entity_type,
                entity_id=invoice_event.entity_id,
                action=invoice_event.action,
                event_metadata=invoice_event.metadata,
            )
        )
    _transition_job(db, job=job, invoice=invoice, status=ProcessingJobStatus.COMPLETED)
    db.commit()
    db.refresh(job)

    return ProcessingJobResult(
        processing_job_id=job.id,
        job_type=ProcessingJobType(job.job_type),
        status=ProcessingJobStatus(job.status),
    )


def get_processing_job(db: Any, processing_job_id: UUID):
    return get_processing_job_for_organization(db, processing_job_id, organization_id=None)


def get_processing_job_for_organization(db: Any, processing_job_id: UUID, *, organization_id: UUID | None):
    from sqlalchemy import select

    from app.models.processing import ProcessingJob

    query = select(ProcessingJob).where(ProcessingJob.id == processing_job_id)
    if organization_id is not None:
        from app.models.invoice import Invoice

        query = query.join(Invoice).where(Invoice.organization_id == organization_id)

    job = db.scalar(query)
    if job is None:
        raise ProcessingJobError("Processing job was not found.")

    return job


def list_failed_processing_jobs(db: Any, *, limit: int = 50) -> list[Any]:
    return list_failed_processing_jobs_for_organization(db, organization_id=None, limit=limit)


def list_failed_processing_jobs_for_organization(
    db: Any,
    *,
    organization_id: UUID | None,
    limit: int = 50,
) -> list[Any]:
    from sqlalchemy import select

    from app.models.invoice import Invoice
    from app.models.processing import ProcessingJob

    query = (
        select(ProcessingJob)
        .where(ProcessingJob.status == ProcessingJobStatus.FAILED.value)
        .order_by(ProcessingJob.updated_at.desc())
        .limit(limit)
    )
    if organization_id is not None:
        query = query.join(Invoice).where(Invoice.organization_id == organization_id)

    return list(
        db.scalars(query)
    )


def requeue_processing_job(
    db: Any,
    redis_client: Any,
    *,
    processing_job_id: UUID,
    organization_id: UUID | None = None,
    actor_id: UUID,
    request_id: str | None = None,
):
    from app.models.audit import AuditLog
    from app.models.invoice import Invoice

    job = get_processing_job_for_organization(
        db,
        processing_job_id,
        organization_id=organization_id,
    )
    if ProcessingJobStatus(job.status) != ProcessingJobStatus.FAILED:
        raise ProcessingJobError("Only failed processing jobs can be reprocessed.")

    invoice = db.get(Invoice, job.invoice_id)
    if invoice is None:
        raise ProcessingJobError("Invoice was not found for processing job.")

    previous_job_status = job.status
    job.status = ProcessingJobStatus.QUEUED.value
    job.last_error = None
    job_event = processing_job_status_changed_event(
        invoice_id=invoice.id,
        actor_id=actor_id,
        processing_job_id=job.id,
        previous_status=previous_job_status,
        status=job.status,
    )
    db.add(
        AuditLog(
            organization_id=invoice.organization_id,
            actor_user_id=job_event.actor_id,
            entity_type=job_event.entity_type,
            entity_id=job_event.entity_id,
            action=job_event.action,
            event_metadata=job_event.metadata,
            request_id=request_id,
        )
    )

    previous_invoice_status = InvoiceStatus(invoice.status)
    invoice.status = transition_invoice_status(previous_invoice_status, InvoiceStatus.QUEUED).value
    invoice_event = invoice_status_changed_event(
        invoice_id=invoice.id,
        actor_id=actor_id,
        previous_status=previous_invoice_status,
        status=InvoiceStatus(invoice.status),
    )
    db.add(
        AuditLog(
            organization_id=invoice.organization_id,
            actor_user_id=invoice_event.actor_id,
            entity_type=invoice_event.entity_type,
            entity_id=invoice_event.entity_id,
            action=invoice_event.action,
            event_metadata=invoice_event.metadata,
            request_id=request_id,
        )
    )
    db.commit()
    enqueue_processing_job(redis_client, job.id)
    db.refresh(job)
    return job


def mark_processing_job_failed(db: Any, processing_job_id: UUID, error_message: str) -> ProcessingJobResult:
    from app.models.processing import ProcessingJob

    job = db.get(ProcessingJob, processing_job_id)
    if job is None:
        raise ProcessingJobError("Processing job was not found.")

    _mark_job_failed(db, job=job, error_message=error_message)
    db.commit()
    db.refresh(job)
    return ProcessingJobResult(
        processing_job_id=job.id,
        job_type=ProcessingJobType(job.job_type),
        status=ProcessingJobStatus(job.status),
    )


def record_processing_job_failure(
    db: Any,
    redis_client: Any,
    processing_job_id: UUID,
    error_message: str,
    *,
    max_attempts: int,
) -> ProcessingJobResult:
    from app.models.audit import AuditLog
    from app.models.invoice import Invoice
    from app.models.processing import ProcessingJob

    job = db.get(ProcessingJob, processing_job_id)
    if job is None:
        raise ProcessingJobError("Processing job was not found.")

    job.attempts += 1
    invoice = db.get(Invoice, job.invoice_id)

    if job.attempts < max_attempts:
        previous_status = job.status
        job.status = ProcessingJobStatus.QUEUED.value
        job.last_error = error_message
        if invoice is not None:
            invoice.status = InvoiceStatus.QUEUED.value
            retry_event = processing_job_retry_scheduled_event(
                invoice_id=invoice.id,
                actor_id=invoice.uploaded_by,
                processing_job_id=job.id,
                attempts=job.attempts,
                max_attempts=max_attempts,
                error_message=error_message,
            )
            db.add(
                AuditLog(
                    organization_id=invoice.organization_id,
                    actor_user_id=retry_event.actor_id,
                    entity_type=retry_event.entity_type,
                    entity_id=retry_event.entity_id,
                    action=retry_event.action,
                    event_metadata=retry_event.metadata,
                )
            )
            if previous_status != job.status:
                status_event = processing_job_status_changed_event(
                    invoice_id=invoice.id,
                    actor_id=invoice.uploaded_by,
                    processing_job_id=job.id,
                    previous_status=previous_status,
                    status=job.status,
                    error_message=error_message,
                )
                db.add(
                    AuditLog(
                        organization_id=invoice.organization_id,
                        actor_user_id=status_event.actor_id,
                        entity_type=status_event.entity_type,
                        entity_id=status_event.entity_id,
                        action=status_event.action,
                        event_metadata=status_event.metadata,
                    )
                )
        db.commit()
        enqueue_processing_job(redis_client, job.id)
        db.refresh(job)
        return ProcessingJobResult(
            processing_job_id=job.id,
            job_type=ProcessingJobType(job.job_type),
            status=ProcessingJobStatus(job.status),
        )

    _mark_job_failed(db, job=job, error_message=error_message)
    db.commit()
    db.refresh(job)
    return ProcessingJobResult(
        processing_job_id=job.id,
        job_type=ProcessingJobType(job.job_type),
        status=ProcessingJobStatus(job.status),
    )


def _transition_job(db: Any, *, job: Any, invoice: Any, status: ProcessingJobStatus) -> None:
    from app.models.audit import AuditLog

    previous_status = job.status
    job.status = status.value
    if status == ProcessingJobStatus.PROCESSING:
        job.attempts += 1
    event = processing_job_status_changed_event(
        invoice_id=invoice.id,
        actor_id=invoice.uploaded_by,
        processing_job_id=job.id,
        previous_status=previous_status,
        status=job.status,
    )
    db.add(
        AuditLog(
            organization_id=invoice.organization_id,
            actor_user_id=event.actor_id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            action=event.action,
            event_metadata=event.metadata,
        )
    )


def _transition_invoice(db: Any, *, invoice: Any, status: InvoiceStatus) -> None:
    from app.models.audit import AuditLog

    previous_status = InvoiceStatus(invoice.status)
    invoice.status = transition_invoice_status(previous_status, status).value
    event = invoice_status_changed_event(
        invoice_id=invoice.id,
        actor_id=invoice.uploaded_by,
        previous_status=previous_status,
        status=InvoiceStatus(invoice.status),
    )
    db.add(
        AuditLog(
            organization_id=invoice.organization_id,
            actor_user_id=event.actor_id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            action=event.action,
            event_metadata=event.metadata,
        )
    )


def _mark_job_failed(db: Any, *, job: Any, error_message: str) -> None:
    from app.models.audit import AuditLog
    from app.models.invoice import Invoice

    invoice = db.get(Invoice, job.invoice_id)
    previous_status = job.status
    job.status = ProcessingJobStatus.FAILED.value
    job.last_error = error_message
    if invoice is not None:
        invoice.status = InvoiceStatus.FAILED.value
        event = processing_job_status_changed_event(
            invoice_id=invoice.id,
            actor_id=invoice.uploaded_by,
            processing_job_id=job.id,
            previous_status=previous_status,
            status=job.status,
            error_message=error_message,
        )
        db.add(
            AuditLog(
                organization_id=invoice.organization_id,
                actor_user_id=event.actor_id,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                action=event.action,
                event_metadata=event.metadata,
            )
        )
