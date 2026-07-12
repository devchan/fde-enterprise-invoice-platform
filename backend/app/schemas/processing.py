from uuid import UUID

from pydantic import BaseModel, Field

from app.services.processing_jobs import ProcessingJobStatus, ProcessingJobType


class ProcessingJobResponse(BaseModel):
    processing_job_id: UUID
    invoice_id: UUID
    job_type: ProcessingJobType
    status: ProcessingJobStatus
    attempts: int
    last_error: str | None


class ProcessingJobReprocessRequest(BaseModel):
    actor_id: UUID | None = None


class FailedProcessingJobsResponse(BaseModel):
    jobs: list[ProcessingJobResponse] = Field(default_factory=list)
