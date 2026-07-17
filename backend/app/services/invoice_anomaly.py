"""Post-extraction anomaly detection.

Runs after extraction (and embedding) has been persisted and looks for signals
that rules on the document alone cannot catch:

- amount outlier: the total is far outside the supplier's approved history
  (z-score over previously approved amounts);
- near-duplicate: the invoice's embedding is almost identical to another
  invoice in the organization (resubmission / duplicate billing).

Hits are written as warning validation results and demote a VALIDATION_PASSED
invoice back to REVIEW_REQUIRED, so an anomalous invoice can never be
auto-approved. Detection is best-effort: a failure here must not fail a job
whose extraction already succeeded.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog

from app.core.config import settings
from app.services.audit_log import invoice_anomaly_flagged_event, invoice_status_changed_event
from app.services.events import publish_event
from app.services.invoice_workflow import InvoiceStatus, transition_invoice_status
from app.services.validation_explanations import explain_validation_failures

logger = structlog.get_logger("app.services.invoice_anomaly")


@dataclass(frozen=True)
class AnomalyFlag:
    rule_code: str
    message: str
    # Mirrors InvoiceValidationResult's shape so explanations and persistence
    # can treat anomalies exactly like failed validation rules.
    severity: str = "warning"
    passed: bool = False


def detect_anomalies(db: Any, *, invoice: Any) -> list[AnomalyFlag]:
    flags: list[AnomalyFlag] = []
    flags.extend(_detect_amount_outlier(db, invoice=invoice))
    flags.extend(_detect_near_duplicate(db, invoice=invoice))
    return flags


def _detect_amount_outlier(db: Any, *, invoice: Any) -> list[AnomalyFlag]:
    if invoice.supplier_id is None or invoice.total_amount is None:
        return []

    from sqlalchemy import select

    from app.models.invoice import Invoice

    amounts = [
        Decimal(value)
        for value in db.scalars(
            select(Invoice.total_amount).where(
                Invoice.organization_id == invoice.organization_id,
                Invoice.supplier_id == invoice.supplier_id,
                Invoice.id != invoice.id,
                Invoice.status == InvoiceStatus.APPROVED.value,
                Invoice.total_amount.is_not(None),
            )
        )
    ]
    # Too little history makes a z-score meaningless; stay silent rather than
    # flagging every second invoice from a new supplier.
    if len(amounts) < max(settings.anomaly_min_history, 2):
        return []

    mean = sum(amounts) / len(amounts)
    variance = sum((amount - mean) ** 2 for amount in amounts) / len(amounts)
    std = variance.sqrt()
    if std == 0:
        # Identical history: any different amount is technically infinite z-score;
        # only flag when it actually differs.
        if invoice.total_amount == mean:
            return []
        z_score = Decimal("Infinity")
    else:
        z_score = abs(Decimal(invoice.total_amount) - mean) / std

    if z_score <= Decimal(settings.anomaly_amount_zscore_threshold):
        return []

    return [
        AnomalyFlag(
            rule_code="amount_anomaly",
            message=(
                f"Invoice total {invoice.total_amount} {invoice.currency} is unusual for this supplier "
                f"(approved history mean {mean.quantize(Decimal('0.01'))} over {len(amounts)} invoices)."
            ),
        )
    ]


def _detect_near_duplicate(db: Any, *, invoice: Any) -> list[AnomalyFlag]:
    from app.services.invoice_embedding import find_similar_invoices

    threshold = float(Decimal(settings.near_duplicate_similarity_threshold))
    # Returns [] when the invoice has no embedding yet (e.g. embedding failed),
    # which safely disables this check for the run.
    similar = find_similar_invoices(db, invoice=invoice, limit=1)
    if not similar or similar[0].similarity < threshold:
        return []

    match = similar[0]
    return [
        AnomalyFlag(
            rule_code="near_duplicate_similarity",
            message=(
                f"Invoice content is nearly identical to invoice {match.invoice_number} "
                f"(similarity {match.similarity:.4f})."
            ),
        )
    ]


def apply_anomaly_flags(db: Any, *, invoice: Any) -> int:
    """Detect anomalies, persist them as warning validation results, and demote
    a VALIDATION_PASSED invoice to REVIEW_REQUIRED. Commits its own work and
    swallows failures (logging them), mirroring the embedding step's contract.
    Returns the number of flags written."""
    if not settings.anomaly_detection_enabled:
        return 0

    from app.models.audit import AuditLog
    from app.models.invoice import InvoiceValidationResult

    try:
        flags = detect_anomalies(db, invoice=invoice)
        if not flags:
            return 0

        explanations = explain_validation_failures(list(flags))
        for flag in flags:
            explanation, suggested_fix = explanations.get(id(flag), (None, None))
            db.add(
                InvoiceValidationResult(
                    invoice_id=invoice.id,
                    rule_code=flag.rule_code,
                    severity=flag.severity,
                    message=flag.message,
                    passed=flag.passed,
                    explanation=explanation,
                    suggested_fix=suggested_fix,
                )
            )
            anomaly_event = invoice_anomaly_flagged_event(
                invoice_id=invoice.id,
                actor_id=invoice.uploaded_by,
                rule_code=flag.rule_code,
                message=flag.message,
            )
            db.add(
                AuditLog(
                    organization_id=invoice.organization_id,
                    actor_user_id=anomaly_event.actor_id,
                    entity_type=anomaly_event.entity_type,
                    entity_id=anomaly_event.entity_id,
                    action=anomaly_event.action,
                    event_metadata=anomaly_event.metadata,
                )
            )

        from app.core.metrics import ANOMALIES_FLAGGED

        for flag in flags:
            ANOMALIES_FLAGGED.labels(flag.rule_code).inc()

        status_changed = False
        previous_status = InvoiceStatus(invoice.status)
        if previous_status == InvoiceStatus.VALIDATION_PASSED:
            invoice.status = transition_invoice_status(previous_status, InvoiceStatus.REVIEW_REQUIRED).value
            status_event = invoice_status_changed_event(
                invoice_id=invoice.id,
                actor_id=invoice.uploaded_by,
                previous_status=previous_status,
                status=InvoiceStatus(invoice.status),
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
            status_changed = True

        db.commit()
        if status_changed:
            publish_event(
                invoice.organization_id,
                {
                    "type": "invoice.status_changed",
                    "invoice_id": str(invoice.id),
                    "status": invoice.status,
                },
            )
        logger.info(
            "invoice_anomaly.flagged",
            invoice_id=str(invoice.id),
            rule_codes=[flag.rule_code for flag in flags],
        )
        return len(flags)
    except Exception as exc:
        db.rollback()
        logger.warning(
            "invoice_anomaly.failed",
            invoice_id=str(invoice.id),
            error_message=str(exc),
        )
        return 0
