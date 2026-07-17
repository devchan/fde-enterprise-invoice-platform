"""Plain-language explanations for failed validation rules.

Reviewers see *why* an invoice was routed to them and what would fix it, not
just a rule code. Deterministic templates cover every known rule so this is
free and instant; when VALIDATION_EXPLANATIONS_LLM_ENABLED is on (and an
OpenAI key is configured) the templates are replaced by model-written text
tailored to the specific failure messages. LLM failures always fall back to
the templates — explanation generation must never break extraction.
"""

import json
from typing import Any

from app.core.config import settings

# rule_code -> (explanation, suggested_fix). Written for a reviewer, not an
# engineer: say what is wrong in business terms and what action resolves it.
_TEMPLATES: dict[str, tuple[str, str]] = {
    "invoice_number_required": (
        "The document does not appear to contain an invoice number, or the extractor could not find one.",
        "Locate the invoice number on the document and enter it in the invoice number field.",
    ),
    "supplier_found": (
        "This invoice is not linked to a known supplier, so it cannot be matched against supplier history.",
        "Match the invoice to an existing supplier record, or create the supplier first.",
    ),
    "duplicate_invoice_number": (
        "Another invoice with the same number already exists for this supplier, "
        "which usually means a duplicate submission.",
        "Compare with the existing invoice; reject this one if it is a duplicate, "
        "or correct the invoice number if it was misread.",
    ),
    "total_amount_required": (
        "No total amount could be read from the document.",
        "Find the invoice total on the document and enter it manually.",
    ),
    "approval_threshold": (
        "The invoice total is above the automatic approval limit, "
        "so it needs human sign-off regardless of data quality.",
        "Verify the amount against the document and approve if it is legitimate.",
    ),
    "extraction_confidence": (
        "The AI extractor was not confident in its overall reading of this document "
        "(poor scan quality or unusual layout are common causes).",
        "Compare each extracted field against the document before approving.",
    ),
    "field_confidence_low": (
        "The AI extractor was unsure about this specific field's value.",
        "Check this field against the document and correct it if needed.",
    ),
    "line_item_description_required": (
        "A line item was extracted without a readable description.",
        "Fill in the missing line item description from the document, or remove the line if it is an artifact.",
    ),
    "line_item_total_matches": (
        "A line item's total does not equal its quantity multiplied by unit price, which suggests a misread digit.",
        "Re-check the quantity, unit price, and line total on the document and correct the misread value.",
    ),
    "amount_anomaly": (
        "The invoice total is far outside this supplier's historical range of approved amounts.",
        "Confirm the amount with the document (and the supplier if needed) before approving.",
    ),
    "near_duplicate_similarity": (
        "This invoice's content is nearly identical to another invoice in your organization, "
        "which can indicate a resubmission or duplicate billing.",
        "Open the similar invoice from the side panel and confirm this one is genuinely new before approving.",
    ),
}

_FALLBACK = (
    "This validation rule failed for the extracted invoice data.",
    "Review the related field against the document and correct it if needed.",
)


def explain_validation_failures(failures: list[Any]) -> dict[int, tuple[str, str]]:
    """Explanations keyed by id() of each failed result object (results are
    plain value objects with no natural unique key — two line items can fail the
    same rule)."""
    explanations = {id(failure): _TEMPLATES.get(failure.rule_code, _FALLBACK) for failure in failures}
    if failures and settings.validation_explanations_llm_enabled and settings.openai_api_key:
        try:
            explanations.update(_llm_explanations(failures))
        except Exception:
            # Any provider issue leaves the deterministic templates in place.
            pass
    return explanations


def _llm_explanations(failures: list[Any]) -> dict[int, tuple[str, str]]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    items = [
        {"index": index, "rule_code": failure.rule_code, "message": failure.message}
        for index, failure in enumerate(failures)
    ]
    response = client.responses.create(
        model=settings.openai_extraction_model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "For each failed invoice validation rule below, write a one-sentence "
                            "plain-language explanation for a human accounts-payable reviewer and a "
                            "one-sentence suggested fix. Return JSON only.\n"
                            f"{json.dumps(items)}"
                        ),
                    }
                ],
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "validation_explanations",
                "schema": {
                    "type": "object",
                    "properties": {
                        "explanations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "index": {"type": "integer"},
                                    "explanation": {"type": "string"},
                                    "suggested_fix": {"type": "string"},
                                },
                                "required": ["index", "explanation", "suggested_fix"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["explanations"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        },
    )
    parsed = json.loads(response.output_text)
    results: dict[int, tuple[str, str]] = {}
    for entry in parsed.get("explanations", []):
        index = entry.get("index")
        if isinstance(index, int) and 0 <= index < len(failures):
            results[id(failures[index])] = (entry["explanation"], entry["suggested_fix"])
    return results
