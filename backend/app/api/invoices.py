"""Invoice HTTP API: intake (metadata-only and file upload), retrieval, review,
status transitions, and signed file downloads.

Route handlers stay thin — they translate request/response models and map
service-layer exceptions onto the platform's error envelope, while all business
logic lives in app.services.invoice_*.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_roles
from app.api.errors import api_error, conflict_error
from app.db.session import get_db
from app.models.user import User
from app.schemas.invoice import (
    InvoiceCreateRequest,
    InvoiceCreateResponse,
    InvoiceDetailResponse,
    InvoiceExtractionResponse,
    InvoiceFileDownloadUrlResponse,
    InvoiceFileResponse,
    InvoiceLineItemResponse,
    InvoiceListResponse,
    InvoiceReviewRequest,
    InvoiceReviewResponse,
    InvoiceStatusTransitionRequest,
    InvoiceStatusTransitionResponse,
    InvoiceValidationResultResponse,
)
from app.services.file_storage import InvoiceFileStorageError, read_invoice_file
from app.services.file_validation import InvalidInvoiceFileError
from app.services.invoice_file_access import (
    InvoiceFileNotFoundError,
    InvoiceFileSignatureError,
    get_invoice_file_for_organization,
    get_invoice_file_for_signed_download,
    sign_invoice_file_download,
)
from app.services.invoice_intake import (
    DuplicateInvoiceError,
    DuplicateInvoiceUploadError,
    InvoiceIntakePayload,
    InvoiceNotFoundError,
    InvoiceUploadPayload,
    SupplierNotFoundError,
    change_invoice_status,
    create_invoice_metadata,
    create_invoice_upload,
)
from app.services.invoice_review import (
    InvoiceReviewConflictError,
    InvoiceReviewError,
    InvoiceReviewPayload,
    get_invoice_detail,
    list_invoices,
    submit_invoice_review,
)
from app.services.invoice_workflow import InvoiceStatus

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("", response_model=InvoiceListResponse)
def list_invoice_records(
    # `status` is exposed as the query param but bound to status_filter to avoid
    # shadowing the imported fastapi `status` module used for HTTP codes.
    status_filter: InvoiceStatus | None = Query(default=None, alias="status"),
    review_queue: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InvoiceListResponse:
    return InvoiceListResponse(
        invoices=[
            _to_detail_response(invoice)
            for invoice in list_invoices(
                db,
                organization_id=current_user.organization_id,
                status=status_filter,
                review_queue=review_queue,
                limit=limit,
            )
        ]
    )


# Metadata-only intake: records an invoice without a file (and without queuing
# extraction). The file-bearing counterpart is the /upload endpoint below.
@router.post("", response_model=InvoiceCreateResponse, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreateRequest,
    db: Session = Depends(get_db),
    # Creating invoices is limited to admins and uploaders.
    current_user: User = Depends(require_roles("admin", "uploader")),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> InvoiceCreateResponse:
    try:
        result = create_invoice_metadata(
            db,
            InvoiceIntakePayload(
                # Tenant and actor are always taken from the authenticated user,
                # never from client input, to prevent cross-organization writes.
                organization_id=current_user.organization_id,
                supplier_id=payload.supplier_id,
                uploaded_by=current_user.id,
                invoice_number=payload.invoice_number,
                total_amount=payload.total_amount,
                currency=payload.currency,
            ),
            request_id=request_id,
        )
    except DuplicateInvoiceError as exc:
        raise conflict_error(
            "invoice_duplicate",
            str(exc),
            request_id=request_id,
        ) from exc
    except SupplierNotFoundError as exc:
        raise api_error(
            http_status=status.HTTP_404_NOT_FOUND,
            code="supplier_not_found",
            message=str(exc),
            request_id=request_id,
        ) from exc

    return InvoiceCreateResponse(
        invoice_id=result.invoice_id,
        organization_id=result.organization_id,
        supplier_id=result.supplier_id,
        invoice_number=result.invoice_number,
        status=result.status,
        message="Invoice metadata persisted. File upload and queueing will be added in the processing milestone.",
        storage_key=result.storage_key,
        processing_job_id=result.processing_job.processing_job_id if result.processing_job else None,
    )


# Full intake: stores the uploaded file, persists metadata, and queues the
# extraction job. This is the endpoint the rate limiter guards (see rate_limit).
@router.post("/upload", response_model=InvoiceCreateResponse, status_code=status.HTTP_201_CREATED)
async def upload_invoice(
    invoice_number: str = Form(...),
    file: UploadFile = File(...),
    # organization_id/uploaded_by are accepted as form fields for backward
    # compatibility but deliberately ignored below in favor of the authenticated
    # user's identity — a client cannot upload on behalf of another tenant/user.
    organization_id: UUID | None = Form(default=None),
    uploaded_by: UUID | None = Form(default=None),
    supplier_id: UUID | None = Form(default=None),
    total_amount: Decimal | None = Form(default=None),
    currency: str = Form(default="USD", min_length=3, max_length=3),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "uploader")),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> InvoiceCreateResponse:
    try:
        # Read the whole upload into memory once; downstream validation and
        # storage both need the raw bytes (and the checksum computed from them).
        content = await file.read()
        result = create_invoice_upload(
            db,
            InvoiceUploadPayload(
                # Identity comes from the token, not the ignored form fields above.
                organization_id=current_user.organization_id,
                supplier_id=supplier_id,
                uploaded_by=current_user.id,
                invoice_number=invoice_number,
                total_amount=total_amount,
                currency=currency,
                filename=file.filename or "",
                mime_type=file.content_type,
                content=content,
            ),
            request_id=request_id,
        )
    except InvalidInvoiceFileError as exc:
        raise api_error(
            http_status=status.HTTP_400_BAD_REQUEST,
            code="invoice_file_invalid",
            message=str(exc),
            request_id=request_id,
        ) from exc
    except DuplicateInvoiceUploadError as exc:
        raise conflict_error(
            "invoice_file_duplicate",
            str(exc),
            request_id=request_id,
        ) from exc
    except DuplicateInvoiceError as exc:
        raise conflict_error(
            "invoice_duplicate",
            str(exc),
            request_id=request_id,
        ) from exc
    except SupplierNotFoundError as exc:
        raise api_error(
            http_status=status.HTTP_404_NOT_FOUND,
            code="supplier_not_found",
            message=str(exc),
            request_id=request_id,
        ) from exc

    return InvoiceCreateResponse(
        invoice_id=result.invoice_id,
        organization_id=result.organization_id,
        supplier_id=result.supplier_id,
        invoice_number=result.invoice_number,
        status=result.status,
        message="Invoice file stored, metadata persisted, and extraction job queued.",
        storage_key=result.storage_key,
        processing_job_id=result.processing_job.processing_job_id if result.processing_job else None,
    )


# Two-step download: this authenticated endpoint mints a short-lived, HMAC-signed
# URL, and the /download endpoint below serves the bytes for that URL. Splitting
# them lets the actual file fetch be authorized by the signature alone, so the
# link can be handed to a browser/<img> tag without exposing the auth token.
@router.get(
    "/{invoice_id}/files/{file_id}/download-url",
    response_model=InvoiceFileDownloadUrlResponse,
)
def create_invoice_file_download_url(
    invoice_id: UUID,
    file_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> InvoiceFileDownloadUrlResponse:
    try:
        invoice_file = get_invoice_file_for_organization(
            db,
            invoice_id=invoice_id,
            file_id=file_id,
            organization_id=current_user.organization_id,
        )
    except InvoiceFileNotFoundError as exc:
        raise api_error(
            http_status=status.HTTP_404_NOT_FOUND,
            code="invoice_file_not_found",
            message=str(exc),
            details={"invoice_id": str(invoice_id), "file_id": str(file_id)},
            request_id=request_id,
        ) from exc

    # Sign against the resolved storage_key (not just the ids) so a tampered or
    # mismatched key cannot be smuggled into the download endpoint.
    signed_download = sign_invoice_file_download(
        invoice_id=invoice_id,
        file_id=file_id,
        storage_key=invoice_file.storage_key,
    )
    # Build an absolute URL to download_invoice_file with expiry+signature baked
    # into the query string; url_for resolves the route by its function name.
    download_url = str(
        request.url_for(
            "download_invoice_file",
            invoice_id=str(invoice_id),
            file_id=str(file_id),
        ).include_query_params(
            expires_at=signed_download.expires_at,
            signature=signed_download.signature,
        )
    )
    return InvoiceFileDownloadUrlResponse(
        file_id=file_id,
        download_url=download_url,
        expires_at=datetime.fromtimestamp(signed_download.expires_at, UTC),
    )


# Note: no auth dependency here — the request is authorized purely by the valid,
# unexpired signature minted above, which is why the signed key check matters.
@router.get("/{invoice_id}/files/{file_id}/download")
def download_invoice_file(
    invoice_id: UUID,
    file_id: UUID,
    expires_at: int = Query(...),
    signature: str = Query(...),
    db: Session = Depends(get_db),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> Response:
    try:
        invoice_file = get_invoice_file_for_signed_download(
            db,
            invoice_id=invoice_id,
            file_id=file_id,
            expires_at=expires_at,
            signature=signature,
        )
        file_bytes = read_invoice_file(storage_key=invoice_file.storage_key)
    except InvoiceFileNotFoundError as exc:
        raise api_error(
            http_status=status.HTTP_404_NOT_FOUND,
            code="invoice_file_not_found",
            message=str(exc),
            details={"invoice_id": str(invoice_id), "file_id": str(file_id)},
            request_id=request_id,
        ) from exc
    except InvoiceFileSignatureError as exc:
        raise api_error(
            http_status=status.HTTP_403_FORBIDDEN,
            code="invoice_file_download_invalid",
            message=str(exc),
            request_id=request_id,
        ) from exc
    except InvoiceFileStorageError as exc:
        raise api_error(
            http_status=status.HTTP_404_NOT_FOUND,
            code="invoice_file_storage_missing",
            message=str(exc),
            details={"invoice_id": str(invoice_id), "file_id": str(file_id)},
            request_id=request_id,
        ) from exc

    return Response(
        content=file_bytes,
        media_type=invoice_file.mime_type,
        headers={"Content-Disposition": 'attachment; filename="invoice-file"'},
    )


@router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
def get_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> InvoiceDetailResponse:
    try:
        invoice = get_invoice_detail(
            db,
            invoice_id,
            organization_id=current_user.organization_id,
        )
    except InvoiceNotFoundError as exc:
        raise api_error(
            http_status=status.HTTP_404_NOT_FOUND,
            code="invoice_not_found",
            message=str(exc),
            details={"invoice_id": str(invoice_id)},
            request_id=request_id,
        ) from exc

    return _to_detail_response(invoice)


@router.post("/{invoice_id}/review", response_model=InvoiceDetailResponse)
def review_invoice(
    invoice_id: UUID,
    payload: InvoiceReviewRequest,
    db: Session = Depends(get_db),
    # Reviewing (approve/reject/correct) is limited to admins and reviewers.
    current_user: User = Depends(require_roles("admin", "reviewer")),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> InvoiceDetailResponse:
    try:
        invoice = submit_invoice_review(
            db,
            invoice_id=invoice_id,
            organization_id=current_user.organization_id,
            payload=InvoiceReviewPayload(
                reviewer_id=current_user.id,
                decision=payload.decision,
                notes=payload.notes,
                corrected_fields=payload.corrected_fields,
                # Optimistic-concurrency token: the service rejects the review
                # (InvoiceReviewConflictError) if the invoice changed since the
                # client loaded it, preventing lost updates between reviewers.
                expected_updated_at=payload.expected_updated_at,
            ),
            request_id=request_id,
        )
    except InvoiceNotFoundError as exc:
        raise api_error(
            http_status=status.HTTP_404_NOT_FOUND,
            code="invoice_not_found",
            message=str(exc),
            details={"invoice_id": str(invoice_id)},
            request_id=request_id,
        ) from exc
    except InvoiceReviewConflictError as exc:
        raise conflict_error(
            "invoice_review_conflict",
            str(exc),
            request_id=request_id,
        ) from exc
    except DuplicateInvoiceError as exc:
        raise conflict_error(
            "invoice_duplicate",
            str(exc),
            request_id=request_id,
        ) from exc
    except InvoiceReviewError as exc:
        raise conflict_error(
            "invoice_review_invalid",
            str(exc),
            request_id=request_id,
        ) from exc

    return _to_detail_response(invoice)


@router.post("/{invoice_id}/status", response_model=InvoiceStatusTransitionResponse)
def transition_invoice(
    invoice_id: UUID,
    payload: InvoiceStatusTransitionRequest,
    db: Session = Depends(get_db),
    # Direct status overrides bypass the normal workflow, so they're admin-only.
    current_user: User = Depends(require_roles("admin")),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> InvoiceStatusTransitionResponse:
    try:
        result = change_invoice_status(
            db,
            invoice_id=invoice_id,
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
            requested_status=payload.requested_status,
            request_id=request_id,
        )
    except InvoiceNotFoundError as exc:
        raise api_error(
            http_status=status.HTTP_404_NOT_FOUND,
            code="invoice_not_found",
            message=str(exc),
            details={"invoice_id": str(invoice_id)},
            request_id=request_id,
        ) from exc
    except ValueError as exc:
        # Illegal transitions surface from the workflow as ValueError; map to 409.
        raise conflict_error(
            "invoice_status_transition_invalid",
            str(exc),
            request_id=request_id,
        ) from exc

    return InvoiceStatusTransitionResponse(
        invoice_id=result.invoice_id,
        organization_id=result.organization_id,
        supplier_id=result.supplier_id,
        invoice_number=result.invoice_number,
        status=result.status,
    )


# Shared serializer that flattens an Invoice ORM row (plus its related files,
# line items, extractions, validation results, and reviews) into the API model.
def _to_detail_response(invoice) -> InvoiceDetailResponse:
    # An invoice may accumulate several extraction attempts (e.g. reprocessing);
    # expose only the most recent one as the "current" extraction.
    latest_extraction = (
        max(invoice.extractions, key=lambda extraction: extraction.created_at)
        if invoice.extractions
        else None
    )
    return InvoiceDetailResponse(
        invoice_id=invoice.id,
        organization_id=invoice.organization_id,
        supplier_id=invoice.supplier_id,
        uploaded_by=invoice.uploaded_by,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        total_amount=invoice.total_amount,
        currency=invoice.currency,
        status=InvoiceStatus(invoice.status),
        file_checksum=invoice.file_checksum,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        files=[
            InvoiceFileResponse(
                file_id=file.id,
                storage_key=file.storage_key,
                mime_type=file.mime_type,
                file_size=file.file_size,
            )
            for file in invoice.files
        ],
        line_items=[
            InvoiceLineItemResponse(
                line_item_id=item.id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
            )
            for item in invoice.line_items
        ],
        latest_extraction=_to_extraction_response(latest_extraction),
        validation_results=[
            InvoiceValidationResultResponse(
                validation_result_id=result.id,
                rule_code=result.rule_code,
                severity=result.severity,
                message=result.message,
                passed=result.passed,
            )
            for result in invoice.validation_results
        ],
        reviews=[
            InvoiceReviewResponse(
                review_id=review.id,
                reviewer_id=review.reviewer_id,
                decision=review.decision,
                notes=review.notes,
                corrected_fields=review.corrected_fields,
                created_at=review.created_at,
            )
            for review in invoice.reviews
        ],
    )


def _to_extraction_response(extraction) -> InvoiceExtractionResponse | None:
    if extraction is None:
        return None

    return InvoiceExtractionResponse(
        extraction_id=extraction.id,
        model_name=extraction.model_name,
        prompt_version=extraction.prompt_version,
        confidence_score=extraction.confidence_score,
        input_tokens=extraction.input_tokens,
        output_tokens=extraction.output_tokens,
        estimated_cost=extraction.estimated_cost,
        extracted_payload=extraction.extracted_payload,
    )
