from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AuditLogEntryResponse(BaseModel):
    audit_log_id: UUID
    organization_id: UUID
    actor_user_id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    metadata: dict[str, Any]
    request_id: str | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    audit_logs: list[AuditLogEntryResponse] = Field(default_factory=list)
