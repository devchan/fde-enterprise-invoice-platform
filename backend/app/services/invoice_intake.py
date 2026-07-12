from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from redis import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.invoice import Invoice, InvoiceFile
from app.models.supplier import Supplier
from app.services.audit_log import (
    invoice_status_changed_event,
    invoice_uploaded_event,
    processing_job_created_event,
)
from app.services.file_storage import (
    build_invoice_storage_key,
    delete_invoice_file_if_exists,
    store_invoice_file,
)
from app.services.file_validation import validate_invoice_file
from app.services.invoice_workflow import InvoiceStatus, transition_invoice_status
from app.services.processing_jobs import (
    ProcessingJobResult,
    ProcessingJobStatus,
    ProcessingJobType,
    build_invoice_extraction_job,
    enqueue_processing_job,
)


class DuplicateInvoiceError(ValueError):
    pass


class DuplicateInvoiceUploadError(ValueError):
    pass


class InvoiceNotFoundError(ValueError):
    pass


class SupplierNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class InvoiceIntakePayload:
    organization_id: UUID
    supplier_id: UUID | None
    uploaded_by: UUID
    invoice_number: str
    total_amount: Decimal | None
    currency: str
    file_checksum: str | None = None


@dataclass(frozen=True)
class InvoiceUploadPayload:
    organization_id: UUID
    supplier_id: UUID | None
    uploaded_by: UUID
    invoice_number: str
    total_amount: Decimal | None
    currency: str
    filename: str
    mime_type: str | None
    content: bytes


@dataclass(frozen=True)
class InvoiceIntakeResult:
    invoice_id: UUID
    organization_id: UUID
    supplier_id: UUID | None
    invoice_number: str
    status: InvoiceStatus
    storage_key: str | None = None
    processing_job: ProcessingJobResult | None = None


def create_invoice_metadata(
    db: Session,
    payload: InvoiceIntakePayload,
    *,
    request_id: str | None = None,
) -> InvoiceIntakeResult:
    _ensure_supplier_belongs_to_organization(db, payload)
    if _invoice_number_exists(db, payload):
        raise DuplicateInvoiceError("Invoice number already exists for this supplier and organization.")

    invoice = Invoice(
        organization_id=payload.organization_id,
        supplier_id=payload.supplier_id,
        uploaded_by=payload.uploaded_by,
        invoice_number=payload.invoice_number,
        total_amount=payload.total_amount,
        currency=payload.currency.upper(),
        status=InvoiceStatus.UPLOADED.value,
        file_checksum=payload.file_checksum,
    )
    db.add(invoice)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if "uq_invoice_org_supplier_number" in str(exc.orig):
            raise DuplicateInvoiceError("Invoice number already exists for this supplier and organization.") from exc
        raise

    event = invoice_uploaded_event(
        invoice_id=invoice.id,
        actor_id=payload.uploaded_by,
        organization_id=payload.organization_id,
        supplier_id=payload.supplier_id,
        invoice_number=payload.invoice_number,
    )
    db.add(
        AuditLog(
            organization_id=payload.organization_id,
            actor_user_id=event.actor_id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            action=event.action,
            event_metadata=event.metadata,
            request_id=request_id,
        )
    )
    db.commit()
    db.refresh(invoice)

    return InvoiceIntakeResult(
        invoice_id=invoice.id,
        organization_id=invoice.organization_id,
        supplier_id=invoice.supplier_id,
        invoice_number=invoice.invoice_number,
        status=InvoiceStatus(invoice.status),
    )


def create_invoice_upload(
    db: Session,
    payload: InvoiceUploadPayload,
    *,
    request_id: str | None = None,
) -> InvoiceIntakeResult:
    file_result = validate_invoice_file(
        filename=payload.filename,
        mime_type=payload.mime_type,
        file_size=len(payload.content),
        max_bytes=settings.invoice_upload_max_bytes,
    )
    checksum = sha256(payload.content).hexdigest()

    if _invoice_checksum_exists(db, payload.organization_id, checksum):
        raise DuplicateInvoiceUploadError("Invoice file was already uploaded for this organization.")

    invoice_payload = InvoiceIntakePayload(
        organization_id=payload.organization_id,
        supplier_id=payload.supplier_id,
        uploaded_by=payload.uploaded_by,
        invoice_number=payload.invoice_number,
        total_amount=payload.total_amount,
        currency=payload.currency,
        file_checksum=checksum,
    )
    _ensure_supplier_belongs_to_organization(db, invoice_payload)
    if _invoice_number_exists(db, invoice_payload):
        raise DuplicateInvoiceError("Invoice number already exists for this supplier and organization.")

    invoice = Invoice(
        organization_id=payload.organization_id,
        supplier_id=payload.supplier_id,
        uploaded_by=payload.uploaded_by,
        invoice_number=payload.invoice_number,
        total_amount=payload.total_amount,
        currency=payload.currency.upper(),
        status=InvoiceStatus.UPLOADED.value,
        file_checksum=checksum,
    )
    db.add(invoice)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if "uq_invoice_org_supplier_number" in str(exc.orig):
            raise DuplicateInvoiceError("Invoice number already exists for this supplier and organization.") from exc
        raise

    storage_key = build_invoice_storage_key(
        organization_id=payload.organization_id,
        invoice_id=invoice.id,
        extension=file_result.extension,
    )

    try:
        store_invoice_file(storage_key=storage_key, content=payload.content)
        processing_job = build_invoice_extraction_job(invoice.id)
        db.add(processing_job)
        db.flush()
        db.add(
            InvoiceFile(
                invoice_id=invoice.id,
                storage_key=storage_key,
                mime_type=file_result.mime_type,
                file_size=file_result.file_size,
            )
        )
        job_event = processing_job_created_event(
            invoice_id=invoice.id,
            actor_id=payload.uploaded_by,
            processing_job_id=processing_job.id,
            job_type=processing_job.job_type,
        )
        db.add(
            AuditLog(
                organization_id=payload.organization_id,
                actor_user_id=job_event.actor_id,
                entity_type=job_event.entity_type,
                entity_id=job_event.entity_id,
                action=job_event.action,
                event_metadata=job_event.metadata,
                request_id=request_id,
            )
        )
        previous_status = InvoiceStatus(invoice.status)
        invoice.status = transition_invoice_status(previous_status, InvoiceStatus.QUEUED).value
        status_event = invoice_status_changed_event(
            invoice_id=invoice.id,
            actor_id=payload.uploaded_by,
            previous_status=previous_status,
            status=InvoiceStatus(invoice.status),
        )
        db.add(
            AuditLog(
                organization_id=payload.organization_id,
                actor_user_id=status_event.actor_id,
                entity_type=status_event.entity_type,
                entity_id=status_event.entity_id,
                action=status_event.action,
                event_metadata=status_event.metadata,
                request_id=request_id,
            )
        )
        event = invoice_uploaded_event(
            invoice_id=invoice.id,
            actor_id=payload.uploaded_by,
            organization_id=payload.organization_id,
            supplier_id=payload.supplier_id,
            invoice_number=payload.invoice_number,
        )
        db.add(
            AuditLog(
                organization_id=payload.organization_id,
                actor_user_id=event.actor_id,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                action=event.action,
                event_metadata={
                    **event.metadata,
                    "file_checksum": checksum,
                    "storage_key": storage_key,
                    "mime_type": file_result.mime_type,
                    "file_size": file_result.file_size,
                },
                request_id=request_id,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        delete_invoice_file_if_exists(storage_key=storage_key)
        raise

    db.refresh(invoice)
    enqueue_processing_job(Redis.from_url(settings.redis_url), processing_job.id)
    return InvoiceIntakeResult(
        invoice_id=invoice.id,
        organization_id=invoice.organization_id,
        supplier_id=invoice.supplier_id,
        invoice_number=invoice.invoice_number,
        status=InvoiceStatus(invoice.status),
        storage_key=storage_key,
        processing_job=ProcessingJobResult(
            processing_job_id=processing_job.id,
            job_type=ProcessingJobType(processing_job.job_type),
            status=ProcessingJobStatus(processing_job.status),
        ),
    )


def change_invoice_status(
    db: Session,
    *,
    invoice_id: UUID,
    organization_id: UUID,
    actor_id: UUID,
    requested_status: InvoiceStatus,
    request_id: str | None = None,
) -> InvoiceIntakeResult:
    invoice = db.scalar(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .where(Invoice.organization_id == organization_id)
    )
    if invoice is None:
        raise InvoiceNotFoundError("Invoice was not found.")

    previous_status = InvoiceStatus(invoice.status)
    next_status = transition_invoice_status(previous_status, requested_status)
    invoice.status = next_status.value

    event = invoice_status_changed_event(
        invoice_id=invoice.id,
        actor_id=actor_id,
        previous_status=previous_status,
        status=next_status,
    )
    db.add(
        AuditLog(
            organization_id=invoice.organization_id,
            actor_user_id=event.actor_id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            action=event.action,
            event_metadata=event.metadata,
            request_id=request_id,
        )
    )
    db.commit()
    db.refresh(invoice)

    return InvoiceIntakeResult(
        invoice_id=invoice.id,
        organization_id=invoice.organization_id,
        supplier_id=invoice.supplier_id,
        invoice_number=invoice.invoice_number,
        status=InvoiceStatus(invoice.status),
    )


def _invoice_number_exists(db: Session, payload: InvoiceIntakePayload) -> bool:
    supplier_clause = (
        Invoice.supplier_id.is_(None)
        if payload.supplier_id is None
        else Invoice.supplier_id == payload.supplier_id
    )
    existing_invoice_id = db.scalar(
        select(Invoice.id).where(
            Invoice.organization_id == payload.organization_id,
            supplier_clause,
            Invoice.invoice_number == payload.invoice_number,
        )
    )

    return existing_invoice_id is not None


def _ensure_supplier_belongs_to_organization(db: Session, payload: InvoiceIntakePayload) -> None:
    if payload.supplier_id is None:
        return

    supplier_id = db.scalar(
        select(Supplier.id).where(
            Supplier.id == payload.supplier_id,
            Supplier.organization_id == payload.organization_id,
        )
    )
    if supplier_id is None:
        raise SupplierNotFoundError("Supplier was not found for this organization.")


def _invoice_checksum_exists(db: Session, organization_id: UUID, checksum: str) -> bool:
    existing_invoice_id = db.scalar(
        select(Invoice.id).where(
            Invoice.organization_id == organization_id,
            Invoice.file_checksum == checksum,
        )
    )

    return existing_invoice_id is not None
