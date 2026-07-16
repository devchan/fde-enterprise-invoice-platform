"""Invoice embeddings: turn extracted invoice fields into a vector via an
embedding model and persist it for pgvector similarity search (similar-invoice
lookup, near-duplicate detection). Ships a deterministic development embedder
so the pipeline runs without an OpenAI API key, mirroring invoice_extraction."""

import hashlib
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.config import settings

# Must match the Vector(...) width on InvoiceEmbedding and the migration; both
# real and development embedders produce vectors of exactly this size.
EMBEDDING_DIMENSIONS = 1536


class EmbeddingError(RuntimeError):
    pass


# Same retry contract as extraction: transient provider failures may be
# retried by callers, anything else is treated as permanent.
class TransientEmbeddingError(EmbeddingError):
    pass


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    model_name: str
    input_tokens: int | None = None
    estimated_cost: Decimal | None = None


def embedding_source_text(*, invoice: Any, payload: Any | None = None) -> str:
    """Canonical text representation of an invoice for embedding.

    Built from extracted fields when available, falling back to the invoice
    row's own values, so semantically similar invoices (same supplier, similar
    line items) land close together in vector space.
    """
    supplier_name = getattr(payload, "supplier_name", None) or (
        invoice.supplier.name if getattr(invoice, "supplier", None) is not None else None
    )
    parts = [
        f"supplier: {supplier_name or 'unknown'}",
        f"invoice number: {getattr(payload, 'invoice_number', None) or invoice.invoice_number}",
        f"currency: {getattr(payload, 'currency', None) or invoice.currency}",
        f"total: {getattr(payload, 'total_amount', None) or invoice.total_amount}",
    ]
    invoice_date = getattr(payload, "invoice_date", None) or invoice.invoice_date
    if invoice_date:
        parts.append(f"date: {invoice_date}")
    for item in getattr(payload, "line_items", None) or []:
        parts.append(
            f"line item: {item.description} x{item.quantity or 1} @ {item.unit_price or ''} = {item.line_total or ''}"
        )
    return "\n".join(parts)


class DevelopmentInvoiceEmbedder:
    # Deterministic stand-in used when no OpenAI key is configured. Hashes each
    # token into a bucket (feature hashing), so invoices sharing supplier/line
    # item words still get measurably similar vectors — enough to exercise the
    # full similarity pipeline locally and in tests.
    model_name = "development-embedder"

    def embed(self, *, text: str) -> EmbeddingResult:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
            # Second hash byte decides sign so buckets don't only accumulate
            # positives, which would make all vectors trivially correlated.
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        return EmbeddingResult(vector=_normalize(vector), model_name=self.model_name)


class OpenAIInvoiceEmbedder:
    def __init__(self, *, api_key: str, model_name: str) -> None:
        self.api_key = api_key
        self.model_name = model_name

    def embed(self, *, text: str) -> EmbeddingResult:
        # Import lazily so the OpenAI SDK stays an optional dependency, matching
        # the extractor.
        try:
            from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
        except ImportError as exc:
            raise EmbeddingError("OpenAI SDK is not installed.") from exc

        client = OpenAI(api_key=self.api_key)
        try:
            response = client.embeddings.create(
                model=self.model_name,
                input=text,
                # Pin the dimension so a future model default can't silently
                # disagree with the database column width.
                dimensions=EMBEDDING_DIMENSIONS,
            )
        except RateLimitError as exc:
            # insufficient_quota arrives as a 429 but is permanent until billing
            # is fixed (same handling as extraction).
            code = getattr(exc, "code", None)
            if code == "insufficient_quota" or "insufficient_quota" in str(exc):
                raise EmbeddingError("OpenAI embedding failed: account quota exhausted.") from exc
            raise TransientEmbeddingError("OpenAI embedding failed due to a transient provider error.") from exc
        except (APITimeoutError, APIConnectionError) as exc:
            raise TransientEmbeddingError("OpenAI embedding failed due to a transient provider error.") from exc
        except Exception as exc:
            raise EmbeddingError("OpenAI embedding failed.") from exc

        input_tokens = getattr(getattr(response, "usage", None), "prompt_tokens", None)
        return EmbeddingResult(
            vector=list(response.data[0].embedding),
            model_name=self.model_name,
            input_tokens=input_tokens,
            estimated_cost=_estimate_embedding_cost(input_tokens),
        )


def build_invoice_embedder():
    # OpenAI when configured, otherwise the deterministic dev embedder so the
    # pipeline always runs (mirrors build_invoice_extractor's fallback).
    if settings.openai_api_key:
        return OpenAIInvoiceEmbedder(
            api_key=settings.openai_api_key,
            model_name=settings.openai_embedding_model,
        )
    return DevelopmentInvoiceEmbedder()


def persist_invoice_embedding(db: Any, *, invoice: Any, source_text: str, result: EmbeddingResult):
    from sqlalchemy import select

    from app.models.invoice import InvoiceEmbedding

    # One embedding per invoice: re-extraction updates the row in place instead
    # of appending, so similarity search never sees stale duplicates.
    embedding = db.scalar(select(InvoiceEmbedding).where(InvoiceEmbedding.invoice_id == invoice.id))
    if embedding is None:
        embedding = InvoiceEmbedding(invoice_id=invoice.id)
        db.add(embedding)

    embedding.model_name = result.model_name
    embedding.source_text = source_text
    embedding.embedding = result.vector
    embedding.input_tokens = result.input_tokens
    embedding.estimated_cost = result.estimated_cost
    db.flush()
    return embedding


@dataclass(frozen=True)
class SimilarInvoice:
    invoice_id: UUID
    invoice_number: str
    supplier_id: UUID | None
    status: str
    total_amount: Decimal | None
    currency: str
    # 1.0 = identical direction, 0.0 = orthogonal; derived from cosine distance.
    similarity: float


def find_similar_invoices(db: Any, *, invoice: Any, limit: int | None = None) -> list[SimilarInvoice]:
    """Nearest invoices (by embedding cosine distance) within the same
    organization, excluding the invoice itself. Empty when the invoice has no
    embedding yet (i.e. extraction has not completed)."""
    from sqlalchemy import select

    from app.models.invoice import Invoice, InvoiceEmbedding

    limit = limit or settings.invoice_similarity_result_limit
    own = db.scalar(select(InvoiceEmbedding).where(InvoiceEmbedding.invoice_id == invoice.id))
    if own is None:
        return []

    if db.get_bind().dialect.name == "postgresql":
        # pgvector's <=> operator: cosine distance, served by the HNSW index.
        distance = InvoiceEmbedding.embedding.cosine_distance(own.embedding)
        rows = db.execute(
            select(Invoice, distance.label("distance"))
            .join(InvoiceEmbedding, InvoiceEmbedding.invoice_id == Invoice.id)
            .where(
                Invoice.organization_id == invoice.organization_id,
                Invoice.id != invoice.id,
            )
            .order_by(distance)
            .limit(limit)
        ).all()
        scored = [(row.Invoice, 1.0 - float(row.distance)) for row in rows]
    else:
        # Non-Postgres fallback (unit tests / future backends): same ranking
        # computed in Python over the organization's embeddings.
        candidates = db.execute(
            select(Invoice, InvoiceEmbedding)
            .join(InvoiceEmbedding, InvoiceEmbedding.invoice_id == Invoice.id)
            .where(
                Invoice.organization_id == invoice.organization_id,
                Invoice.id != invoice.id,
            )
        ).all()
        scored = sorted(
            ((row.Invoice, cosine_similarity(own.embedding, row.InvoiceEmbedding.embedding)) for row in candidates),
            key=lambda pair: pair[1],
            reverse=True,
        )[:limit]

    return [
        SimilarInvoice(
            invoice_id=candidate.id,
            invoice_number=candidate.invoice_number,
            supplier_id=candidate.supplier_id,
            status=candidate.status,
            total_amount=candidate.total_amount,
            currency=candidate.currency,
            similarity=round(similarity, 6),
        )
        for candidate, similarity in scored
    ]


def cosine_similarity(a: Any, b: Any) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def _estimate_embedding_cost(input_tokens: int | None) -> Decimal | None:
    if input_tokens is None:
        return None
    rate = Decimal(settings.openai_embedding_cost_per_million_tokens)
    return (Decimal(input_tokens) * rate / Decimal("1000000")).quantize(Decimal("0.000001"))
