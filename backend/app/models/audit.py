"""AuditLog model: an append-only record of security-relevant actions.

Rows are immutable — ORM update/delete are blocked by event listeners below —
so the trail cannot be tampered with after the fact."""

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
    # Indexes support the two common audit queries: "all events for this
    # entity" and "all events for this organization".
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
    # Attribute is event_metadata (SQLAlchemy reserves `metadata`), but the DB
    # column is named "metadata"; holds arbitrary structured event context.
    event_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    # Correlates the entry with the originating HTTP request for tracing.
    request_id: Mapped[str | None] = mapped_column(String(100))

    organization: Mapped["Organization"] = relationship(back_populates="audit_logs")
    actor: Mapped["User"] = relationship(back_populates="audit_logs")


def _raise_append_only_error(*_args) -> None:
    raise AuditLogAppendOnlyError("Audit log records are append-only and cannot be modified or deleted.")


# Enforce immutability at the ORM layer: any attempt to update or delete an
# audit row raises instead of silently mutating the trail.
event.listen(AuditLog, "before_update", _raise_append_only_error)
event.listen(AuditLog, "before_delete", _raise_append_only_error)
