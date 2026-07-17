"""Invoice field extraction: turn an uploaded document into structured fields
via an LLM, validate the response against a strict schema, then persist the
extraction, line items and validation results. Ships a deterministic
development extractor so the pipeline runs without an OpenAI API key."""

import base64
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings
from app.services.invoice_validation import (
    InvoiceLineItemInput,
    InvoiceValidationInput,
    next_status_after_validation,
    validate_invoice,
)

# Expense categories a line item may be classified into during extraction.
# Kept as a closed set (Literal below) so strict structured output can enforce
# it and downstream GL-coding/reporting can rely on stable values.
LINE_ITEM_CATEGORIES = (
    "goods",
    "services",
    "software",
    "travel",
    "utilities",
    "professional_services",
    "marketing",
    "other",
)

PROMPT_NAME = "invoice_extraction"
PROMPT_VERSION = "2026-07-17.v2"
PROMPT_TEMPLATE = """Extract structured invoice fields from the invoice document.
Return only JSON that matches the configured schema. If a field is unknown, use null.
For each line item, classify it into one of the allowed expense categories; use "other" when unsure.
Report confidence_score as your overall confidence in the extraction (0 to 1).
Report field_confidences as your per-field confidence (0 to 1) for each named field;
use null for a field you did not find in the document.
When example invoices from the same supplier are provided, use them to resolve
layout ambiguity (field placement, number formats), but never copy their values
into fields you cannot see in this document.
"""


class ExtractedInvoiceLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None
    # Literal renders as a JSON-schema enum, so strict mode guarantees the model
    # can only answer with a known category (or null when it cannot tell).
    category: Literal[*LINE_ITEM_CATEGORIES] | None = None


class ExtractedFieldConfidences(BaseModel):
    # Per-field confidence in [0, 1]; null means "field not found in document".
    # Fixed keys (rather than a free dict) keep OpenAI strict mode satisfiable.
    model_config = ConfigDict(extra="forbid")

    invoice_number: Decimal | None = Field(default=None, ge=0, le=1)
    supplier_name: Decimal | None = Field(default=None, ge=0, le=1)
    invoice_date: Decimal | None = Field(default=None, ge=0, le=1)
    total_amount: Decimal | None = Field(default=None, ge=0, le=1)
    currency: Decimal | None = Field(default=None, ge=0, le=1)


class ExtractedInvoicePayload(BaseModel):
    # extra="forbid" makes the model reject any field the LLM invents, so the
    # strict JSON schema and our parsing stay in lockstep.
    model_config = ConfigDict(extra="forbid")

    invoice_number: str | None = None
    supplier_name: str | None = None
    invoice_date: str | None = None
    total_amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    confidence_score: Decimal = Field(ge=0, le=1)
    field_confidences: ExtractedFieldConfidences | None = None
    line_items: list[ExtractedInvoiceLineItem] = Field(default_factory=list)


@dataclass(frozen=True)
class ExtractionUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: Decimal | None = None


@dataclass(frozen=True)
class ExtractionResult:
    payload: ExtractedInvoicePayload
    model_name: str
    usage: ExtractionUsage


class ExtractionError(RuntimeError):
    pass


# Transient failures (timeouts, rate limits) are safe to retry; the worker
# (via is_retryable_processing_error) distinguishes this from permanent
# ExtractionError to decide whether to requeue or fail immediately.
class TransientExtractionError(ExtractionError):
    pass


class InvalidExtractionResponseError(ExtractionError):
    pass


class DevelopmentInvoiceExtractor:
    # Deterministic stand-in used when no OpenAI key is configured: echoes the
    # invoice's known fields so the rest of the pipeline can be exercised locally.
    model_name = "development-extractor"

    def extract(
        self,
        *,
        invoice,
        file_bytes: bytes,
        mime_type: str | None = None,
        examples: list[dict[str, Any]] | None = None,
    ) -> ExtractionResult:
        payload = ExtractedInvoicePayload(
            invoice_number=invoice.invoice_number,
            total_amount=invoice.total_amount,
            currency=invoice.currency,
            confidence_score=Decimal("0.8000"),
            # Mirror the real extractors' shape so confidence-driven routing and
            # auto-approval logic is exercisable without a provider key.
            field_confidences=ExtractedFieldConfidences(
                invoice_number=Decimal("0.9000") if invoice.invoice_number else None,
                total_amount=Decimal("0.9000") if invoice.total_amount is not None else None,
                currency=Decimal("0.9000"),
            ),
            line_items=[
                ExtractedInvoiceLineItem(
                    description="Extracted invoice total",
                    quantity=Decimal("1"),
                    unit_price=invoice.total_amount,
                    line_total=invoice.total_amount,
                    category="other",
                )
            ]
            if invoice.total_amount is not None
            else [],
        )
        return ExtractionResult(payload=payload, model_name=self.model_name, usage=ExtractionUsage())


class OpenAIInvoiceExtractor:
    def __init__(self, *, api_key: str, model_name: str) -> None:
        self.api_key = api_key
        self.model_name = model_name

    def extract(
        self,
        *,
        invoice,
        file_bytes: bytes,
        mime_type: str | None = None,
        examples: list[dict[str, Any]] | None = None,
    ) -> ExtractionResult:
        # Import lazily so the OpenAI SDK is only required when this extractor
        # is actually selected, keeping it an optional dependency.
        try:
            from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
        except ImportError as exc:
            raise ExtractionError("OpenAI SDK is not installed.") from exc

        client = OpenAI(api_key=self.api_key)
        mime_type = mime_type or "application/pdf"
        # The Responses API accepts PDFs via `input_file` but rejects images
        # there ("unsupported MIME type"); images must be sent as `input_image`
        # with a data-URL. Since uploads allow PDF/JPEG/PNG, branch on the type.
        if mime_type.startswith("image/"):
            document_content = {
                "type": "input_image",
                "image_url": _file_data_url(file_bytes=file_bytes, mime_type=mime_type),
            }
        else:
            document_content = {
                "type": "input_file",
                "filename": _invoice_filename(invoice_id=invoice.id, mime_type=mime_type),
                "file_data": _file_data_url(file_bytes=file_bytes, mime_type=mime_type),
            }
        try:
            response = client.responses.create(
                model=self.model_name,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": _prompt_text(invoice=invoice, examples=examples),
                            },
                            document_content,
                        ],
                    }
                ],
                # Constrain the model to our Pydantic-derived schema so the
                # response is guaranteed-parseable JSON, not free-form text.
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "invoice_extraction",
                        "description": "Structured fields extracted from an invoice document.",
                        "schema": extraction_json_schema(),
                        "strict": True,
                    }
                },
            )
        # Split provider errors: network/rate-limit issues are retryable, any
        # other failure is treated as permanent.
        except RateLimitError as exc:
            # `insufficient_quota` arrives as a 429 but is permanent until billing
            # is fixed, so retrying only wastes attempts; treat it as a hard
            # failure. Genuine rate limiting (any other 429) stays retryable.
            code = getattr(exc, "code", None)
            if code == "insufficient_quota" or "insufficient_quota" in str(exc):
                raise ExtractionError("OpenAI extraction failed: account quota exhausted.") from exc
            raise TransientExtractionError("OpenAI extraction failed due to a transient provider error.") from exc
        except (APITimeoutError, APIConnectionError) as exc:
            raise TransientExtractionError("OpenAI extraction failed due to a transient provider error.") from exc
        except Exception as exc:
            raise ExtractionError("OpenAI extraction failed.") from exc

        raw_text = _response_output_text(response)
        try:
            raw_payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise InvalidExtractionResponseError("OpenAI extraction returned invalid JSON.") from exc

        return ExtractionResult(
            payload=parse_extraction_payload(raw_payload),
            model_name=self.model_name,
            usage=_response_usage(response),
        )


class GeminiInvoiceExtractor:
    def __init__(self, *, api_key: str, model_name: str) -> None:
        self.api_key = api_key
        self.model_name = model_name

    def extract(
        self,
        *,
        invoice,
        file_bytes: bytes,
        mime_type: str | None = None,
        examples: list[dict[str, Any]] | None = None,
    ) -> ExtractionResult:
        # Import lazily so the Gemini SDK is only required when this extractor is
        # actually selected, keeping it an optional dependency.
        try:
            from google import genai
            from google.genai import errors as genai_errors
            from google.genai import types
        except ImportError as exc:
            raise ExtractionError("Gemini SDK is not installed.") from exc

        client = genai.Client(api_key=self.api_key)
        mime_type = mime_type or "application/pdf"
        # Gemini reads PDFs and images through the same inline-bytes Part, so no
        # per-type branching is needed here (unlike the OpenAI Responses API).
        # The schema is embedded in the prompt and JSON output is forced via
        # response_mime_type; our own parse step still validates the result.
        prompt = (
            f"{PROMPT_TEMPLATE}\n"
            f"Return only JSON matching this schema:\n{json.dumps(extraction_json_schema())}\n"
            f"{_prompt_known_fields_and_examples(invoice=invoice, examples=examples)}"
        )
        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
        # Server-side/transient statuses are retryable; everything else (auth,
        # quota, malformed request) is permanent so the worker stops requeuing.
        except genai_errors.APIError as exc:
            status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            if status in {429, 500, 502, 503, 504}:
                raise TransientExtractionError("Gemini extraction failed due to a transient provider error.") from exc
            raise ExtractionError("Gemini extraction failed.") from exc
        except Exception as exc:
            raise ExtractionError("Gemini extraction failed.") from exc

        raw_text = response.text
        try:
            raw_payload = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise InvalidExtractionResponseError("Gemini extraction returned invalid JSON.") from exc

        return ExtractionResult(
            payload=parse_extraction_payload(raw_payload),
            model_name=self.model_name,
            usage=_gemini_usage(response),
        )


# Provider identifiers shared by the API, the persisted job column and the UI.
PROVIDER_OPENAI = "openai"
PROVIDER_GEMINI = "gemini"
PROVIDER_LABELS = {PROVIDER_OPENAI: "OpenAI", PROVIDER_GEMINI: "Gemini"}


def provider_availability() -> dict[str, bool]:
    # A provider is "available" only when its API key is configured; the UI uses
    # this to disable options the server can't actually run.
    return {
        PROVIDER_OPENAI: bool(settings.openai_api_key),
        PROVIDER_GEMINI: bool(settings.gemini_api_key),
    }


def default_provider() -> str | None:
    # Prefer OpenAI, then Gemini; None means only the dev fallback is available.
    availability = provider_availability()
    for provider in (PROVIDER_OPENAI, PROVIDER_GEMINI):
        if availability[provider]:
            return provider
    return None


def _openai_extractor() -> "OpenAIInvoiceExtractor":
    return OpenAIInvoiceExtractor(
        api_key=settings.openai_api_key,
        model_name=settings.openai_extraction_model,
    )


def _gemini_extractor() -> "GeminiInvoiceExtractor":
    return GeminiInvoiceExtractor(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_extraction_model,
    )


def build_invoice_extractor(provider: str | None = None):
    # Pick the extractor for the requested provider when its key is configured.
    # An explicit-but-unavailable choice, or no choice, falls back to whichever
    # provider is available (preferring OpenAI), then the deterministic dev
    # extractor so the pipeline always runs.
    provider = (provider or "").strip().lower() or None
    availability = provider_availability()

    if provider == PROVIDER_OPENAI and availability[PROVIDER_OPENAI]:
        return _openai_extractor()
    if provider == PROVIDER_GEMINI and availability[PROVIDER_GEMINI]:
        return _gemini_extractor()

    if provider is None:
        if availability[PROVIDER_OPENAI]:
            return _openai_extractor()
        if availability[PROVIDER_GEMINI]:
            return _gemini_extractor()

    return DevelopmentInvoiceExtractor()


def _prompt_known_fields_and_examples(*, invoice, examples: list[dict[str, Any]] | None) -> str:
    parts = [
        f"Known invoice number: {invoice.invoice_number}",
        f"Known amount: {invoice.total_amount}",
        f"Known currency: {invoice.currency}",
    ]
    if examples:
        parts.append("Previously approved invoices from the same supplier (layout/format reference only):")
        parts.append(json.dumps(examples, default=str))
    return "\n".join(parts)


def _prompt_text(*, invoice, examples: list[dict[str, Any]] | None) -> str:
    # Static template first, per-invoice details last, so provider-side prompt
    # caching can reuse the shared prefix across extractions.
    return f"{PROMPT_TEMPLATE}\n{_prompt_known_fields_and_examples(invoice=invoice, examples=examples)}"


def few_shot_examples(db, *, invoice, limit: int | None = None) -> list[dict[str, Any]]:
    """Retrieval-augmented extraction: compact summaries of the supplier's most
    recently approved invoices, used as few-shot examples in the prompt. Approved
    invoices carry reviewer-corrected values, so they are ground truth for how
    this supplier's layout should be read. Empty when the feature is disabled or
    the invoice has no matched supplier yet."""
    if not settings.extraction_few_shot_enabled or invoice.supplier_id is None:
        return []

    from sqlalchemy import select

    from app.models.invoice import Invoice

    limit = limit or settings.extraction_few_shot_examples
    approved = db.scalars(
        select(Invoice)
        .where(
            Invoice.organization_id == invoice.organization_id,
            Invoice.supplier_id == invoice.supplier_id,
            Invoice.id != invoice.id,
            Invoice.status == "approved",
        )
        .order_by(Invoice.updated_at.desc())
        .limit(limit)
    )
    return [
        {
            "invoice_number": candidate.invoice_number,
            "invoice_date": candidate.invoice_date.isoformat() if candidate.invoice_date else None,
            "total_amount": str(candidate.total_amount) if candidate.total_amount is not None else None,
            "currency": candidate.currency,
            # Cap line items so a long historical invoice can't blow up the prompt.
            "line_items": [
                {"description": item.description, "category": item.category}
                for item in candidate.line_items[:5]
            ],
        }
        for candidate in approved
    ]


def run_invoice_extraction(
    *,
    invoice,
    file_bytes: bytes,
    mime_type: str | None = None,
    provider: str | None = None,
    examples: list[dict[str, Any]] | None = None,
) -> ExtractionResult:
    """Extraction entry point with optional model tiering: try the cheaper
    tier-1 OpenAI model first and escalate to the primary model only when the
    tier-1 confidence lands below the escalation bar. Usage/cost of both calls
    is aggregated so spend accounting stays honest."""
    primary = build_invoice_extractor(provider=provider)
    tiering_applicable = (
        settings.extraction_tiering_enabled
        and isinstance(primary, OpenAIInvoiceExtractor)
        and bool(settings.openai_extraction_tier1_model)
        and settings.openai_extraction_tier1_model != primary.model_name
    )
    if not tiering_applicable:
        return primary.extract(invoice=invoice, file_bytes=file_bytes, mime_type=mime_type, examples=examples)

    tier1 = OpenAIInvoiceExtractor(
        api_key=primary.api_key,
        model_name=settings.openai_extraction_tier1_model,
    )
    first = tier1.extract(invoice=invoice, file_bytes=file_bytes, mime_type=mime_type, examples=examples)
    if first.payload.confidence_score >= Decimal(settings.extraction_escalation_confidence):
        return first

    from app.core.metrics import EXTRACTION_ESCALATIONS

    EXTRACTION_ESCALATIONS.inc()
    second = primary.extract(invoice=invoice, file_bytes=file_bytes, mime_type=mime_type, examples=examples)
    # Keep whichever attempt the model itself was more confident about, but
    # charge the invoice for both calls.
    chosen = second if second.payload.confidence_score >= first.payload.confidence_score else first
    return ExtractionResult(
        payload=chosen.payload,
        model_name=chosen.model_name,
        usage=_combined_usage(first.usage, second.usage),
    )


def _combined_usage(first: ExtractionUsage, second: ExtractionUsage) -> ExtractionUsage:
    def add(a: int | None, b: int | None) -> int | None:
        if a is None and b is None:
            return None
        return (a or 0) + (b or 0)

    def add_cost(a: Decimal | None, b: Decimal | None) -> Decimal | None:
        if a is None and b is None:
            return None
        return (a or Decimal("0")) + (b or Decimal("0"))

    return ExtractionUsage(
        input_tokens=add(first.input_tokens, second.input_tokens),
        output_tokens=add(first.output_tokens, second.output_tokens),
        estimated_cost=add_cost(first.estimated_cost, second.estimated_cost),
    )


def minimum_field_confidence(payload: ExtractedInvoicePayload) -> Decimal | None:
    """Lowest reported per-field confidence, or None when the extractor did not
    report any. Auto-approval gates on this so one weak field blocks touchless
    processing even when the overall score looks fine."""
    if payload.field_confidences is None:
        return None
    values = [value for value in payload.field_confidences.model_dump().values() if value is not None]
    return min(values) if values else None


# Validation keywords Pydantic emits but OpenAI's strict Structured Outputs mode
# rejects; leaving any of them in makes the API refuse the whole schema.
_UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "default",
        "minItems",
        "maxItems",
        "uniqueItems",
    }
)


def _to_strict_schema(node: Any) -> Any:
    # Rewrite a Pydantic-generated JSON schema into the subset OpenAI strict mode
    # accepts: strip unsupported keywords, and on every object force `required` to
    # list all properties and forbid extras (strict mode demands both). Nullable
    # fields stay satisfiable because their anyOf already permits null.
    if isinstance(node, list):
        return [_to_strict_schema(item) for item in node]
    if not isinstance(node, dict):
        return node

    cleaned = {
        key: _to_strict_schema(value)
        for key, value in node.items()
        if key not in _UNSUPPORTED_SCHEMA_KEYS
    }

    if cleaned.get("type") == "object" or "properties" in cleaned:
        properties = cleaned.get("properties", {})
        cleaned["required"] = list(properties.keys())
        cleaned["additionalProperties"] = False

    return cleaned


def extraction_json_schema() -> dict[str, Any]:
    return _to_strict_schema(ExtractedInvoicePayload.model_json_schema())


def get_or_create_prompt_version(db):
    # Local imports avoid a circular dependency between this service module and
    # the ORM models at import time.
    from sqlalchemy import select

    from app.models.prompt import PromptVersion

    # Record the exact prompt/schema used for extractions so results stay
    # traceable to a versioned prompt; reuse the row if it already exists.
    prompt_version = db.scalar(
        select(PromptVersion).where(
            PromptVersion.name == PROMPT_NAME,
            PromptVersion.version == PROMPT_VERSION,
        )
    )
    if prompt_version is not None:
        return prompt_version

    prompt_version = PromptVersion(
        name=PROMPT_NAME,
        version=PROMPT_VERSION,
        prompt_template=PROMPT_TEMPLATE,
        json_schema=extraction_json_schema(),
        is_active=True,
    )
    db.add(prompt_version)
    db.flush()
    return prompt_version


def persist_extraction_result(
    db,
    *,
    invoice,
    result: ExtractionResult,
):
    from app.models.invoice import (
        InvoiceExtraction,
        InvoiceLineItem,
    )
    from app.models.invoice import (
        InvoiceValidationResult as InvoiceValidationResultModel,
    )

    prompt_version = get_or_create_prompt_version(db)
    payload = result.payload.model_dump(mode="json")

    extraction = InvoiceExtraction(
        invoice_id=invoice.id,
        prompt_version_id=prompt_version.id,
        model_name=result.model_name,
        prompt_version=prompt_version.version,
        extracted_payload=payload,
        confidence_score=result.payload.confidence_score,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        estimated_cost=result.usage.estimated_cost,
    )
    db.add(extraction)

    for item in result.payload.line_items:
        db.add(
            InvoiceLineItem(
                invoice_id=invoice.id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
                category=item.category,
            )
        )

    field_confidences = (
        {
            name: value
            for name, value in result.payload.field_confidences.model_dump().items()
            if value is not None
        }
        if result.payload.field_confidences is not None
        else None
    )
    # Run business validation against the extracted values so the resulting
    # status reflects whether the invoice can auto-pass or needs human review.
    validation_results = validate_invoice(
        InvoiceValidationInput(
            invoice_number=result.payload.invoice_number or invoice.invoice_number,
            supplier_found=invoice.supplier_id is not None,
            total_amount=result.payload.total_amount,
            extracted_confidence=result.payload.confidence_score,
            field_confidences=field_confidences,
            field_confidence_threshold=Decimal(settings.field_confidence_review_threshold),
            line_items=tuple(
                InvoiceLineItemInput(
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                )
                for item in result.payload.line_items
            ),
        )
    )
    from app.services.validation_explanations import explain_validation_failures

    # Failed rules get a plain-language explanation + suggested fix so reviewers
    # see actionable guidance instead of just rule codes.
    explanations = explain_validation_failures(
        [item for item in validation_results if not item.passed]
    )
    for validation_result in validation_results:
        explanation, suggested_fix = explanations.get(id(validation_result), (None, None))
        db.add(
            InvoiceValidationResultModel(
                invoice_id=invoice.id,
                rule_code=validation_result.rule_code,
                severity=validation_result.severity,
                message=validation_result.message,
                passed=validation_result.passed,
                explanation=explanation,
                suggested_fix=suggested_fix,
            )
        )

    # Prefer extracted values but keep the uploader-supplied ones when the model
    # returned nothing, so we never overwrite known data with blanks.
    invoice.total_amount = result.payload.total_amount or invoice.total_amount
    invoice.currency = result.payload.currency.upper()
    invoice.invoice_number = result.payload.invoice_number or invoice.invoice_number
    invoice.status = next_status_after_validation(validation_results).value

    return extraction


def parse_extraction_payload(raw_payload: dict[str, Any]) -> ExtractedInvoicePayload:
    try:
        return ExtractedInvoicePayload.model_validate(raw_payload)
    except ValidationError as exc:
        raise InvalidExtractionResponseError("Invoice extraction response did not match the required schema.") from exc


def _response_output_text(response: Any) -> str:
    # Prefer the SDK's flattened convenience field, but fall back to walking the
    # structured output blocks in case it is absent on a given response shape.
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    output_items = getattr(response, "output", None) or []
    for item in output_items:
        content_items = getattr(item, "content", None) or []
        for content in content_items:
            text = getattr(content, "text", None)
            if text:
                return text

    raise InvalidExtractionResponseError("OpenAI extraction response did not include output text.")


def _response_usage(response: Any) -> ExtractionUsage:
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None) if usage else None
    output_tokens = getattr(usage, "output_tokens", None) if usage else None
    return ExtractionUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=_estimate_cost(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _gemini_usage(response: Any) -> ExtractionUsage:
    # Gemini reports token counts under usage_metadata with different field names
    # than OpenAI, and is priced with its own configured rates.
    usage = getattr(response, "usage_metadata", None)
    input_tokens = getattr(usage, "prompt_token_count", None) if usage else None
    output_tokens = getattr(usage, "candidates_token_count", None) if usage else None
    return ExtractionUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=_estimate_cost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost_per_million=settings.gemini_input_cost_per_million_tokens,
            output_cost_per_million=settings.gemini_output_cost_per_million_tokens,
        ),
    )


def _file_data_url(*, file_bytes: bytes, mime_type: str) -> str:
    # Inline the document as a base64 data URL so the file travels in the request
    # body itself, no separate upload/hosting step required.
    encoded = base64.b64encode(file_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _invoice_filename(*, invoice_id: Any, mime_type: str) -> str:
    extensions = {
        "application/pdf": "pdf",
        "image/jpeg": "jpg",
        "image/png": "png",
    }
    return f"invoice-{invoice_id}.{extensions.get(mime_type, 'bin')}"


def _estimate_cost(
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    input_cost_per_million: str | None = None,
    output_cost_per_million: str | None = None,
) -> Decimal | None:
    if input_tokens is None and output_tokens is None:
        return None

    # Prices are configured per million tokens; use Decimal throughout to avoid
    # float rounding when accumulating cost. Callers pass provider-specific rates;
    # default to the OpenAI rates for backward compatibility.
    input_cost = Decimal(
        input_cost_per_million
        if input_cost_per_million is not None
        else settings.openai_input_cost_per_million_tokens
    )
    output_cost = Decimal(
        output_cost_per_million
        if output_cost_per_million is not None
        else settings.openai_output_cost_per_million_tokens
    )
    total = Decimal("0")
    if input_tokens is not None:
        total += Decimal(input_tokens) * input_cost / Decimal("1000000")
    if output_tokens is not None:
        total += Decimal(output_tokens) * output_cost / Decimal("1000000")

    return total.quantize(Decimal("0.000001"))
