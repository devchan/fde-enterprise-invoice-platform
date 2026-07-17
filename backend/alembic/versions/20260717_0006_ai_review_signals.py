"""add line item category and validation explanation columns

Revision ID: 20260717_0006
Revises: 20260717_0005
Create Date: 2026-07-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260717_0006"
down_revision: str | None = "20260717_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Expense category assigned during extraction; nullable so existing rows
    # (and models that decline to classify) stay valid.
    op.add_column("invoice_line_items", sa.Column("category", sa.String(length=50), nullable=True))
    # Reviewer-facing guidance for failed validation rules.
    op.add_column("invoice_validation_results", sa.Column("explanation", sa.Text(), nullable=True))
    op.add_column("invoice_validation_results", sa.Column("suggested_fix", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("invoice_validation_results", "suggested_fix")
    op.drop_column("invoice_validation_results", "explanation")
    op.drop_column("invoice_line_items", "category")
