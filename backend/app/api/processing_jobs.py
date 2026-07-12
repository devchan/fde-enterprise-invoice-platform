from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from redis import Redis
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_roles
from app.api.errors import api_error, conflict_error
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.processing import (
    FailedProcessingJobsResponse,
    ProcessingJobReprocessRequest,
    ProcessingJobResponse,
)
from app.services.processing_jobs import (
    ProcessingJobError,
    get_processing_job_for_organization,
    list_failed_processing_jobs_for_organization,
    requeue_processing_job,
)

router = APIRouter(prefix="/processing-jobs", tags=["processing-jobs"])


@router.get("/failed", response_model=FailedProcessingJobsResponse)
def list_failed_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FailedProcessingJobsResponse:
    return FailedProcessingJobsResponse(
        jobs=[
            _to_response(job)
            for job in list_failed_processing_jobs_for_organization(
                db,
                organization_id=current_user.organization_id,
                limit=limit,
            )
        ]
    )


@router.get("/{processing_job_id}", response_model=ProcessingJobResponse)
def get_job(
    processing_job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> ProcessingJobResponse:
    try:
        job = get_processing_job_for_organization(
            db,
            processing_job_id,
            organization_id=current_user.organization_id,
        )
    except ProcessingJobError as exc:
        raise api_error(
            http_status=status.HTTP_404_NOT_FOUND,
            code="processing_job_not_found",
            message=str(exc),
            details={"processing_job_id": str(processing_job_id)},
            request_id=request_id,
        ) from exc

    return _to_response(job)


@router.post("/{processing_job_id}/reprocess", response_model=ProcessingJobResponse)
def reprocess_job(
    processing_job_id: UUID,
    payload: ProcessingJobReprocessRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "reviewer")),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> ProcessingJobResponse:
    redis_client = Redis.from_url(settings.redis_url)
    try:
        job = requeue_processing_job(
            db,
            redis_client,
            processing_job_id=processing_job_id,
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
            request_id=request_id,
        )
    except ProcessingJobError as exc:
        raise conflict_error(
            "processing_job_reprocess_invalid",
            str(exc),
            request_id=request_id,
        ) from exc

    return _to_response(job)


def _to_response(job) -> ProcessingJobResponse:
    return ProcessingJobResponse(
        processing_job_id=job.id,
        invoice_id=job.invoice_id,
        job_type=job.job_type,
        status=job.status,
        attempts=job.attempts,
        last_error=job.last_error,
    )
