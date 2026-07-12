"""PromptVersion model: a versioned extraction prompt + its expected JSON
schema, so extractions are reproducible and traceable to a specific version."""

from uuid import UUID, uuid4

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin


class PromptVersion(TimestampMixin, Base):
    __tablename__ = "prompt_versions"
    # Each (name, version) pair is registered exactly once so a version label
    # unambiguously identifies one prompt template.
    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompt_versions_name_version"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON schema the model output is expected to conform to for this version.
    json_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Only active versions are selected for new extractions; retired ones are
    # kept for auditing past runs rather than deleted.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    extractions: Mapped[list["InvoiceExtraction"]] = relationship(back_populates="prompt_version_record")
