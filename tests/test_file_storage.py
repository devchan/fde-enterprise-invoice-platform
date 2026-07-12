from __future__ import annotations

import unittest
from io import BytesIO
from tempfile import TemporaryDirectory

from app.core.config import settings
from app.services import file_storage
from app.services.file_storage import InvoiceFileStorageError


class FakeS3Client:
    def __init__(self) -> None:
        self.put_calls: list[dict[str, object]] = []
        self.get_calls: list[dict[str, object]] = []
        self.delete_calls: list[dict[str, object]] = []
        self.object_body = b"stored-pdf"

    def put_object(self, **kwargs: object) -> None:
        self.put_calls.append(kwargs)

    def get_object(self, **kwargs: object) -> dict[str, BytesIO]:
        self.get_calls.append(kwargs)
        return {"Body": BytesIO(self.object_body)}

    def delete_object(self, **kwargs: object) -> None:
        self.delete_calls.append(kwargs)


class FileStorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_backend = settings.object_storage_backend
        self.original_bucket = settings.object_storage_bucket
        self.original_local_path = settings.object_storage_local_path
        self.original_s3_client = file_storage._s3_client

    def tearDown(self) -> None:
        settings.object_storage_backend = self.original_backend
        settings.object_storage_bucket = self.original_bucket
        settings.object_storage_local_path = self.original_local_path
        file_storage._s3_client = self.original_s3_client

    def test_local_storage_round_trip_and_delete(self) -> None:
        with TemporaryDirectory() as storage_root:
            settings.object_storage_backend = "local"
            settings.object_storage_local_path = storage_root
            storage_key = "organizations/org-1/invoices/inv-1/original.pdf"
            content = b"%PDF-1.4\nlocal-storage\n%%EOF"

            file_storage.store_invoice_file(storage_key=storage_key, content=content)

            self.assertEqual(file_storage.read_invoice_file(storage_key=storage_key), content)

            file_storage.delete_invoice_file_if_exists(storage_key=storage_key)
            with self.assertRaises(InvoiceFileStorageError):
                file_storage.read_invoice_file(storage_key=storage_key)

    def test_s3_storage_uses_configured_bucket_and_key(self) -> None:
        fake_client = FakeS3Client()
        settings.object_storage_backend = "s3"
        settings.object_storage_bucket = "invoice-platform-test"
        file_storage._s3_client = lambda: fake_client
        storage_key = "organizations/org-1/invoices/inv-1/original.pdf"
        content = b"%PDF-1.4\ns3-storage\n%%EOF"

        file_storage.store_invoice_file(storage_key=storage_key, content=content)
        result = file_storage.read_invoice_file(storage_key=storage_key)
        file_storage.delete_invoice_file_if_exists(storage_key=storage_key)

        self.assertEqual(result, b"stored-pdf")
        self.assertEqual(
            fake_client.put_calls,
            [{"Bucket": "invoice-platform-test", "Key": storage_key, "Body": content}],
        )
        self.assertEqual(
            fake_client.get_calls,
            [{"Bucket": "invoice-platform-test", "Key": storage_key}],
        )
        self.assertEqual(
            fake_client.delete_calls,
            [{"Bucket": "invoice-platform-test", "Key": storage_key}],
        )

    def test_unsupported_storage_backend_is_rejected(self) -> None:
        settings.object_storage_backend = "ftp"

        with self.assertRaisesRegex(InvoiceFileStorageError, "Unsupported object storage backend"):
            file_storage.store_invoice_file(storage_key="invoice.pdf", content=b"content")


if __name__ == "__main__":
    unittest.main()
