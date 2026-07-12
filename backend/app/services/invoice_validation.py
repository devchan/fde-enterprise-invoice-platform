"""Pure business rules for validating an extracted invoice. Each rule yields a
pass/fail result with a severity; a single failing rule (of any severity) routes
the invoice to human review. Kept side-effect-free so it is trivially testable."""

from dataclasses import dataclass
from decimal import Decimal

from .invoice_workflow import InvoiceStatus


@dataclass(frozen=True)
class InvoiceLineItemInput:
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None


@dataclass(frozen=True)
class InvoiceValidationInput:
    invoice_number: str | None
    supplier_found: bool
    total_amount: Decimal | None
    extracted_confidence: Decimal | None = None
    duplicate_invoice_number: bool = False
    approval_threshold: Decimal = Decimal("10000.00")
    line_items: tuple[InvoiceLineItemInput, ...] = ()


@dataclass(frozen=True)
class InvoiceValidationResult:
    rule_code: str
    severity: str
    message: str
    passed: bool


def validate_invoice(payload: InvoiceValidationInput) -> list[InvoiceValidationResult]:
    results = [
        InvoiceValidationResult(
            rule_code="invoice_number_required",
            severity="error",
            message="Invoice number is required.",
            passed=bool(payload.invoice_number and payload.invoice_number.strip()),
        ),
        InvoiceValidationResult(
            rule_code="supplier_found",
            severity="error",
            message="Supplier must be matched before approval.",
            passed=payload.supplier_found,
        ),
        InvoiceValidationResult(
            rule_code="duplicate_invoice_number",
            severity="error",
            message="Invoice number must be unique for the supplier and organization.",
            passed=not payload.duplicate_invoice_number,
        ),
        InvoiceValidationResult(
            rule_code="total_amount_required",
            severity="error",
            message="Invoice total amount is required.",
            passed=payload.total_amount is not None,
        ),
        # "warning" rules still block auto-approval (see next_status_after_validation)
        # but flag judgement calls — large amounts and low-confidence extractions —
        # rather than hard data errors.
        InvoiceValidationResult(
            rule_code="approval_threshold",
            severity="warning",
            message="Invoice amount exceeds automatic approval threshold.",
            passed=payload.total_amount is None or payload.total_amount <= payload.approval_threshold,
        ),
        InvoiceValidationResult(
            rule_code="extraction_confidence",
            severity="warning",
            message="Extraction confidence is below review threshold.",
            passed=payload.extracted_confidence is None or payload.extracted_confidence >= Decimal("0.8500"),
        ),
    ]

    results.extend(_validate_line_items(payload.line_items))
    return results


def next_status_after_validation(results: list[InvoiceValidationResult]) -> InvoiceStatus:
    # Auto-pass only when every rule passes; any failure (error or warning)
    # sends the invoice to the review queue.
    if all(result.passed for result in results):
        return InvoiceStatus.VALIDATION_PASSED

    return InvoiceStatus.REVIEW_REQUIRED


def _validate_line_items(line_items: tuple[InvoiceLineItemInput, ...]) -> list[InvoiceValidationResult]:
    results: list[InvoiceValidationResult] = []
    for index, item in enumerate(line_items, start=1):
        has_required_description = bool(item.description and item.description.strip())
        results.append(
            InvoiceValidationResult(
                rule_code="line_item_description_required",
                severity="error",
                message=f"Line item {index} requires a description.",
                passed=has_required_description,
            )
        )

        # Can only cross-check the arithmetic when all three figures are present;
        # a missing field is validated by other rules, not here.
        if item.quantity is None or item.unit_price is None or item.line_total is None:
            continue

        expected_total = item.quantity * item.unit_price
        results.append(
            InvoiceValidationResult(
                rule_code="line_item_total_matches",
                severity="error",
                message=f"Line item {index} total must equal quantity multiplied by unit price.",
                passed=expected_total == item.line_total,
            )
        )

    return results
