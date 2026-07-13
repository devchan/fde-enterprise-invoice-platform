"""Invoice field extraction: turn an uploaded document into structured fields
via an LLM, validate the response against a strict schema, then persist the
extraction, line items and validation results. Ships a deterministic
development extractor so the pipeline runs without an OpenAI API key."""

import base64
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings
from app.services.invoice_validation import (
    InvoiceLineItemInput,
    InvoiceValidationInput,
    next_status_after_validation,
    validate_invoice,
)

PROMPT_NAME = "invoice_extraction"
PROMPT_VERSION = "2026-07-10.v1"
PROMPT_TEMPLATE = """Extract structured invoice fields from the invoice document.
Return only JSON that matches the configured schema. If a field is unknown, use null.
"""


class ExtractedInvoiceLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None


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
# distinguishes this from permanent ExtractionError to decide whether to requeue.
class TransientExtractionError(ExtractionError):
    pass


class InvalidExtractionResponseError(ExtractionError):
    pass


class DevelopmentInvoiceExtractor:
    # Deterministic stand-in used when no OpenAI key is configured: echoes the
    # invoice's known fields so the rest of the pipeline can be exercised locally.
    model_name = "development-extractor"

    def extract(self, *, invoice, file_bytes: bytes, mime_type: str | None = None) -> ExtractionResult:
        payload = ExtractedInvoicePayload(
            invoice_number=invoice.invoice_number,
            total_amount=invoice.total_amount,
            currency=invoice.currency,
            confidence_score=Decimal("0.8000"),
            line_items=[
                ExtractedInvoiceLineItem(
                    description="Extracted invoice total",
                    quantity=Decimal("1"),
                    unit_price=invoice.total_amount,
                    line_total=invoice.total_amount,
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

    def extract(self, *, invoice, file_bytes: bytes, mime_type: str | None = None) -> ExtractionResult:
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
                                "text": (
                                    f"{PROMPT_TEMPLATE}\n"
                                    f"Known invoice number: {invoice.invoice_number}\n"
                                    f"Known amount: {invoice.total_amount}\n"
                                    f"Known currency: {invoice.currency}"
                                ),
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


def build_invoice_extractor():
    # Use the real extractor when a key is configured, otherwise fall back to
    # the deterministic development extractor.
    if settings.openai_api_key:
        return OpenAIInvoiceExtractor(
            api_key=settings.openai_api_key,
            model_name=settings.openai_extraction_model,
        )

    return DevelopmentInvoiceExtractor()


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
            )
        )

    # Run business validation against the extracted values so the resulting
    # status reflects whether the invoice can auto-pass or needs human review.
    validation_results = validate_invoice(
        InvoiceValidationInput(
            invoice_number=result.payload.invoice_number or invoice.invoice_number,
            supplier_found=invoice.supplier_id is not None,
            total_amount=result.payload.total_amount,
            extracted_confidence=result.payload.confidence_score,
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
    for validation_result in validation_results:
        db.add(
            InvoiceValidationResultModel(
                invoice_id=invoice.id,
                rule_code=validation_result.rule_code,
                severity=validation_result.severity,
                message=validation_result.message,
                passed=validation_result.passed,
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


def _estimate_cost(*, input_tokens: int | None, output_tokens: int | None) -> Decimal | None:
    if input_tokens is None and output_tokens is None:
        return None

    # Prices are configured per million tokens; use Decimal throughout to avoid
    # float rounding when accumulating cost.
    input_cost = Decimal(settings.openai_input_cost_per_million_tokens)
    output_cost = Decimal(settings.openai_output_cost_per_million_tokens)
    total = Decimal("0")
    if input_tokens is not None:
        total += Decimal(input_tokens) * input_cost / Decimal("1000000")
    if output_tokens is not None:
        total += Decimal(output_tokens) * output_cost / Decimal("1000000")

    return total.quantize(Decimal("0.000001"))
