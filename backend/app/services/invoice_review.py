"""Human review of extracted invoices: list/fetch invoices for the review
queue, apply reviewer corrections, and record approve/reject decisions with a
full audit trail. Uses row locking plus an optimistic-concurrency check so two
reviewers cannot clobber each other's edits."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.audit import AuditLog
from app.models.invoice import Invoice, InvoiceLineItem, InvoiceReview
from app.services.audit_log import (
    invoice_review_corrections_saved_event,
    invoice_review_decision_event,
    invoice_status_changed_event,
)
from app.services.events import publish_event
from app.services.invoice_intake import DuplicateInvoiceError, InvoiceNotFoundError
from app.services.invoice_workflow import InvoiceStatus, transition_invoice_status


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class InvoiceReviewError(ValueError):
    pass


class InvoiceReviewConflictError(InvoiceReviewError):
    pass


@dataclass(frozen=True)
class CorrectedLineItem:
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None


@dataclass(frozen=True)
class InvoiceReviewPayload:
    reviewer_id: UUID
    decision: ReviewDecision
    notes: str | None
    corrected_fields: dict[str, Any]
    expected_updated_at: datetime | None = None


# Whitelist of invoice fields a reviewer may overwrite; anything else in the
# corrections payload is rejected to prevent editing unintended columns.
SUPPORTED_CORRECTED_FIELDS = {
    "invoice_number",
    "invoice_date",
    "total_amount",
    "currency",
    "line_items",
}


def get_invoice_detail(db: Session, invoice_id: UUID, *, organization_id: UUID) -> Invoice:
    invoice = db.scalar(
        _invoice_detail_query()
        .where(Invoice.id == invoice_id)
        .where(Invoice.organization_id == organization_id)
    )
    if invoice is None:
        raise InvoiceNotFoundError("Invoice was not found.")

    return invoice


def list_invoices(
    db: Session,
    *,
    organization_id: UUID,
    status: InvoiceStatus | None = None,
    review_queue: bool = False,
    limit: int = 50,
) -> list[Invoice]:
    query = (
        _invoice_detail_query()
        .where(Invoice.organization_id == organization_id)
        .order_by(Invoice.updated_at.desc())
        .limit(limit)
    )
    if review_queue:
        query = query.where(Invoice.status == InvoiceStatus.REVIEW_REQUIRED.value)
    elif status is not None:
        query = query.where(Invoice.status == status.value)

    return list(db.scalars(query))


def submit_invoice_review(
    db: Session,
    *,
    invoice_id: UUID,
    organization_id: UUID,
    payload: InvoiceReviewPayload,
    request_id: str | None = None,
) -> Invoice:
    # Lock the row for the duration of the transaction so a concurrent review
    # cannot interleave between the conflict check and the status update.
    invoice = db.scalar(
        _invoice_detail_query()
        .where(Invoice.id == invoice_id)
        .where(Invoice.organization_id == organization_id)
        .with_for_update()
    )
    if invoice is None:
        raise InvoiceNotFoundError("Invoice was not found.")

    # Optimistic-concurrency guard: reject the review if the invoice changed
    # since the reviewer loaded it (they'd be acting on stale data).
    if payload.expected_updated_at is not None and not _same_instant(invoice.updated_at, payload.expected_updated_at):
        raise InvoiceReviewConflictError("Invoice was changed after the reviewer loaded it.")

    previous_status = InvoiceStatus(invoice.status)
    next_status = _review_decision_status(payload.decision)
    try:
        transition_invoice_status(previous_status, next_status)
    except ValueError as exc:
        raise InvoiceReviewError(str(exc)) from exc

    _apply_corrected_fields(invoice=invoice, corrected_fields=payload.corrected_fields)
    if "line_items" in payload.corrected_fields:
        _replace_line_items(db, invoice=invoice, line_items=payload.corrected_fields["line_items"])

    review = InvoiceReview(
        invoice_id=invoice.id,
        reviewer_id=payload.reviewer_id,
        decision=payload.decision.value,
        notes=payload.notes,
        corrected_fields=payload.corrected_fields or None,
    )
    db.add(review)
    try:
        db.flush()
    except IntegrityError as exc:
        # A corrected invoice_number may collide with an existing one; surface
        # that as a duplicate error rather than a raw DB failure.
        db.rollback()
        _raise_duplicate_invoice_if_applicable(exc)
        raise

    if payload.corrected_fields:
        event = invoice_review_corrections_saved_event(
            invoice_id=invoice.id,
            actor_id=payload.reviewer_id,
            corrected_fields=payload.corrected_fields,
        )
        db.add(_audit_log(invoice=invoice, event=event, request_id=request_id))

    invoice.status = next_status.value
    decision_event = invoice_review_decision_event(
        invoice_id=invoice.id,
        actor_id=payload.reviewer_id,
        review_id=review.id,
        decision=payload.decision.value,
        previous_status=previous_status,
        status=next_status,
    )
    db.add(_audit_log(invoice=invoice, event=decision_event, request_id=request_id))

    status_event = invoice_status_changed_event(
        invoice_id=invoice.id,
        actor_id=payload.reviewer_id,
        previous_status=previous_status,
        status=next_status,
    )
    db.add(_audit_log(invoice=invoice, event=status_event, request_id=request_id))

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_duplicate_invoice_if_applicable(exc)
        raise

    # Each corrected field is a ground-truth signal that extraction got that
    # field wrong; the counter feeds the per-field accuracy dashboards.
    if payload.corrected_fields:
        from app.core.metrics import EXTRACTION_FIELD_CORRECTIONS

        for field_name in payload.corrected_fields:
            EXTRACTION_FIELD_CORRECTIONS.labels(field_name).inc()

    publish_event(
        invoice.organization_id,
        {
            "type": "invoice.status_changed",
            "invoice_id": str(invoice.id),
            "status": invoice.status,
        },
    )

    return get_invoice_detail(db, invoice.id, organization_id=organization_id)


def _invoice_detail_query():
    # Eager-load every child relationship up front so the API can serialize the
    # full invoice without triggering N+1 lazy loads.
    return select(Invoice).options(
        selectinload(Invoice.files),
        selectinload(Invoice.line_items),
        selectinload(Invoice.extractions),
        selectinload(Invoice.validation_results),
        selectinload(Invoice.reviews),
        selectinload(Invoice.processing_jobs),
    )


def _review_decision_status(decision: ReviewDecision) -> InvoiceStatus:
    if decision == ReviewDecision.APPROVE:
        return InvoiceStatus.APPROVED
    if decision == ReviewDecision.REJECT:
        return InvoiceStatus.REJECTED
    raise InvoiceReviewError("Unsupported review decision.")


def _apply_corrected_fields(*, invoice: Invoice, corrected_fields: dict[str, Any]) -> None:
    unsupported_fields = set(corrected_fields) - SUPPORTED_CORRECTED_FIELDS
    if unsupported_fields:
        raise InvoiceReviewError(f"Unsupported corrected fields: {', '.join(sorted(unsupported_fields))}.")

    if "invoice_number" in corrected_fields:
        invoice.invoice_number = corrected_fields["invoice_number"]
    if "invoice_date" in corrected_fields:
        invoice.invoice_date = _parse_date(corrected_fields["invoice_date"])
    if "total_amount" in corrected_fields:
        invoice.total_amount = _parse_decimal(corrected_fields["total_amount"])
    if "currency" in corrected_fields:
        invoice.currency = str(corrected_fields["currency"]).upper()


def _replace_line_items(db: Session, *, invoice: Invoice, line_items: Any) -> None:
    if not isinstance(line_items, list):
        raise InvoiceReviewError("Corrected line_items must be a list.")

    # Full replace rather than diff/merge: clear the existing line items and
    # rebuild from the corrected set so the stored rows match exactly.
    db.query(InvoiceLineItem).filter(InvoiceLineItem.invoice_id == invoice.id).delete(synchronize_session=False)
    for raw_item in line_items:
        if not isinstance(raw_item, dict):
            raise InvoiceReviewError("Each corrected line item must be an object.")
        description = str(raw_item.get("description") or "").strip()
        if not description:
            raise InvoiceReviewError("Each corrected line item must include a description.")
        db.add(
            InvoiceLineItem(
                invoice_id=invoice.id,
                description=description,
                quantity=_parse_decimal(raw_item.get("quantity")),
                unit_price=_parse_decimal(raw_item.get("unit_price")),
                line_total=_parse_decimal(raw_item.get("line_total")),
            )
        )


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _same_instant(left: datetime, right: datetime) -> bool:
    # Compare via ISO strings so the client can round-trip the timestamp it
    # received verbatim, sidestepping microsecond/tzinfo representation quirks.
    return left.isoformat() == right.isoformat()


def _audit_log(*, invoice: Invoice, event, request_id: str | None) -> AuditLog:
    return AuditLog(
        organization_id=invoice.organization_id,
        actor_user_id=event.actor_id,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        action=event.action,
        event_metadata=event.metadata,
        request_id=request_id,
    )


def _raise_duplicate_invoice_if_applicable(exc: IntegrityError) -> None:
    if "uq_invoice_org_supplier_number" in str(exc.orig):
        raise DuplicateInvoiceError("Invoice number already exists for this supplier and organization.") from exc
