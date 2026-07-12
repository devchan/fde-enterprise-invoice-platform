import importlib.util
import unittest
from decimal import Decimal
from uuid import uuid4

if importlib.util.find_spec("pydantic") is not None:
    from backend.app.services import invoice_extraction as extraction_module
    from backend.app.services.invoice_extraction import (
        DevelopmentInvoiceExtractor,
        ExtractionError,
        ExtractionUsage,
        _estimate_cost,
        _file_data_url,
        _invoice_filename,
        _response_output_text,
        _response_usage,
        parse_extraction_payload,
    )


class InvoiceStub:
    id = uuid4()
    invoice_number = "INV-DEV-1"
    total_amount = Decimal("25.00")
    currency = "USD"


class FakeUsage:
    input_tokens = 1000
    output_tokens = 500


class FakeResponse:
    output_text = '{"invoice_number":"INV-100","confidence_score":"0.9"}'
    usage = FakeUsage()


class FakeContent:
    text = '{"invoice_number":"INV-101","confidence_score":"0.8"}'


class FakeOutput:
    content = [FakeContent()]


class FakeNestedResponse:
    output_text = None
    output = [FakeOutput()]
    usage = None


@unittest.skipIf(importlib.util.find_spec("pydantic") is None, "pydantic is not installed")
class InvoiceExtractionTest(unittest.TestCase):
    def test_strict_extraction_payload_parses_valid_data(self) -> None:
        payload = parse_extraction_payload(
            {
                "invoice_number": "INV-100",
                "supplier_name": "Supplier A",
                "invoice_date": None,
                "total_amount": "120.00",
                "currency": "USD",
                "confidence_score": "0.9100",
                "line_items": [
                    {
                        "description": "Consulting",
                        "quantity": "2",
                        "unit_price": "60.00",
                        "line_total": "120.00",
                    }
                ],
            }
        )

        self.assertEqual(payload.invoice_number, "INV-100")
        self.assertEqual(payload.total_amount, Decimal("120.00"))
        self.assertEqual(payload.line_items[0].line_total, Decimal("120.00"))

    def test_strict_extraction_payload_rejects_extra_fields(self) -> None:
        with self.assertRaises(ExtractionError):
            parse_extraction_payload(
                {
                    "invoice_number": "INV-100",
                    "currency": "USD",
                    "confidence_score": "0.9100",
                    "unexpected": "not allowed",
                }
            )

    def test_development_extractor_uses_invoice_metadata(self) -> None:
        result = DevelopmentInvoiceExtractor().extract(
            invoice=InvoiceStub(),
            file_bytes=b"%PDF-1.4",
        )

        self.assertEqual(result.payload.invoice_number, "INV-DEV-1")
        self.assertEqual(result.payload.total_amount, Decimal("25.00"))
        self.assertEqual(result.payload.confidence_score, Decimal("0.8000"))
        self.assertEqual(result.model_name, "development-extractor")

    def test_response_output_text_uses_direct_output_text(self) -> None:
        self.assertEqual(_response_output_text(FakeResponse()), FakeResponse.output_text)

    def test_response_output_text_falls_back_to_nested_content(self) -> None:
        self.assertEqual(_response_output_text(FakeNestedResponse()), FakeContent.text)

    def test_response_usage_extracts_tokens_and_estimated_cost(self) -> None:
        previous_input_cost = extraction_module.settings.openai_input_cost_per_million_tokens
        previous_output_cost = extraction_module.settings.openai_output_cost_per_million_tokens
        extraction_module.settings.openai_input_cost_per_million_tokens = "2.50"
        extraction_module.settings.openai_output_cost_per_million_tokens = "10.00"
        try:
            usage = _response_usage(FakeResponse())
        finally:
            extraction_module.settings.openai_input_cost_per_million_tokens = previous_input_cost
            extraction_module.settings.openai_output_cost_per_million_tokens = previous_output_cost

        self.assertEqual(
            usage,
            ExtractionUsage(
                input_tokens=1000,
                output_tokens=500,
                estimated_cost=Decimal("0.007500"),
            ),
        )

    def test_estimate_cost_returns_none_without_usage(self) -> None:
        self.assertIsNone(_estimate_cost(input_tokens=None, output_tokens=None))

    def test_file_data_url_includes_mime_type_and_base64_payload(self) -> None:
        self.assertEqual(
            _file_data_url(file_bytes=b"%PDF", mime_type="application/pdf"),
            "data:application/pdf;base64,JVBERg==",
        )

    def test_invoice_filename_uses_mime_extension(self) -> None:
        self.assertEqual(_invoice_filename(invoice_id="123", mime_type="image/png"), "invoice-123.png")


if __name__ == "__main__":
    unittest.main()
