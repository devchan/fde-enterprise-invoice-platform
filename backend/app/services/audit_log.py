"""Factory functions that build :class:`AuditEvent` value objects.

Centralising every audit event here keeps action names and metadata shapes
consistent across the codebase (callers never hand-write the ``action`` string),
which is what downstream audit querying and compliance reporting rely on.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from .invoice_workflow import InvoiceStatus


@dataclass(frozen=True)
class AuditEvent:
    actor_id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    # Stamped at construction in UTC so an event's time reflects when it happened,
    # independent of when the row is eventually committed.
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


def invoice_uploaded_event(
    *,
    invoice_id: UUID,
    actor_id: UUID,
    organization_id: UUID,
    supplier_id: UUID | None,
    invoice_number: str,
) -> AuditEvent:
    return AuditEvent(
        actor_id=actor_id,
        entity_type="invoice",
        entity_id=invoice_id,
        action="invoice.uploaded",
        metadata={
            "organization_id": str(organization_id),
            "supplier_id": str(supplier_id) if supplier_id else None,
            "invoice_number": invoice_number,
            "status": InvoiceStatus.UPLOADED.value,
        },
    )


def invoice_status_changed_event(
    *,
    invoice_id: UUID,
    actor_id: UUID,
    previous_status: InvoiceStatus,
    status: InvoiceStatus,
) -> AuditEvent:
    return AuditEvent(
        actor_id=actor_id,
        entity_type="invoice",
        entity_id=invoice_id,
        action="invoice.status_changed",
        metadata={
            "previous_status": previous_status.value,
            "status": status.value,
        },
    )


def processing_job_created_event(
    *,
    invoice_id: UUID,
    actor_id: UUID,
    processing_job_id: UUID,
    job_type: str,
) -> AuditEvent:
    return AuditEvent(
        actor_id=actor_id,
        entity_type="invoice",
        entity_id=invoice_id,
        action="processing_job.created",
        metadata={
            "processing_job_id": str(processing_job_id),
            "job_type": job_type,
        },
    )


def processing_job_status_changed_event(
    *,
    invoice_id: UUID,
    actor_id: UUID,
    processing_job_id: UUID,
    previous_status: str,
    status: str,
    error_message: str | None = None,
) -> AuditEvent:
    metadata: dict[str, Any] = {
        "processing_job_id": str(processing_job_id),
        "previous_status": previous_status,
        "status": status,
    }
    if error_message:
        metadata["error_message"] = error_message

    return AuditEvent(
        actor_id=actor_id,
        entity_type="invoice",
        entity_id=invoice_id,
        action="processing_job.status_changed",
        metadata=metadata,
    )


def processing_job_retry_scheduled_event(
    *,
    invoice_id: UUID,
    actor_id: UUID,
    processing_job_id: UUID,
    attempts: int,
    max_attempts: int,
    error_message: str,
) -> AuditEvent:
    return AuditEvent(
        actor_id=actor_id,
        entity_type="invoice",
        entity_id=invoice_id,
        action="processing_job.retry_scheduled",
        metadata={
            "processing_job_id": str(processing_job_id),
            "attempts": attempts,
            "max_attempts": max_attempts,
            "error_message": error_message,
        },
    )


def invoice_extraction_completed_event(
    *,
    invoice_id: UUID,
    actor_id: UUID,
    extraction_id: UUID,
    model_name: str,
    prompt_version: str,
    confidence_score: str | None,
) -> AuditEvent:
    return AuditEvent(
        actor_id=actor_id,
        entity_type="invoice",
        entity_id=invoice_id,
        action="invoice.extraction_completed",
        metadata={
            "extraction_id": str(extraction_id),
            "model_name": model_name,
            "prompt_version": prompt_version,
            "confidence_score": confidence_score,
        },
    )


def invoice_review_corrections_saved_event(
    *,
    invoice_id: UUID,
    actor_id: UUID,
    corrected_fields: dict[str, Any],
) -> AuditEvent:
    return AuditEvent(
        actor_id=actor_id,
        entity_type="invoice",
        entity_id=invoice_id,
        action="invoice.review_corrections_saved",
        metadata={
            # Log only which fields changed, not their values, to keep
            # potentially sensitive invoice data out of the audit trail.
            "corrected_fields": sorted(corrected_fields.keys()),
        },
    )


def invoice_review_decision_event(
    *,
    invoice_id: UUID,
    actor_id: UUID,
    review_id: UUID,
    decision: str,
    previous_status: InvoiceStatus,
    status: InvoiceStatus,
) -> AuditEvent:
    return AuditEvent(
        actor_id=actor_id,
        entity_type="invoice",
        entity_id=invoice_id,
        action="invoice.review_decision",
        metadata={
            "review_id": str(review_id),
            "decision": decision,
            "previous_status": previous_status.value,
            "status": status.value,
        },
    )


def invoice_auto_approved_event(
    *,
    invoice_id: UUID,
    actor_id: UUID,
    confidence_score: str,
    min_field_confidence: str | None,
) -> AuditEvent:
    # Distinct action (not invoice.review_decision) so compliance reporting can
    # always separate machine approvals from human ones.
    return AuditEvent(
        actor_id=actor_id,
        entity_type="invoice",
        entity_id=invoice_id,
        action="invoice.auto_approved",
        metadata={
            "confidence_score": confidence_score,
            "min_field_confidence": min_field_confidence,
            "status": InvoiceStatus.APPROVED.value,
        },
    )


def invoice_anomaly_flagged_event(
    *,
    invoice_id: UUID,
    actor_id: UUID,
    rule_code: str,
    message: str,
) -> AuditEvent:
    return AuditEvent(
        actor_id=actor_id,
        entity_type="invoice",
        entity_id=invoice_id,
        action="invoice.anomaly_flagged",
        metadata={
            "rule_code": rule_code,
            "message": message,
        },
    )


def user_admin_event(
    *,
    actor_id: UUID,
    user_id: UUID,
    action: str,
    metadata: dict[str, Any],
) -> AuditEvent:
    return AuditEvent(
        actor_id=actor_id,
        entity_type="user",
        entity_id=user_id,
        action=action,
        metadata=metadata,
    )
