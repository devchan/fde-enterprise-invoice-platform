"""add invoice embeddings table with pgvector

Revision ID: 20260717_0005
Revises: 20260713_0004
Create Date: 2026-07-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260717_0005"
down_revision: str | None = "20260713_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Matches OpenAI text-embedding-3-small; the dev fallback pads to this width.
EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    # The vector type ships as a Postgres extension (available in the
    # pgvector/pgvector image); IF NOT EXISTS keeps re-runs harmless.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "invoice_embeddings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("invoice_id", sa.Uuid(), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("invoice_id", name="uq_invoice_embedding_invoice"),
    )
    # HNSW gives fast approximate nearest-neighbour search that stays accurate
    # as rows grow, without ivfflat's requirement to train on existing data.
    op.execute(
        "CREATE INDEX ix_invoice_embeddings_embedding_hnsw "
        "ON invoice_embeddings USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_table("invoice_embeddings")
    # The extension is left installed on downgrade: other objects may use it and
    # dropping it would require superuser rights the app role may not have.
