from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"
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
    supplier_id: Mapped[UUID | None] = mapped_column(ForeignKey("suppliers.id"))
    uploaded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded", index=True)
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


class InvoiceFile(TimestampMixin, Base):
    __tablename__ = "invoice_files"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
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

    invoice: Mapped[Invoice] = relationship(back_populates="line_items")


class InvoiceExtraction(TimestampMixin, Base):
    __tablename__ = "invoice_extractions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    prompt_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("prompt_versions.id"))
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    extracted_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))

    invoice: Mapped[Invoice] = relationship(back_populates="extractions")
    prompt_version_record: Mapped["PromptVersion | None"] = relationship(back_populates="extractions")


class InvoiceValidationResult(TimestampMixin, Base):
    __tablename__ = "invoice_validation_results"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool] = mapped_column(nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="validation_results")


class InvoiceReview(TimestampMixin, Base):
    __tablename__ = "invoice_reviews"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    corrected_fields: Mapped[dict | None] = mapped_column(JSONB)

    invoice: Mapped[Invoice] = relationship(back_populates="reviews")
