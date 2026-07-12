"""Validation of uploaded invoice files before they are accepted for storage.

Uses strict allowlists for both extension and MIME type (rather than blocking
known-bad values) so anything unexpected is rejected by default.
"""

from dataclasses import dataclass
from pathlib import Path

ALLOWED_INVOICE_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}
ALLOWED_INVOICE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


class InvalidInvoiceFileError(ValueError):
    pass


@dataclass(frozen=True)
class InvoiceFileValidationResult:
    filename: str
    extension: str
    mime_type: str
    file_size: int


def validate_invoice_file(
    *,
    filename: str,
    mime_type: str | None,
    file_size: int,
    max_bytes: int,
) -> InvoiceFileValidationResult:
    if not filename or not filename.strip():
        raise InvalidInvoiceFileError("Invoice file requires a filename.")

    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_INVOICE_EXTENSIONS:
        raise InvalidInvoiceFileError("Invoice file extension is not allowed.")

    if mime_type not in ALLOWED_INVOICE_MIME_TYPES:
        raise InvalidInvoiceFileError("Invoice file MIME type is not allowed.")

    if file_size <= 0:
        raise InvalidInvoiceFileError("Invoice file cannot be empty.")

    if file_size > max_bytes:
        raise InvalidInvoiceFileError("Invoice file exceeds the maximum allowed size.")

    return InvoiceFileValidationResult(
        # Strip any directory components from the client-supplied name to guard
        # against path traversal; only the bare basename is retained.
        filename=Path(filename).name,
        extension=extension,
        mime_type=mime_type,
        file_size=file_size,
    )
