"""Invoice lifecycle state machine: the canonical set of statuses and the
transitions allowed between them. Centralising this here keeps every service
(intake, extraction, review) agreeing on which status changes are legal."""

from enum import StrEnum


class InvoiceStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    VALIDATION_PASSED = "validation_passed"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


# Adjacency map of the state machine. Any status may move to FAILED; APPROVED
# and REJECTED are terminal (empty set); FAILED can only be re-QUEUED for retry;
# REVIEW_REQUIRED can loop back to PROCESSING when a reviewer requests re-extraction.
ALLOWED_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.UPLOADED: {InvoiceStatus.QUEUED, InvoiceStatus.FAILED},
    InvoiceStatus.QUEUED: {InvoiceStatus.PROCESSING, InvoiceStatus.FAILED},
    InvoiceStatus.PROCESSING: {InvoiceStatus.EXTRACTED, InvoiceStatus.REVIEW_REQUIRED, InvoiceStatus.FAILED},
    InvoiceStatus.EXTRACTED: {InvoiceStatus.VALIDATION_PASSED, InvoiceStatus.REVIEW_REQUIRED, InvoiceStatus.FAILED},
    InvoiceStatus.VALIDATION_PASSED: {InvoiceStatus.APPROVED, InvoiceStatus.REVIEW_REQUIRED, InvoiceStatus.FAILED},
    InvoiceStatus.REVIEW_REQUIRED: {InvoiceStatus.APPROVED, InvoiceStatus.REJECTED, InvoiceStatus.PROCESSING},
    InvoiceStatus.APPROVED: set(),
    InvoiceStatus.REJECTED: set(),
    InvoiceStatus.FAILED: {InvoiceStatus.QUEUED},
}


def transition_invoice_status(current: InvoiceStatus, requested: InvoiceStatus) -> InvoiceStatus:
    allowed_next_statuses = ALLOWED_TRANSITIONS[current]
    if requested not in allowed_next_statuses:
        raise ValueError(f"Invoice status cannot transition from {current} to {requested}.")

    return requested

