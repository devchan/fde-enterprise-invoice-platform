import unittest
from decimal import Decimal

from backend.app.services.invoice_validation import (
    InvoiceLineItemInput,
    InvoiceValidationInput,
    next_status_after_validation,
    validate_invoice,
)
from backend.app.services.invoice_workflow import InvoiceStatus


class InvoiceValidationTest(unittest.TestCase):
    def test_valid_invoice_can_pass_validation(self) -> None:
        results = validate_invoice(
            InvoiceValidationInput(
                invoice_number="INV-100",
                supplier_found=True,
                total_amount=Decimal("120.00"),
                extracted_confidence=Decimal("0.9500"),
                line_items=(
                    InvoiceLineItemInput(
                        description="Consulting",
                        quantity=Decimal("2"),
                        unit_price=Decimal("60.00"),
                        line_total=Decimal("120.00"),
                    ),
                ),
            )
        )

        self.assertTrue(all(result.passed for result in results))
        self.assertEqual(next_status_after_validation(results), InvoiceStatus.VALIDATION_PASSED)

    def test_missing_supplier_routes_invoice_to_review(self) -> None:
        results = validate_invoice(
            InvoiceValidationInput(
                invoice_number="INV-101",
                supplier_found=False,
                total_amount=Decimal("120.00"),
            )
        )

        supplier_result = next(result for result in results if result.rule_code == "supplier_found")
        self.assertFalse(supplier_result.passed)
        self.assertEqual(next_status_after_validation(results), InvoiceStatus.REVIEW_REQUIRED)

    def test_duplicate_invoice_number_routes_invoice_to_review(self) -> None:
        results = validate_invoice(
            InvoiceValidationInput(
                invoice_number="INV-102",
                supplier_found=True,
                total_amount=Decimal("120.00"),
                duplicate_invoice_number=True,
            )
        )

        duplicate_result = next(result for result in results if result.rule_code == "duplicate_invoice_number")
        self.assertFalse(duplicate_result.passed)
        self.assertEqual(next_status_after_validation(results), InvoiceStatus.REVIEW_REQUIRED)

    def test_line_item_total_mismatch_routes_invoice_to_review(self) -> None:
        results = validate_invoice(
            InvoiceValidationInput(
                invoice_number="INV-103",
                supplier_found=True,
                total_amount=Decimal("120.00"),
                line_items=(
                    InvoiceLineItemInput(
                        description="Consulting",
                        quantity=Decimal("2"),
                        unit_price=Decimal("60.00"),
                        line_total=Decimal("100.00"),
                    ),
                ),
            )
        )

        line_total_result = next(result for result in results if result.rule_code == "line_item_total_matches")
        self.assertFalse(line_total_result.passed)
        self.assertEqual(next_status_after_validation(results), InvoiceStatus.REVIEW_REQUIRED)


if __name__ == "__main__":
    unittest.main()
