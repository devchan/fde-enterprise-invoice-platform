"""Controls access to stored invoice files two ways: authenticated,
organization-scoped lookups, and short-lived HMAC-signed download links that
grant access without a session (e.g. for a browser fetch or third party)."""

import hashlib
import hmac
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.invoice import Invoice, InvoiceFile


class InvoiceFileAccessError(ValueError):
    pass


class InvoiceFileNotFoundError(InvoiceFileAccessError):
    pass


class InvoiceFileSignatureError(InvoiceFileAccessError):
    pass


@dataclass(frozen=True)
class SignedInvoiceFileDownload:
    expires_at: int
    signature: str


def get_invoice_file_for_organization(
    db: Session,
    *,
    invoice_id: UUID,
    file_id: UUID,
    organization_id: UUID,
) -> InvoiceFile:
    # Join through Invoice and filter on organization_id so one tenant can never
    # fetch another tenant's file even with a valid invoice/file id pair.
    invoice_file = db.scalar(
        select(InvoiceFile)
        .join(Invoice)
        .where(Invoice.id == invoice_id)
        .where(InvoiceFile.id == file_id)
        .where(InvoiceFile.invoice_id == invoice_id)
        .where(Invoice.organization_id == organization_id)
    )
    if invoice_file is None:
        raise InvoiceFileNotFoundError("Invoice file was not found.")

    return invoice_file


def get_invoice_file_for_signed_download(
    db: Session,
    *,
    invoice_id: UUID,
    file_id: UUID,
    expires_at: int,
    signature: str,
) -> InvoiceFile:
    invoice_file = db.scalar(
        select(InvoiceFile)
        .where(InvoiceFile.id == file_id)
        .where(InvoiceFile.invoice_id == invoice_id)
    )
    if invoice_file is None:
        raise InvoiceFileNotFoundError("Invoice file was not found.")

    validate_invoice_file_download_signature(
        invoice_id=invoice_id,
        file_id=file_id,
        storage_key=invoice_file.storage_key,
        expires_at=expires_at,
        signature=signature,
    )
    return invoice_file


def sign_invoice_file_download(
    *,
    invoice_id: UUID,
    file_id: UUID,
    storage_key: str,
    now: int | None = None,
) -> SignedInvoiceFileDownload:
    # `now` is injectable purely so tests can produce deterministic signatures.
    issued_at = int(time.time()) if now is None else now
    expires_at = issued_at + settings.invoice_file_download_url_ttl_seconds
    return SignedInvoiceFileDownload(
        expires_at=expires_at,
        signature=_download_signature(
            invoice_id=invoice_id,
            file_id=file_id,
            storage_key=storage_key,
            expires_at=expires_at,
        ),
    )


def validate_invoice_file_download_signature(
    *,
    invoice_id: UUID,
    file_id: UUID,
    storage_key: str,
    expires_at: int,
    signature: str,
    now: int | None = None,
) -> None:
    # Check expiry before recomputing the signature so an expired link fails
    # fast with a clear reason.
    current_time = int(time.time()) if now is None else now
    if expires_at <= current_time:
        raise InvoiceFileSignatureError("Invoice file download URL has expired.")

    expected_signature = _download_signature(
        invoice_id=invoice_id,
        file_id=file_id,
        storage_key=storage_key,
        expires_at=expires_at,
    )
    # Constant-time compare to avoid leaking signature bytes via timing.
    if not hmac.compare_digest(signature, expected_signature):
        raise InvoiceFileSignatureError("Invoice file download signature is invalid.")


def _download_signature(
    *,
    invoice_id: UUID,
    file_id: UUID,
    storage_key: str,
    expires_at: int,
) -> str:
    # Bind the signature to all identifying fields + expiry so a link cannot be
    # replayed against a different file or with a tampered expiry. Reuses the JWT
    # secret as the shared HMAC key.
    message = f"{invoice_id}:{file_id}:{storage_key}:{expires_at}".encode("utf-8")
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
