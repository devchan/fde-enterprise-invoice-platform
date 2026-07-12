import unittest

from backend.app.services.invoice_workflow import InvoiceStatus, transition_invoice_status


class InvoiceWorkflowTest(unittest.TestCase):
    def test_uploaded_invoice_can_be_queued(self) -> None:
        self.assertEqual(
            transition_invoice_status(InvoiceStatus.UPLOADED, InvoiceStatus.QUEUED),
            InvoiceStatus.QUEUED,
        )

    def test_review_required_invoice_can_be_approved(self) -> None:
        self.assertEqual(
            transition_invoice_status(InvoiceStatus.REVIEW_REQUIRED, InvoiceStatus.APPROVED),
            InvoiceStatus.APPROVED,
        )

    def test_approved_invoice_is_terminal(self) -> None:
        with self.assertRaises(ValueError):
            transition_invoice_status(InvoiceStatus.APPROVED, InvoiceStatus.PROCESSING)

    def test_failed_invoice_can_be_requeued(self) -> None:
        self.assertEqual(
            transition_invoice_status(InvoiceStatus.FAILED, InvoiceStatus.QUEUED),
            InvoiceStatus.QUEUED,
        )


if __name__ == "__main__":
    unittest.main()
