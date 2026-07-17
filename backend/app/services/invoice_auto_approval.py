"""Touchless processing: auto-approve invoices that need no human judgement.

An invoice qualifies only when every validation rule passed (status is
VALIDATION_PASSED — anomaly detection has already had its chance to demote it),
the extractor's overall confidence meets the auto-approval bar, and no single
field confidence falls below it. The approval is recorded with a dedicated
audit action so auto-approvals are always distinguishable from human ones.
"""

from decimal import Decimal
from typing import Any

import structlog

from app.core.config import settings
from app.services.audit_log import invoice_auto_approved_event, invoice_status_changed_event
from app.services.events import publish_event
from app.services.invoice_extraction import ExtractedInvoicePayload, minimum_field_confidence
from app.services.invoice_workflow import InvoiceStatus, transition_invoice_status

logger = structlog.get_logger("app.services.invoice_auto_approval")


def auto_approval_decision(*, status: InvoiceStatus, payload: ExtractedInvoicePayload) -> tuple[bool, str]:
    """Pure decision function: (approve?, reason). Kept side-effect-free so the
    threshold logic is unit-testable without a database."""
    if not settings.auto_approval_enabled:
        return False, "auto_approval_disabled"
    if status != InvoiceStatus.VALIDATION_PASSED:
        return False, f"status_not_eligible:{status.value}"

    threshold = Decimal(settings.auto_approval_min_confidence)
    if payload.confidence_score < threshold:
        return False, "overall_confidence_below_threshold"

    min_field = minimum_field_confidence(payload)
    # Extractors that don't report per-field confidences (older prompt versions)
    # still qualify on the overall score alone.
    if min_field is not None and min_field < threshold:
        return False, "field_confidence_below_threshold"

    return True, "confidence_met"


def maybe_auto_approve(db: Any, *, invoice: Any, payload: ExtractedInvoicePayload) -> bool:
    """Apply the auto-approval decision to an invoice. Commits its own work;
    a failure here leaves the invoice in VALIDATION_PASSED for normal manual
    approval, so this step is safe to run best-effort after extraction."""
    from app.models.audit import AuditLog

    try:
        approve, reason = auto_approval_decision(
            status=InvoiceStatus(invoice.status),
            payload=payload,
        )
        if not approve:
            return False

        previous_status = InvoiceStatus(invoice.status)
        invoice.status = transition_invoice_status(previous_status, InvoiceStatus.APPROVED).value

        approved_event = invoice_auto_approved_event(
            invoice_id=invoice.id,
            actor_id=invoice.uploaded_by,
            confidence_score=str(payload.confidence_score),
            min_field_confidence=(
                str(minimum_field_confidence(payload))
                if minimum_field_confidence(payload) is not None
                else None
            ),
        )
        status_event = invoice_status_changed_event(
            invoice_id=invoice.id,
            actor_id=invoice.uploaded_by,
            previous_status=previous_status,
            status=InvoiceStatus.APPROVED,
        )
        for event in (approved_event, status_event):
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
        db.commit()

        from app.core.metrics import INVOICES_AUTO_APPROVED

        INVOICES_AUTO_APPROVED.inc()
        publish_event(
            invoice.organization_id,
            {
                "type": "invoice.status_changed",
                "invoice_id": str(invoice.id),
                "status": invoice.status,
            },
        )
        logger.info("invoice.auto_approved", invoice_id=str(invoice.id))
        return True
    except Exception as exc:
        db.rollback()
        logger.warning(
            "invoice.auto_approval_failed",
            invoice_id=str(invoice.id),
            error_message=str(exc),
        )
        return False
