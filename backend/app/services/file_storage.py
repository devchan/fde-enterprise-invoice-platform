"""Storage abstraction for original invoice files.

A single ``StorageBackend`` protocol hides whether files live on the local
filesystem (dev/tests) or in an S3-compatible object store (production); the
backend is chosen at call time from settings so no code outside this module
needs to know which one is active.
"""

from pathlib import Path
from typing import Protocol
from uuid import UUID

from app.core.config import settings


class InvoiceFileStorageError(RuntimeError):
    pass


class StorageBackend(Protocol):
    def store(self, *, storage_key: str, content: bytes) -> None:
        ...

    def read(self, *, storage_key: str) -> bytes:
        ...

    def delete_if_exists(self, *, storage_key: str) -> None:
        ...


def build_invoice_storage_key(
    *,
    organization_id: UUID,
    invoice_id: UUID,
    extension: str,
) -> str:
    # Namespacing the key by organization then invoice keeps tenants isolated
    # and makes keys predictable/reconstructable from row data alone.
    normalized_extension = extension.lower().lstrip(".")
    return f"organizations/{organization_id}/invoices/{invoice_id}/original.{normalized_extension}"


def store_invoice_file(*, storage_key: str, content: bytes) -> None:
    _storage_backend().store(storage_key=storage_key, content=content)


def read_invoice_file(*, storage_key: str) -> bytes:
    return _storage_backend().read(storage_key=storage_key)


def delete_invoice_file_if_exists(*, storage_key: str) -> None:
    _storage_backend().delete_if_exists(storage_key=storage_key)


def _storage_root() -> Path:
    return Path(settings.object_storage_local_path).resolve()


def _storage_backend() -> StorageBackend:
    # Resolve the backend per call (not cached) so a settings change in tests
    # or config reload takes effect immediately.
    backend = settings.object_storage_backend.strip().lower()
    if backend == "local":
        return LocalStorageBackend()
    if backend == "s3":
        return S3StorageBackend()
    raise InvoiceFileStorageError(f"Unsupported object storage backend: {settings.object_storage_backend}")


class LocalStorageBackend:
    def store(self, *, storage_key: str, content: bytes) -> None:
        target = _storage_root() / storage_key
        target.parent.mkdir(parents=True, exist_ok=True)

        # Write to a temp file then atomically rename into place so a crash
        # mid-write can never leave a partially written invoice at the real key.
        temporary_target = target.with_suffix(f"{target.suffix}.tmp")
        try:
            temporary_target.write_bytes(content)
            temporary_target.replace(target)
        except OSError as exc:
            raise InvoiceFileStorageError("Failed to store invoice file.") from exc

    def read(self, *, storage_key: str) -> bytes:
        target = _storage_root() / storage_key
        try:
            return target.read_bytes()
        except OSError as exc:
            raise InvoiceFileStorageError("Failed to read invoice file.") from exc

    def delete_if_exists(self, *, storage_key: str) -> None:
        target = _storage_root() / storage_key
        try:
            # Best-effort cleanup: a missing file or unlink error must not fail
            # the caller (e.g. rolling back an upload).
            target.unlink(missing_ok=True)
        except OSError:
            pass


class S3StorageBackend:
    def store(self, *, storage_key: str, content: bytes) -> None:
        try:
            _s3_client().put_object(
                Bucket=settings.object_storage_bucket,
                Key=storage_key,
                Body=content,
            )
        # boto3/botocore raise a wide range of exception types; collapse them
        # all into the storage error so callers have one type to handle.
        except Exception as exc:
            raise InvoiceFileStorageError("Failed to store invoice file in object storage.") from exc

    def read(self, *, storage_key: str) -> bytes:
        try:
            response = _s3_client().get_object(
                Bucket=settings.object_storage_bucket,
                Key=storage_key,
            )
            return response["Body"].read()
        except Exception as exc:
            raise InvoiceFileStorageError("Failed to read invoice file from object storage.") from exc

    def delete_if_exists(self, *, storage_key: str) -> None:
        try:
            _s3_client().delete_object(
                Bucket=settings.object_storage_bucket,
                Key=storage_key,
            )
        # Deletion is best-effort cleanup, so swallow any backend error.
        except Exception:
            pass


def _s3_client():
    # Import boto3 lazily so deployments using only the local backend are not
    # forced to install it.
    try:
        import boto3
    except ImportError as exc:
        raise InvoiceFileStorageError("S3 object storage requires the boto3 package.") from exc

    return boto3.client(
        "s3",
        endpoint_url=settings.object_storage_endpoint_url or None,
        region_name=settings.object_storage_region,
        aws_access_key_id=settings.object_storage_access_key_id or None,
        aws_secret_access_key=settings.object_storage_secret_access_key or None,
    )
