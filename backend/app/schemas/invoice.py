"""API request/response schemas for invoice endpoints (upload, listing,
detail, status transitions, and human review)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.invoice_review import ReviewDecision
from app.services.invoice_workflow import InvoiceStatus


class InvoiceCreateRequest(BaseModel):
    # organization_id/uploaded_by are optional here because the API fills them
    # from the authenticated user rather than trusting client-supplied values.
    organization_id: UUID | None = None
    supplier_id: UUID | None = None
    uploaded_by: UUID | None = None
    invoice_number: str = Field(min_length=1, max_length=100)
    total_amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class InvoiceCreateResponse(BaseModel):
    invoice_id: UUID
    organization_id: UUID
    supplier_id: UUID | None
    invoice_number: str
    status: InvoiceStatus
    message: str
    storage_key: str | None = None
    processing_job_id: UUID | None = None


class InvoiceStatusTransitionRequest(BaseModel):
    actor_id: UUID | None = None
    requested_status: InvoiceStatus


class InvoiceStatusTransitionResponse(BaseModel):
    invoice_id: UUID
    organization_id: UUID
    supplier_id: UUID | None
    invoice_number: str
    status: InvoiceStatus


class InvoiceFileResponse(BaseModel):
    file_id: UUID
    storage_key: str
    mime_type: str
    file_size: int


class InvoiceFileDownloadUrlResponse(BaseModel):
    file_id: UUID
    download_url: str
    expires_at: datetime


class InvoiceLineItemResponse(BaseModel):
    line_item_id: UUID
    description: str
    quantity: Decimal | None
    unit_price: Decimal | None
    line_total: Decimal | None
    # AI-assigned expense category (see LINE_ITEM_CATEGORIES); null when the
    # extractor was unsure or the row predates categorization.
    category: str | None = None


class InvoiceExtractionResponse(BaseModel):
    extraction_id: UUID
    model_name: str
    prompt_version: str
    confidence_score: Decimal | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost: Decimal | None
    extracted_payload: dict[str, Any]


class InvoiceValidationResultResponse(BaseModel):
    validation_result_id: UUID
    rule_code: str
    severity: str
    message: str
    passed: bool
    # Reviewer-facing guidance for failed rules; null for passed/legacy rows.
    explanation: str | None = None
    suggested_fix: str | None = None


class InvoiceReviewResponse(BaseModel):
    review_id: UUID
    reviewer_id: UUID
    decision: str
    notes: str | None
    corrected_fields: dict[str, Any] | None
    created_at: datetime


class InvoiceDetailResponse(BaseModel):
    invoice_id: UUID
    organization_id: UUID
    supplier_id: UUID | None
    uploaded_by: UUID
    invoice_number: str
    invoice_date: date | None
    total_amount: Decimal | None
    currency: str
    status: InvoiceStatus
    file_checksum: str | None
    created_at: datetime
    updated_at: datetime
    files: list[InvoiceFileResponse]
    line_items: list[InvoiceLineItemResponse]
    latest_extraction: InvoiceExtractionResponse | None
    validation_results: list[InvoiceValidationResultResponse]
    reviews: list[InvoiceReviewResponse]


class InvoiceListResponse(BaseModel):
    invoices: list[InvoiceDetailResponse]


class SimilarInvoiceResponse(BaseModel):
    invoice_id: UUID
    invoice_number: str
    supplier_id: UUID | None
    status: InvoiceStatus
    total_amount: Decimal | None
    currency: str
    # Cosine similarity of the invoices' embeddings: 1.0 = same content
    # direction, 0.0 = unrelated. Useful for near-duplicate triage in review.
    similarity: float


class SimilarInvoicesResponse(BaseModel):
    invoice_id: UUID
    similar_invoices: list[SimilarInvoiceResponse]


class InvoiceNLSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class InvoiceNLSearchResponse(BaseModel):
    query: str
    # The structured filters the query was translated into, echoed back so the
    # UI can show users how their request was interpreted.
    filters: dict[str, Any]
    invoices: list[InvoiceDetailResponse]


class InvoiceReviewRequest(BaseModel):
    reviewer_id: UUID | None = None
    decision: ReviewDecision
    notes: str | None = None
    corrected_fields: dict[str, Any] = Field(default_factory=dict)
    # Optimistic-concurrency token: if set, the review is rejected when the
    # invoice was modified since the client last read it (lost-update guard).
    expected_updated_at: datetime | None = None
