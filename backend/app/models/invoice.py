"""Invoice model and its child records (files, line items, extractions,
validation results, reviews) that together capture an invoice's lifecycle."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"
    # Guards against ingesting the same invoice twice: a supplier's invoice
    # number must be unique within an organization.
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "supplier_id",
            "invoice_number",
            name="uq_invoice_org_supplier_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    # Nullable: an uploaded invoice may not be matched to a supplier yet.
    supplier_id: Mapped[UUID | None] = mapped_column(ForeignKey("suppliers.id"))
    uploaded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    # Financial fields stay null until extraction populates them from the file.
    invoice_date: Mapped[date | None] = mapped_column(Date)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    # Workflow state (see InvoiceStatus); indexed for status-filtered listings.
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded", index=True)
    # Checksum of the uploaded file, indexed to detect duplicate uploads.
    file_checksum: Mapped[str | None] = mapped_column(String(128), index=True)

    organization: Mapped["Organization"] = relationship(back_populates="invoices")
    supplier: Mapped["Supplier | None"] = relationship(back_populates="invoices")
    uploaded_by_user: Mapped["User"] = relationship(back_populates="uploaded_invoices")
    files: Mapped[list["InvoiceFile"]] = relationship(back_populates="invoice")
    line_items: Mapped[list["InvoiceLineItem"]] = relationship(back_populates="invoice")
    extractions: Mapped[list["InvoiceExtraction"]] = relationship(back_populates="invoice")
    validation_results: Mapped[list["InvoiceValidationResult"]] = relationship(back_populates="invoice")
    reviews: Mapped[list["InvoiceReview"]] = relationship(back_populates="invoice")
    processing_jobs: Mapped[list["ProcessingJob"]] = relationship(back_populates="invoice")
    embedding: Mapped["InvoiceEmbedding | None"] = relationship(back_populates="invoice")


# The uploaded document(s) for an invoice. The bytes live in object storage;
# only the pointer (storage_key) and metadata are kept in the database.
class InvoiceFile(TimestampMixin, Base):
    __tablename__ = "invoice_files"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    # Object-storage locator (e.g. S3 key), resolved to bytes on download.
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="files")


class InvoiceLineItem(TimestampMixin, Base):
    __tablename__ = "invoice_line_items"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Expense category assigned by the extractor (see LINE_ITEM_CATEGORIES);
    # null for rows written before categorization or when the model was unsure.
    category: Mapped[str | None] = mapped_column(String(50))

    invoice: Mapped[Invoice] = relationship(back_populates="line_items")


# One row per LLM extraction attempt: the structured payload plus the model,
# prompt version, confidence, and token/cost accounting used to produce it.
class InvoiceExtraction(TimestampMixin, Base):
    __tablename__ = "invoice_extractions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    prompt_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("prompt_versions.id"))
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    # Raw structured output from the model, stored as JSONB for flexible schema.
    extracted_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    # Token counts and estimated cost let us track/attribute LLM spend per run.
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))

    invoice: Mapped[Invoice] = relationship(back_populates="extractions")
    prompt_version_record: Mapped["PromptVersion | None"] = relationship(back_populates="extractions")


# Outcome of a single validation rule against an invoice; `passed` plus
# `severity` drive whether the invoice can advance or needs human review.
class InvoiceValidationResult(TimestampMixin, Base):
    __tablename__ = "invoice_validation_results"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool] = mapped_column(nullable=False)
    # Reviewer-facing guidance for failed rules: why it failed in plain language
    # and what action resolves it. Null for passed rules and legacy rows.
    explanation: Mapped[str | None] = mapped_column(Text)
    suggested_fix: Mapped[str | None] = mapped_column(Text)

    invoice: Mapped[Invoice] = relationship(back_populates="validation_results")


# Semantic fingerprint of an invoice's extracted content, used for
# similar-invoice lookup and near-duplicate detection via pgvector. One row
# per invoice: re-extraction replaces the embedding rather than appending.
class InvoiceEmbedding(TimestampMixin, Base):
    __tablename__ = "invoice_embeddings"
    __table_args__ = (
        UniqueConstraint("invoice_id", name="uq_invoice_embedding_invoice"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # The exact text that was embedded, kept for traceability (mirrors how
    # extractions persist their prompt version) and to allow re-embedding with
    # a different model without re-running extraction.
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Dimension matches OpenAI text-embedding-3-small; the dev fallback embedder
    # pads to the same width so both providers share one column.
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    input_tokens: Mapped[int | None]
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))

    invoice: Mapped[Invoice] = relationship(back_populates="embedding")


# A human reviewer's decision on an invoice, including any field corrections
# they applied (stored as JSONB so the correction shape can vary).
class InvoiceReview(TimestampMixin, Base):
    __tablename__ = "invoice_reviews"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    corrected_fields: Mapped[dict | None] = mapped_column(JSONB)

    invoice: Mapped[Invoice] = relationship(back_populates="reviews")
