"""Unit tests for the AI pipeline optimizations: per-field confidence routing,
auto-approval decisions, model-tiering usage aggregation, anomaly detection,
validation explanations, NL search parsing, and image preprocessing."""

import importlib.util
import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

# Import everything through the `app.` package (the path the services
# themselves use) so mutating `settings` in tests affects the exact object the
# code under test reads — `backend.app.*` would be a second module instance
# with its own Settings.
REQUIRED_MODULES = ("pydantic", "sqlalchemy", "structlog", "app")
HAS_REQUIRED_MODULES = all(importlib.util.find_spec(module) is not None for module in REQUIRED_MODULES)

if HAS_REQUIRED_MODULES:
    from app.core.config import settings
    from app.services.invoice_anomaly import _detect_amount_outlier
    from app.services.invoice_auto_approval import auto_approval_decision
    from app.services.invoice_extraction import (
        DevelopmentInvoiceExtractor,
        ExtractedFieldConfidences,
        ExtractedInvoicePayload,
        ExtractionUsage,
        _combined_usage,
        minimum_field_confidence,
        parse_extraction_payload,
    )
    from app.services.invoice_nl_search import InvoiceSearchFilters, _parse_fallback
    from app.services.invoice_validation import (
        InvoiceValidationInput,
        next_status_after_validation,
        validate_invoice,
    )
    from app.services.invoice_workflow import InvoiceStatus
    from app.services.validation_explanations import (
        _TEMPLATES,
        explain_validation_failures,
    )


class InvoiceStub:
    def __init__(self, *, total_amount: Decimal | None = Decimal("25.00")) -> None:
        self.id = uuid4()
        self.organization_id = uuid4()
        self.supplier_id = uuid4()
        self.invoice_number = "INV-DEV-1"
        self.total_amount = total_amount
        self.currency = "USD"
        self.status = InvoiceStatus.VALIDATION_PASSED.value


def _payload(
    *,
    confidence: str = "0.95",
    field_confidences: dict | None = None,
) -> "ExtractedInvoicePayload":
    return ExtractedInvoicePayload(
        invoice_number="INV-1",
        total_amount=Decimal("100.00"),
        currency="USD",
        confidence_score=Decimal(confidence),
        field_confidences=(
            ExtractedFieldConfidences(**field_confidences) if field_confidences is not None else None
        ),
    )


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend dependencies are not installed")
class FieldConfidenceValidationTest(unittest.TestCase):
    def _base_input(self, **overrides) -> "InvoiceValidationInput":
        defaults = dict(
            invoice_number="INV-100",
            supplier_found=True,
            total_amount=Decimal("120.00"),
            extracted_confidence=Decimal("0.9500"),
        )
        defaults.update(overrides)
        return InvoiceValidationInput(**defaults)

    def test_low_field_confidence_routes_to_review(self) -> None:
        results = validate_invoice(
            self._base_input(
                field_confidences={"total_amount": Decimal("0.40"), "currency": Decimal("0.99")}
            )
        )

        failures = [result for result in results if not result.passed]
        self.assertEqual([failure.rule_code for failure in failures], ["field_confidence_low"])
        self.assertIn("total_amount", failures[0].message)
        self.assertEqual(next_status_after_validation(results), InvoiceStatus.REVIEW_REQUIRED)

    def test_confident_fields_do_not_add_results(self) -> None:
        results = validate_invoice(
            self._base_input(field_confidences={"total_amount": Decimal("0.95")})
        )

        self.assertTrue(all(result.passed for result in results))
        self.assertNotIn("field_confidence_low", [result.rule_code for result in results])

    def test_absent_field_confidences_skip_the_rule(self) -> None:
        results = validate_invoice(self._base_input(field_confidences=None))

        self.assertEqual(next_status_after_validation(results), InvoiceStatus.VALIDATION_PASSED)


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend dependencies are not installed")
class AutoApprovalDecisionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_enabled = settings.auto_approval_enabled
        self._previous_threshold = settings.auto_approval_min_confidence
        settings.auto_approval_enabled = True
        settings.auto_approval_min_confidence = "0.92"

    def tearDown(self) -> None:
        settings.auto_approval_enabled = self._previous_enabled
        settings.auto_approval_min_confidence = self._previous_threshold

    def test_approves_confident_validated_invoice(self) -> None:
        approve, reason = auto_approval_decision(
            status=InvoiceStatus.VALIDATION_PASSED,
            payload=_payload(confidence="0.97", field_confidences={"total_amount": "0.95"}),
        )

        self.assertTrue(approve)
        self.assertEqual(reason, "confidence_met")

    def test_rejects_when_disabled(self) -> None:
        settings.auto_approval_enabled = False
        approve, reason = auto_approval_decision(
            status=InvoiceStatus.VALIDATION_PASSED,
            payload=_payload(confidence="0.99"),
        )

        self.assertFalse(approve)
        self.assertEqual(reason, "auto_approval_disabled")

    def test_rejects_wrong_status(self) -> None:
        approve, reason = auto_approval_decision(
            status=InvoiceStatus.REVIEW_REQUIRED,
            payload=_payload(confidence="0.99"),
        )

        self.assertFalse(approve)
        self.assertTrue(reason.startswith("status_not_eligible"))

    def test_rejects_low_overall_confidence(self) -> None:
        approve, reason = auto_approval_decision(
            status=InvoiceStatus.VALIDATION_PASSED,
            payload=_payload(confidence="0.80"),
        )

        self.assertFalse(approve)
        self.assertEqual(reason, "overall_confidence_below_threshold")

    def test_one_weak_field_blocks_auto_approval(self) -> None:
        approve, reason = auto_approval_decision(
            status=InvoiceStatus.VALIDATION_PASSED,
            payload=_payload(
                confidence="0.99",
                field_confidences={"total_amount": "0.99", "invoice_number": "0.50"},
            ),
        )

        self.assertFalse(approve)
        self.assertEqual(reason, "field_confidence_below_threshold")


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend dependencies are not installed")
class ExtractionHelpersTest(unittest.TestCase):
    def test_minimum_field_confidence_ignores_nulls(self) -> None:
        payload = _payload(field_confidences={"total_amount": "0.90", "invoice_date": None})

        self.assertEqual(minimum_field_confidence(payload), Decimal("0.90"))

    def test_minimum_field_confidence_none_without_confidences(self) -> None:
        self.assertIsNone(minimum_field_confidence(_payload(field_confidences=None)))

    def test_combined_usage_sums_tokens_and_cost(self) -> None:
        combined = _combined_usage(
            ExtractionUsage(input_tokens=100, output_tokens=50, estimated_cost=Decimal("0.01")),
            ExtractionUsage(input_tokens=200, output_tokens=None, estimated_cost=Decimal("0.02")),
        )

        self.assertEqual(combined.input_tokens, 300)
        self.assertEqual(combined.output_tokens, 50)
        self.assertEqual(combined.estimated_cost, Decimal("0.03"))

    def test_payload_accepts_category_and_field_confidences(self) -> None:
        payload = parse_extraction_payload(
            {
                "invoice_number": "INV-100",
                "supplier_name": None,
                "invoice_date": None,
                "total_amount": "120.00",
                "currency": "USD",
                "confidence_score": "0.9100",
                "field_confidences": {
                    "invoice_number": "0.95",
                    "supplier_name": None,
                    "invoice_date": None,
                    "total_amount": "0.90",
                    "currency": "0.99",
                },
                "line_items": [
                    {
                        "description": "Laptop",
                        "quantity": "1",
                        "unit_price": "120.00",
                        "line_total": "120.00",
                        "category": "goods",
                    }
                ],
            }
        )

        self.assertEqual(payload.line_items[0].category, "goods")
        self.assertEqual(payload.field_confidences.total_amount, Decimal("0.90"))

    def test_development_extractor_reports_confidences_and_category(self) -> None:
        result = DevelopmentInvoiceExtractor().extract(invoice=InvoiceStub(), file_bytes=b"%PDF-1.4")

        self.assertIsNotNone(result.payload.field_confidences)
        self.assertEqual(result.payload.line_items[0].category, "other")


class FakeScalarDb:
    def __init__(self, values: list) -> None:
        self._values = values

    def scalars(self, _query):
        return list(self._values)


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend dependencies are not installed")
class AmountAnomalyTest(unittest.TestCase):
    def test_flags_amount_far_from_supplier_history(self) -> None:
        invoice = InvoiceStub(total_amount=Decimal("50000.00"))
        history = [Decimal("100.00"), Decimal("110.00"), Decimal("95.00"), Decimal("105.00")]

        flags = _detect_amount_outlier(FakeScalarDb(history), invoice=invoice)

        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].rule_code, "amount_anomaly")

    def test_normal_amount_is_not_flagged(self) -> None:
        invoice = InvoiceStub(total_amount=Decimal("102.00"))
        history = [Decimal("100.00"), Decimal("110.00"), Decimal("95.00"), Decimal("105.00")]

        self.assertEqual(_detect_amount_outlier(FakeScalarDb(history), invoice=invoice), [])

    def test_insufficient_history_is_silent(self) -> None:
        invoice = InvoiceStub(total_amount=Decimal("50000.00"))

        self.assertEqual(_detect_amount_outlier(FakeScalarDb([Decimal("100.00")]), invoice=invoice), [])

    def test_identical_history_flags_only_different_amounts(self) -> None:
        history = [Decimal("100.00")] * 4

        same = InvoiceStub(total_amount=Decimal("100.00"))
        different = InvoiceStub(total_amount=Decimal("250.00"))

        self.assertEqual(_detect_amount_outlier(FakeScalarDb(history), invoice=same), [])
        self.assertEqual(len(_detect_amount_outlier(FakeScalarDb(history), invoice=different)), 1)


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend dependencies are not installed")
class ValidationExplanationsTest(unittest.TestCase):
    class FailureStub:
        def __init__(self, rule_code: str) -> None:
            self.rule_code = rule_code
            self.message = "failed"

    def test_every_known_rule_has_a_template(self) -> None:
        known_rules = {
            "invoice_number_required",
            "supplier_found",
            "duplicate_invoice_number",
            "total_amount_required",
            "approval_threshold",
            "extraction_confidence",
            "field_confidence_low",
            "line_item_description_required",
            "line_item_total_matches",
            "amount_anomaly",
            "near_duplicate_similarity",
        }

        self.assertTrue(known_rules.issubset(_TEMPLATES.keys()))

    def test_failures_get_explanations_including_unknown_rules(self) -> None:
        failures = [self.FailureStub("total_amount_required"), self.FailureStub("brand_new_rule")]

        explanations = explain_validation_failures(failures)

        self.assertEqual(len(explanations), 2)
        for failure in failures:
            explanation, suggested_fix = explanations[id(failure)]
            self.assertTrue(explanation)
            self.assertTrue(suggested_fix)


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend dependencies are not installed")
class NLSearchFallbackParserTest(unittest.TestCase):
    TODAY = date(2026, 7, 17)

    def test_parses_status_amount_and_supplier(self) -> None:
        filters = _parse_fallback("approved acme invoices over $10,000", today=self.TODAY)

        self.assertEqual(filters.status, InvoiceStatus.APPROVED)
        self.assertEqual(filters.min_total, Decimal("10000"))
        self.assertEqual(filters.supplier_name_contains, "acme")

    def test_parses_k_magnitude_and_under(self) -> None:
        filters = _parse_fallback("invoices under 5k", today=self.TODAY)

        self.assertEqual(filters.max_total, Decimal("5000"))

    def test_parses_month_into_date_range(self) -> None:
        filters = _parse_fallback("invoices from june", today=self.TODAY)

        self.assertEqual(filters.date_from, date(2026, 6, 1))
        self.assertEqual(filters.date_to, date(2026, 6, 30))

    def test_future_month_resolves_to_previous_year(self) -> None:
        filters = _parse_fallback("invoices from december", today=self.TODAY)

        self.assertEqual(filters.date_from, date(2025, 12, 1))

    def test_parses_currency_and_review_status(self) -> None:
        filters = _parse_fallback("eur invoices needing review", today=self.TODAY)

        self.assertEqual(filters.currency, "EUR")
        self.assertEqual(filters.status, InvoiceStatus.REVIEW_REQUIRED)

    def test_plain_query_returns_default_filters(self) -> None:
        filters = _parse_fallback("show me all invoices", today=self.TODAY)

        self.assertEqual(
            filters.model_dump(exclude_none=True),
            InvoiceSearchFilters().model_dump(exclude_none=True),
        )


@unittest.skipIf(
    not HAS_REQUIRED_MODULES or importlib.util.find_spec("PIL") is None,
    "backend dependencies or Pillow are not installed",
)
class ImagePreprocessingTest(unittest.TestCase):
    def _png_bytes(self, width: int, height: int) -> bytes:
        import io

        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (width, height), color=(200, 10, 10)).save(buffer, format="PNG")
        return buffer.getvalue()

    def test_oversized_image_is_downscaled(self) -> None:
        import io

        from PIL import Image

        from app.services.file_preprocessing import preprocess_for_extraction

        previous = settings.extraction_image_max_dimension
        settings.extraction_image_max_dimension = 512
        try:
            processed = preprocess_for_extraction(
                file_bytes=self._png_bytes(2048, 1024), mime_type="image/png"
            )
        finally:
            settings.extraction_image_max_dimension = previous

        width, height = Image.open(io.BytesIO(processed)).size
        self.assertEqual((width, height), (512, 256))

    def test_small_image_and_pdfs_pass_through(self) -> None:
        from app.services.file_preprocessing import preprocess_for_extraction

        small = self._png_bytes(100, 100)
        self.assertIs(preprocess_for_extraction(file_bytes=small, mime_type="image/png"), small)

        pdf = b"%PDF-1.4"
        self.assertIs(preprocess_for_extraction(file_bytes=pdf, mime_type="application/pdf"), pdf)


if __name__ == "__main__":
    unittest.main()
