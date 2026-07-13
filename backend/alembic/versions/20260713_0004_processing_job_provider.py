"""add processing job extraction provider

Revision ID: 20260713_0004
Revises: 20260711_0003
Create Date: 2026-07-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260713_0004"
down_revision: str | None = "20260711_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable so existing jobs keep working; null means "use the server default".
    op.add_column("processing_jobs", sa.Column("provider", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("processing_jobs", "provider")
