"""Shared ORM building blocks mixed into every table model."""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    # Timestamps are set by the database (server_default/onupdate) rather than
    # in Python so they stay consistent regardless of which app instance or
    # migration writes the row. Stored timezone-aware (UTC) to avoid ambiguity.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

