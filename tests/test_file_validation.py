import unittest

from backend.app.services.file_validation import InvalidInvoiceFileError, validate_invoice_file


class FileValidationTest(unittest.TestCase):
    def test_pdf_invoice_file_is_allowed(self) -> None:
        result = validate_invoice_file(
            filename="invoice.pdf",
            mime_type="application/pdf",
            file_size=1024,
            max_bytes=2048,
        )

        self.assertEqual(result.filename, "invoice.pdf")
        self.assertEqual(result.extension, ".pdf")
        self.assertEqual(result.mime_type, "application/pdf")
        self.assertEqual(result.file_size, 1024)

    def test_disallowed_extension_is_rejected(self) -> None:
        with self.assertRaises(InvalidInvoiceFileError):
            validate_invoice_file(
                filename="invoice.exe",
                mime_type="application/pdf",
                file_size=1024,
                max_bytes=2048,
            )

    def test_disallowed_mime_type_is_rejected(self) -> None:
        with self.assertRaises(InvalidInvoiceFileError):
            validate_invoice_file(
                filename="invoice.pdf",
                mime_type="application/octet-stream",
                file_size=1024,
                max_bytes=2048,
            )

    def test_oversized_file_is_rejected(self) -> None:
        with self.assertRaises(InvalidInvoiceFileError):
            validate_invoice_file(
                filename="invoice.pdf",
                mime_type="application/pdf",
                file_size=4096,
                max_bytes=2048,
            )


if __name__ == "__main__":
    unittest.main()
