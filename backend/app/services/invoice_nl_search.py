"""Natural-language invoice search.

Translates a reviewer's plain-English query ("unpaid Acme invoices over $10k
from June") into structured filters, then runs those filters as a normal
tenant-scoped SQL query. The LLM only ever produces filter JSON — it never
touches data or SQL — so tenancy and RBAC stay enforced by the API exactly as
for every other listing endpoint. Without an OpenAI key, a deterministic
keyword parser covers the common phrasings so the feature still works in
development.
"""

import calendar
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.invoice import Invoice
from app.models.supplier import Supplier
from app.services.invoice_workflow import InvoiceStatus


class InvoiceSearchFilters(BaseModel):
    """Structured filters an NL query is translated into. Every field is
    optional; unset fields simply don't constrain the query."""

    status: InvoiceStatus | None = None
    supplier_name_contains: str | None = None
    invoice_number_contains: str | None = None
    min_total: Decimal | None = Field(default=None, ge=0)
    max_total: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(default=50, ge=1, le=200)


class NLSearchError(RuntimeError):
    pass


def parse_search_query(query: str, *, today: date | None = None) -> InvoiceSearchFilters:
    query = query.strip()
    if not query:
        raise NLSearchError("Search query must not be empty.")

    if settings.openai_api_key:
        try:
            return _parse_with_llm(query, today=today or date.today())
        except Exception:
            # Never let a provider hiccup break search; the deterministic parser
            # handles the common phrasings.
            pass
    return _parse_fallback(query, today=today or date.today())


def search_invoices(db: Session, *, organization_id: UUID, filters: InvoiceSearchFilters) -> list[Invoice]:
    from app.services.invoice_review import _invoice_detail_query

    search = (
        _invoice_detail_query()
        .where(Invoice.organization_id == organization_id)
        .order_by(Invoice.updated_at.desc())
        .limit(filters.limit)
    )
    if filters.status is not None:
        search = search.where(Invoice.status == filters.status.value)
    if filters.invoice_number_contains:
        search = search.where(Invoice.invoice_number.ilike(f"%{filters.invoice_number_contains}%"))
    if filters.supplier_name_contains:
        search = search.join(Supplier, Supplier.id == Invoice.supplier_id).where(
            Supplier.name.ilike(f"%{filters.supplier_name_contains}%")
        )
    if filters.min_total is not None:
        search = search.where(Invoice.total_amount >= filters.min_total)
    if filters.max_total is not None:
        search = search.where(Invoice.total_amount <= filters.max_total)
    if filters.currency:
        search = search.where(Invoice.currency == filters.currency.upper())
    if filters.date_from is not None:
        search = search.where(Invoice.invoice_date >= filters.date_from)
    if filters.date_to is not None:
        search = search.where(Invoice.invoice_date <= filters.date_to)

    return list(db.scalars(search))


def _parse_with_llm(query: str, *, today: date) -> InvoiceSearchFilters:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    schema = InvoiceSearchFilters.model_json_schema()
    response = client.responses.create(
        model=settings.openai_extraction_model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Translate this invoice search request into JSON filters matching the schema. "
                            "Leave a filter null when the request does not mention it. "
                            f"Today's date is {today.isoformat()} (for relative dates like 'last month').\n"
                            f"Schema: {json.dumps(schema, default=str)}\n"
                            f"Request: {query}"
                        ),
                    }
                ],
            }
        ],
        text={"format": {"type": "json_object"}},
    )
    raw = json.loads(response.output_text)
    try:
        return InvoiceSearchFilters.model_validate(raw)
    except ValidationError as exc:
        raise NLSearchError("Could not translate the search query into filters.") from exc


_STATUS_KEYWORDS = {
    "approved": InvoiceStatus.APPROVED,
    "rejected": InvoiceStatus.REJECTED,
    "failed": InvoiceStatus.FAILED,
    "review": InvoiceStatus.REVIEW_REQUIRED,
    "pending review": InvoiceStatus.REVIEW_REQUIRED,
    "queued": InvoiceStatus.QUEUED,
    "processing": InvoiceStatus.PROCESSING,
    "uploaded": InvoiceStatus.UPLOADED,
}

_CURRENCY_CODES = {"USD", "EUR", "GBP", "AUD", "CAD", "JPY", "CHF", "INR", "LKR", "SGD"}

_AMOUNT_PATTERN = re.compile(
    r"(over|above|more than|greater than|under|below|less than|>=?|<=?)\s*\$?\s*([\d,]+(?:\.\d+)?)\s*(k|m)?",
    re.IGNORECASE,
)


def _parse_fallback(query: str, *, today: date) -> InvoiceSearchFilters:
    """Deterministic keyword parser used without an OpenAI key (or when the
    provider call fails). Intentionally handles only the frequent phrasings:
    status words, amount comparisons, currency codes, month/year names, and a
    trailing free-text supplier hint."""
    text = query.lower()
    filters: dict[str, Any] = {}
    consumed_spans: list[tuple[int, int]] = []

    for keyword, status in _STATUS_KEYWORDS.items():
        index = text.find(keyword)
        if index != -1:
            filters["status"] = status
            consumed_spans.append((index, index + len(keyword)))
            break

    for match in _AMOUNT_PATTERN.finditer(text):
        direction, raw_amount, magnitude = match.groups()
        try:
            amount = Decimal(raw_amount.replace(",", ""))
        except InvalidOperation:
            continue
        if magnitude:
            amount *= Decimal("1000") if magnitude.lower() == "k" else Decimal("1000000")
        if direction.lower() in {"over", "above", "more than", "greater than", ">", ">="}:
            filters["min_total"] = amount
        else:
            filters["max_total"] = amount
        consumed_spans.append(match.span())

    for code in _CURRENCY_CODES:
        pattern = re.compile(rf"\b{code.lower()}\b")
        match = pattern.search(text)
        if match:
            filters["currency"] = code
            consumed_spans.append(match.span())
            break

    month_span = _extract_month_range(text, today=today)
    if month_span is not None:
        date_from, date_to, span = month_span
        filters["date_from"] = date_from
        filters["date_to"] = date_to
        consumed_spans.append(span)

    supplier_hint = _remaining_words(text, consumed_spans)
    if supplier_hint:
        filters["supplier_name_contains"] = supplier_hint

    return InvoiceSearchFilters(**filters)


def _extract_month_range(text: str, *, today: date) -> tuple[date, date, tuple[int, int]] | None:
    for month_index in range(1, 13):
        month_name = calendar.month_name[month_index].lower()
        match = re.search(rf"\b{month_name}\b(?:\s+(\d{{4}}))?", text)
        if match is None:
            continue
        year = int(match.group(1)) if match.group(1) else today.year
        # A bare month name means the most recent occurrence of that month.
        if not match.group(1) and month_index > today.month:
            year -= 1
        last_day = calendar.monthrange(year, month_index)[1]
        return date(year, month_index, 1), date(year, month_index, last_day), match.span()
    return None


_NOISE_WORDS = {
    "invoice", "invoices", "show", "me", "all", "find", "list", "from", "for", "the",
    "with", "in", "of", "and", "that", "are", "is", "get", "than", "amount", "total",
    "last", "this", "month", "year", "need", "needing", "required", "status",
}


def _remaining_words(text: str, consumed_spans: list[tuple[int, int]]) -> str | None:
    # Blank out everything already claimed by a structured filter, then treat
    # whatever meaningful words remain as a supplier-name hint.
    characters = list(text)
    for start, end in consumed_spans:
        for position in range(start, end):
            characters[position] = " "
    leftover = "".join(characters)
    words = [
        word
        for word in re.findall(r"[a-z][a-z0-9&.-]*", leftover)
        if word not in _NOISE_WORDS
    ]
    if not words:
        return None
    return " ".join(words)[:100]
