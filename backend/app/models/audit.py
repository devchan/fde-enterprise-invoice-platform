from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, String, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin


class AuditLogAppendOnlyError(RuntimeError):
    pass


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_organization_id", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(100))

    organization: Mapped["Organization"] = relationship(back_populates="audit_logs")
    actor: Mapped["User"] = relationship(back_populates="audit_logs")


def _raise_append_only_error(*_args) -> None:
    raise AuditLogAppendOnlyError("Audit log records are append-only and cannot be modified or deleted.")


event.listen(AuditLog, "before_update", _raise_append_only_error)
event.listen(AuditLog, "before_delete", _raise_append_only_error)
