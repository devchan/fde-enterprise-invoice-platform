from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogEntryResponse, AuditLogListResponse

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    entity_type: str | None = Query(default=None, min_length=1, max_length=100),
    entity_id: UUID | None = Query(default=None),
    action: str | None = Query(default=None, min_length=1, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AuditLogListResponse:
    query = select(AuditLog).where(AuditLog.organization_id == current_user.organization_id)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if action:
        query = query.where(AuditLog.action == action)

    rows = db.scalars(query.order_by(AuditLog.created_at.desc()).limit(limit))
    return AuditLogListResponse(audit_logs=[_to_response(row) for row in rows])


def _to_response(row: AuditLog) -> AuditLogEntryResponse:
    return AuditLogEntryResponse(
        audit_log_id=row.id,
        organization_id=row.organization_id,
        actor_user_id=row.actor_user_id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        action=row.action,
        metadata=row.event_metadata or {},
        request_id=row.request_id,
        created_at=row.created_at,
    )
