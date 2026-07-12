"""User model: an authenticated member of an organization."""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    # Indexed because login looks users up by email on every authentication.
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Free-form RBAC role string (e.g. admin/reviewer); checked by require_roles.
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    # Nullable so externally-provisioned users (e.g. SSO) can exist without a
    # local password; verify_password treats a null hash as a failed login.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="users")
    uploaded_invoices: Mapped[list["Invoice"]] = relationship(back_populates="uploaded_by_user")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="actor")
