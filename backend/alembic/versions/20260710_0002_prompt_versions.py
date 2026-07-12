"""add prompt versions

Revision ID: 20260710_0002
Revises: 20260710_0001
Create Date: 2026-07-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260710_0002"
down_revision: str | None = "20260710_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("json_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_prompt_versions_name_version"),
    )
    op.add_column(
        "invoice_extractions",
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_invoice_extractions_prompt_version_id",
        "invoice_extractions",
        "prompt_versions",
        ["prompt_version_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_invoice_extractions_prompt_version_id",
        "invoice_extractions",
        type_="foreignkey",
    )
    op.drop_column("invoice_extractions", "prompt_version_id")
    op.drop_table("prompt_versions")
