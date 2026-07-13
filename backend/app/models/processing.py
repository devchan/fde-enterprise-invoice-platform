"""ProcessingJob model: an async unit of work (extraction, validation, etc.)
queued against an invoice and drained by the background worker."""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin


class ProcessingJob(TimestampMixin, Base):
    __tablename__ = "processing_jobs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Indexed so the worker can cheaply poll for queued/failed jobs to run.
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued", index=True)
    # Retry bookkeeping: attempt count and the most recent failure message.
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    # Extraction provider chosen at upload (e.g. "openai"/"gemini"); null lets the
    # worker fall back to the server default.
    provider: Mapped[str | None] = mapped_column(String(50))

    invoice: Mapped["Invoice"] = relationship(back_populates="processing_jobs")
