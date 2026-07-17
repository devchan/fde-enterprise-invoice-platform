"""Extraction accuracy analytics derived from reviewer corrections.

Every human review is a free ground-truth label: a field the reviewer
corrected is a field the extractor got wrong, and a field left untouched on a
reviewed invoice is (approximately) one it got right. Aggregating corrections
per field and per prompt version answers the question every prompt/model
change raises — "did extraction actually get better?" — without a separate
eval pipeline.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.invoice import Invoice, InvoiceExtraction, InvoiceReview

# Fields whose corrections we attribute to extraction quality. line_items is
# tracked as a single unit — any line-item edit counts as one correction.
TRACKED_FIELDS = ("invoice_number", "invoice_date", "total_amount", "currency", "line_items")


@dataclass(frozen=True)
class FieldAccuracy:
    field: str
    reviewed_count: int
    corrected_count: int

    @property
    def accuracy(self) -> float | None:
        if self.reviewed_count == 0:
            return None
        return round(1.0 - (self.corrected_count / self.reviewed_count), 4)


@dataclass(frozen=True)
class PromptVersionAccuracy:
    prompt_version: str
    model_names: list[str]
    reviewed_invoices: int
    fields: list[FieldAccuracy]


def extraction_accuracy_report(db: Session, *, organization_id: UUID) -> list[PromptVersionAccuracy]:
    """Per-prompt-version field accuracy for one organization's reviewed
    invoices. Each review is paired with the newest extraction that preceded
    it, so a correction is always attributed to the prompt/model that actually
    produced the value the reviewer fixed."""
    rows = db.execute(
        select(InvoiceReview, Invoice)
        .join(Invoice, Invoice.id == InvoiceReview.invoice_id)
        .where(Invoice.organization_id == organization_id)
    ).all()
    if not rows:
        return []

    invoice_ids = {row.Invoice.id for row in rows}
    extractions = list(
        db.scalars(
            select(InvoiceExtraction)
            .where(InvoiceExtraction.invoice_id.in_(invoice_ids))
            .order_by(InvoiceExtraction.created_at)
        )
    )
    extractions_by_invoice: dict[UUID, list[InvoiceExtraction]] = {}
    for extraction in extractions:
        extractions_by_invoice.setdefault(extraction.invoice_id, []).append(extraction)

    # (prompt_version) -> aggregation buckets
    reviewed: dict[str, int] = {}
    corrected: dict[str, dict[str, int]] = {}
    models: dict[str, set[str]] = {}

    for row in rows:
        review, invoice = row.InvoiceReview, row.Invoice
        extraction = _extraction_for_review(extractions_by_invoice.get(invoice.id, []), review)
        if extraction is None:
            # Metadata-only invoices reviewed without any extraction say nothing
            # about extraction quality.
            continue
        version = extraction.prompt_version
        reviewed[version] = reviewed.get(version, 0) + 1
        models.setdefault(version, set()).add(extraction.model_name)
        corrected.setdefault(version, dict.fromkeys(TRACKED_FIELDS, 0))
        for field in _corrected_tracked_fields(review):
            corrected[version][field] += 1

    return [
        PromptVersionAccuracy(
            prompt_version=version,
            model_names=sorted(models[version]),
            reviewed_invoices=reviewed[version],
            fields=[
                FieldAccuracy(
                    field=field,
                    reviewed_count=reviewed[version],
                    corrected_count=corrected[version][field],
                )
                for field in TRACKED_FIELDS
            ],
        )
        for version in sorted(reviewed)
    ]


def _extraction_for_review(extractions: list[Any], review: Any) -> Any | None:
    # The newest extraction created at/before the review; falls back to the
    # newest overall to tolerate clock-identical timestamps in tests.
    prior = [extraction for extraction in extractions if extraction.created_at <= review.created_at]
    if prior:
        return prior[-1]
    return extractions[-1] if extractions else None


def _corrected_tracked_fields(review: Any) -> list[str]:
    corrected_fields = review.corrected_fields or {}
    return [field for field in TRACKED_FIELDS if field in corrected_fields]
