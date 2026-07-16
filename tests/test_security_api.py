from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import time
import unittest
from decimal import Decimal
from uuid import uuid4

REQUIRED_MODULES = ("fastapi", "sqlalchemy", "pydantic")
HAS_REQUIRED_MODULES = all(importlib.util.find_spec(module) is not None for module in REQUIRED_MODULES)

if HAS_REQUIRED_MODULES:
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.main import app
    from app.models.audit import AuditLog
    from app.models.invoice import Invoice, InvoiceFile
    from app.models.organization import Organization
    from app.models.processing import ProcessingJob
    from app.models.supplier import Supplier
    from app.models.user import User
    from app.services.invoice_extraction import ExtractionError, TransientExtractionError
    from app.services.invoice_workflow import InvoiceStatus
    from app.services.processing_jobs import (
        ProcessingJobStatus,
        ProcessingJobType,
        is_retryable_processing_error,
        record_processing_job_failure,
    )


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend integration dependencies are not installed")
class SecurityApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.db = SessionLocal()
        self.org = Organization(name=f"Security API Org {uuid4()}")
        self.other_org = Organization(name=f"Other Security API Org {uuid4()}")
        self.db.add_all([self.org, self.other_org])
        self.db.flush()
        self.admin = User(
            organization_id=self.org.id,
            email=f"admin-{uuid4()}@example.com",
            role="admin",
        )
        self.uploader = User(
            organization_id=self.org.id,
            email=f"uploader-{uuid4()}@example.com",
            role="uploader",
        )
        self.reviewer = User(
            organization_id=self.org.id,
            email=f"reviewer-{uuid4()}@example.com",
            role="reviewer",
        )
        self.other_admin = User(
            organization_id=self.other_org.id,
            email=f"other-admin-{uuid4()}@example.com",
            role="admin",
        )
        self.db.add_all([self.admin, self.uploader, self.reviewer, self.other_admin])
        self.other_supplier = Supplier(
            organization_id=self.other_org.id,
            name=f"Other Supplier {uuid4()}",
        )
        self.db.add(self.other_supplier)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_create_invoice_requires_authentication(self) -> None:
        response = self.client.post(
            "/api/v1/invoices",
            json={
                "invoice_number": f"INV-{uuid4()}",
                "currency": "USD",
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "authentication_required")

    def test_create_invoice_uses_authenticated_user_tenant_and_actor(self) -> None:
        response = self.client.post(
            "/api/v1/invoices",
            headers=self._auth_headers(self.uploader),
            json={
                "organization_id": str(self.other_org.id),
                "uploaded_by": str(self.other_admin.id),
                "invoice_number": f"INV-{uuid4()}",
                "total_amount": "42.00",
                "currency": "usd",
            },
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["organization_id"], str(self.org.id))
        self.db.expire_all()
        invoice = self.db.get(Invoice, body["invoice_id"])
        self.assertEqual(invoice.organization_id, self.org.id)
        self.assertEqual(invoice.uploaded_by, self.uploader.id)

    def test_create_invoice_rejects_cross_tenant_supplier(self) -> None:
        response = self.client.post(
            "/api/v1/invoices",
            headers=self._auth_headers(self.uploader),
            json={
                "supplier_id": str(self.other_supplier.id),
                "invoice_number": f"INV-{uuid4()}",
                "currency": "USD",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "supplier_not_found")

    def test_upload_invoice_uses_authenticated_user_tenant_and_actor(self) -> None:
        response = self.client.post(
            "/api/v1/invoices/upload",
            headers=self._auth_headers(self.uploader),
            data={
                "organization_id": str(self.other_org.id),
                "uploaded_by": str(self.other_admin.id),
                "invoice_number": f"UPLOAD-{uuid4()}",
                "currency": "USD",
            },
            files={
                "file": (
                    "invoice.pdf",
                    f"%PDF-1.4\n{uuid4()}\n%%EOF".encode("utf-8"),
                    "application/pdf",
                )
            },
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["organization_id"], str(self.org.id))
        self.db.expire_all()
        invoice = self.db.get(Invoice, body["invoice_id"])
        self.assertEqual(invoice.organization_id, self.org.id)
        self.assertEqual(invoice.uploaded_by, self.uploader.id)

    def test_upload_invoice_rejects_cross_tenant_supplier(self) -> None:
        response = self.client.post(
            "/api/v1/invoices/upload",
            headers=self._auth_headers(self.uploader),
            data={
                "supplier_id": str(self.other_supplier.id),
                "invoice_number": f"UPLOAD-{uuid4()}",
                "currency": "USD",
            },
            files={
                "file": (
                    "invoice.pdf",
                    f"%PDF-1.4\n{uuid4()}\n%%EOF".encode("utf-8"),
                    "application/pdf",
                )
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "supplier_not_found")

    def test_signed_file_download_url_streams_uploaded_file(self) -> None:
        file_content = f"%PDF-1.4\nsigned-download-{uuid4()}\n%%EOF".encode("utf-8")
        upload_response = self.client.post(
            "/api/v1/invoices/upload",
            headers=self._auth_headers(self.uploader),
            data={
                "invoice_number": f"UPLOAD-{uuid4()}",
                "currency": "USD",
            },
            files={"file": ("invoice.pdf", file_content, "application/pdf")},
        )
        self.assertEqual(upload_response.status_code, 201)
        invoice_id = upload_response.json()["invoice_id"]
        invoice_file = self._first_invoice_file(invoice_id)

        url_response = self.client.get(
            f"/api/v1/invoices/{invoice_id}/files/{invoice_file.id}/download-url",
            headers=self._auth_headers(self.uploader),
        )

        self.assertEqual(url_response.status_code, 200)
        download_url = url_response.json()["download_url"]
        download_response = self.client.get(download_url)
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response.content, file_content)
        self.assertEqual(download_response.headers["content-type"], "application/pdf")

    def test_cross_tenant_file_download_url_returns_not_found(self) -> None:
        other_invoice = self._create_invoice(
            status=InvoiceStatus.QUEUED,
            organization_id=self.other_org.id,
            uploaded_by=self.other_admin.id,
        )
        other_file = self._create_invoice_file(invoice_id=other_invoice.id)

        response = self.client.get(
            f"/api/v1/invoices/{other_invoice.id}/files/{other_file.id}/download-url",
            headers=self._auth_headers(self.uploader),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "invoice_file_not_found")

    def test_file_download_rejects_tampered_signature(self) -> None:
        file_content = f"%PDF-1.4\ntampered-download-{uuid4()}\n%%EOF".encode("utf-8")
        upload_response = self.client.post(
            "/api/v1/invoices/upload",
            headers=self._auth_headers(self.uploader),
            data={
                "invoice_number": f"UPLOAD-{uuid4()}",
                "currency": "USD",
            },
            files={"file": ("invoice.pdf", file_content, "application/pdf")},
        )
        self.assertEqual(upload_response.status_code, 201)
        invoice_id = upload_response.json()["invoice_id"]
        invoice_file = self._first_invoice_file(invoice_id)
        url_response = self.client.get(
            f"/api/v1/invoices/{invoice_id}/files/{invoice_file.id}/download-url",
            headers=self._auth_headers(self.uploader),
        )
        self.assertEqual(url_response.status_code, 200)

        download_url = url_response.json()["download_url"].replace("signature=", "signature=tampered")
        response = self.client.get(download_url)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "invoice_file_download_invalid")

    def test_status_transition_requires_admin_and_uses_authenticated_actor(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.UPLOADED, uploaded_by=self.uploader.id)

        denied = self.client.post(
            f"/api/v1/invoices/{invoice.id}/status",
            headers=self._auth_headers(self.reviewer),
            json={
                "actor_id": str(self.other_admin.id),
                "requested_status": InvoiceStatus.QUEUED.value,
            },
        )
        self.assertEqual(denied.status_code, 403)

        response = self.client.post(
            f"/api/v1/invoices/{invoice.id}/status",
            headers=self._auth_headers(self.admin),
            json={
                "actor_id": str(self.other_admin.id),
                "requested_status": InvoiceStatus.QUEUED.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.db.expire_all()
        audit = (
            self.db.query(AuditLog)
            .filter_by(entity_id=invoice.id, action="invoice.status_changed")
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        self.assertEqual(audit.actor_user_id, self.admin.id)

    def test_cross_tenant_status_transition_returns_not_found(self) -> None:
        invoice = self._create_invoice(
            status=InvoiceStatus.UPLOADED,
            organization_id=self.other_org.id,
            uploaded_by=self.other_admin.id,
        )

        response = self.client.post(
            f"/api/v1/invoices/{invoice.id}/status",
            headers=self._auth_headers(self.admin),
            json={"requested_status": InvoiceStatus.QUEUED.value},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "invoice_not_found")

    def test_failed_processing_jobs_are_limited_to_authenticated_user_tenant(self) -> None:
        own_invoice = self._create_invoice(status=InvoiceStatus.FAILED)
        own_job = self._create_job(invoice_id=own_invoice.id, status=ProcessingJobStatus.FAILED)
        other_invoice = self._create_invoice(
            status=InvoiceStatus.FAILED,
            organization_id=self.other_org.id,
            uploaded_by=self.other_admin.id,
        )
        other_job = self._create_job(invoice_id=other_invoice.id, status=ProcessingJobStatus.FAILED)

        response = self.client.get(
            "/api/v1/processing-jobs/failed",
            headers=self._auth_headers(self.admin),
        )

        self.assertEqual(response.status_code, 200)
        job_ids = {item["processing_job_id"] for item in response.json()["jobs"]}
        self.assertIn(str(own_job.id), job_ids)
        self.assertNotIn(str(other_job.id), job_ids)

    def test_cross_tenant_processing_job_detail_returns_not_found(self) -> None:
        other_invoice = self._create_invoice(
            status=InvoiceStatus.FAILED,
            organization_id=self.other_org.id,
            uploaded_by=self.other_admin.id,
        )
        other_job = self._create_job(invoice_id=other_invoice.id, status=ProcessingJobStatus.FAILED)

        response = self.client.get(
            f"/api/v1/processing-jobs/{other_job.id}",
            headers=self._auth_headers(self.admin),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "processing_job_not_found")

    def test_processing_job_reprocess_uses_authenticated_actor(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.FAILED, uploaded_by=self.uploader.id)
        job = self._create_job(invoice_id=invoice.id, status=ProcessingJobStatus.FAILED)

        response = self.client.post(
            f"/api/v1/processing-jobs/{job.id}/reprocess",
            headers=self._auth_headers(self.reviewer),
            json={"actor_id": str(self.other_admin.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.db.expire_all()
        audit = (
            self.db.query(AuditLog)
            .filter_by(entity_id=invoice.id, action="processing_job.status_changed")
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        self.assertEqual(audit.actor_user_id, self.reviewer.id)

    def test_processing_job_failure_requeues_before_max_attempts(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.QUEUED, uploaded_by=self.uploader.id)
        job = self._create_job(invoice_id=invoice.id, status=ProcessingJobStatus.QUEUED, attempts=0)
        redis_client = FakeRedis()

        result = record_processing_job_failure(
            self.db,
            redis_client,
            job.id,
            "temporary provider error",
            max_attempts=3,
        )

        self.assertEqual(result.status, ProcessingJobStatus.QUEUED)
        self.assertEqual(redis_client.enqueued_job_ids, [])
        self.assertEqual(redis_client.delayed_job_ids, [str(job.id)])
        self.assertGreater(redis_client.delayed_scores[0], time.time())
        self.db.expire_all()
        refreshed_job = self.db.get(ProcessingJob, job.id)
        refreshed_invoice = self.db.get(Invoice, invoice.id)
        self.assertEqual(refreshed_job.attempts, 1)
        self.assertEqual(refreshed_job.status, ProcessingJobStatus.QUEUED.value)
        self.assertEqual(refreshed_job.last_error, "temporary provider error")
        self.assertEqual(refreshed_invoice.status, InvoiceStatus.QUEUED.value)
        retry_audit = (
            self.db.query(AuditLog)
            .filter_by(entity_id=invoice.id, action="processing_job.retry_scheduled")
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        self.assertEqual(retry_audit.event_metadata["attempts"], 1)
        self.assertEqual(retry_audit.event_metadata["max_attempts"], 3)

    def test_processing_job_failure_marks_failed_at_max_attempts(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.QUEUED, uploaded_by=self.uploader.id)
        job = self._create_job(invoice_id=invoice.id, status=ProcessingJobStatus.QUEUED, attempts=2)
        redis_client = FakeRedis()

        result = record_processing_job_failure(
            self.db,
            redis_client,
            job.id,
            "permanent provider error",
            max_attempts=3,
        )

        self.assertEqual(result.status, ProcessingJobStatus.FAILED)
        self.assertEqual(redis_client.enqueued_job_ids, [])
        self.db.expire_all()
        refreshed_job = self.db.get(ProcessingJob, job.id)
        refreshed_invoice = self.db.get(Invoice, invoice.id)
        self.assertEqual(refreshed_job.attempts, 3)
        self.assertEqual(refreshed_job.status, ProcessingJobStatus.FAILED.value)
        self.assertEqual(refreshed_job.last_error, "permanent provider error")
        self.assertEqual(refreshed_invoice.status, InvoiceStatus.FAILED.value)

    def test_processing_job_failure_fails_immediately_when_not_retryable(self) -> None:
        # A permanent provider error (e.g. bad auth, exhausted quota) must not
        # be requeued just because attempts are still under the cap.
        invoice = self._create_invoice(status=InvoiceStatus.QUEUED, uploaded_by=self.uploader.id)
        job = self._create_job(invoice_id=invoice.id, status=ProcessingJobStatus.QUEUED, attempts=0)
        redis_client = FakeRedis()

        result = record_processing_job_failure(
            self.db,
            redis_client,
            job.id,
            "permanent provider error",
            max_attempts=3,
            retryable=False,
        )

        self.assertEqual(result.status, ProcessingJobStatus.FAILED)
        self.assertEqual(redis_client.enqueued_job_ids, [])
        self.assertEqual(redis_client.delayed_job_ids, [])
        self.db.expire_all()
        refreshed_job = self.db.get(ProcessingJob, job.id)
        refreshed_invoice = self.db.get(Invoice, invoice.id)
        self.assertEqual(refreshed_job.attempts, 1)
        self.assertEqual(refreshed_job.status, ProcessingJobStatus.FAILED.value)
        self.assertEqual(refreshed_invoice.status, InvoiceStatus.FAILED.value)

    def test_is_retryable_processing_error_classifies_extraction_errors(self) -> None:
        self.assertTrue(is_retryable_processing_error(TransientExtractionError("transient")))
        self.assertFalse(is_retryable_processing_error(ExtractionError("permanent")))
        self.assertTrue(is_retryable_processing_error(RuntimeError("some other infra error")))

    def test_audit_logs_are_limited_to_authenticated_user_tenant(self) -> None:
        own_invoice = self._create_invoice(status=InvoiceStatus.UPLOADED)
        other_invoice = self._create_invoice(
            status=InvoiceStatus.UPLOADED,
            organization_id=self.other_org.id,
            uploaded_by=self.other_admin.id,
        )
        own_audit = self._create_audit(
            organization_id=self.org.id,
            actor_user_id=self.admin.id,
            entity_id=own_invoice.id,
            action="invoice.uploaded",
        )
        other_audit = self._create_audit(
            organization_id=self.other_org.id,
            actor_user_id=self.other_admin.id,
            entity_id=other_invoice.id,
            action="invoice.uploaded",
        )

        response = self.client.get("/api/v1/audit-logs", headers=self._auth_headers(self.admin))

        self.assertEqual(response.status_code, 200)
        audit_ids = {item["audit_log_id"] for item in response.json()["audit_logs"]}
        self.assertIn(str(own_audit.id), audit_ids)
        self.assertNotIn(str(other_audit.id), audit_ids)

    def test_audit_logs_can_filter_by_entity_and_action(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.UPLOADED)
        matching = self._create_audit(
            organization_id=self.org.id,
            actor_user_id=self.admin.id,
            entity_id=invoice.id,
            action="invoice.uploaded",
        )
        self._create_audit(
            organization_id=self.org.id,
            actor_user_id=self.admin.id,
            entity_id=invoice.id,
            action="invoice.status_changed",
        )

        response = self.client.get(
            "/api/v1/audit-logs",
            headers=self._auth_headers(self.admin),
            params={
                "entity_type": "invoice",
                "entity_id": str(invoice.id),
                "action": "invoice.uploaded",
            },
        )

        self.assertEqual(response.status_code, 200)
        audit_logs = response.json()["audit_logs"]
        self.assertEqual([item["audit_log_id"] for item in audit_logs], [str(matching.id)])
        self.assertEqual(audit_logs[0]["metadata"]["source"], "test")

    def _create_invoice(
        self,
        *,
        status: InvoiceStatus,
        organization_id=None,
        uploaded_by=None,
    ) -> "Invoice":
        invoice = Invoice(
            organization_id=organization_id or self.org.id,
            supplier_id=None,
            uploaded_by=uploaded_by or self.admin.id,
            invoice_number=f"INV-{uuid4()}",
            total_amount=Decimal("100.00"),
            currency="USD",
            status=status.value,
        )
        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)
        return invoice

    def _create_job(self, *, invoice_id, status: ProcessingJobStatus, attempts: int = 1) -> "ProcessingJob":
        job = ProcessingJob(
            invoice_id=invoice_id,
            job_type=ProcessingJobType.INVOICE_EXTRACTION.value,
            status=status.value,
            attempts=attempts,
            last_error="Test failure" if status == ProcessingJobStatus.FAILED else None,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def _create_audit(self, *, organization_id, actor_user_id, entity_id, action: str) -> "AuditLog":
        audit = AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            entity_type="invoice",
            entity_id=entity_id,
            action=action,
            event_metadata={"source": "test"},
        )
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(audit)
        return audit

    def _create_invoice_file(self, *, invoice_id) -> "InvoiceFile":
        invoice_file = InvoiceFile(
            invoice_id=invoice_id,
            storage_key=f"test/missing/{uuid4()}.pdf",
            mime_type="application/pdf",
            file_size=100,
        )
        self.db.add(invoice_file)
        self.db.commit()
        self.db.refresh(invoice_file)
        return invoice_file

    def _first_invoice_file(self, invoice_id) -> "InvoiceFile":
        self.db.expire_all()
        return (
            self.db.query(InvoiceFile)
            .filter_by(invoice_id=invoice_id)
            .order_by(InvoiceFile.created_at.asc())
            .first()
        )

    def _auth_headers(self, user: "User") -> dict[str, str]:
        return {"Authorization": f"Bearer {_test_jwt(user.id)}"}


class FakeRedis:
    def __init__(self) -> None:
        self.enqueued_job_ids: list[str] = []
        self.delayed_job_ids: list[str] = []
        self.delayed_scores: list[float] = []

    def rpush(self, _queue_name: str, processing_job_id: str) -> None:
        self.enqueued_job_ids.append(processing_job_id)

    def zadd(self, _queue_name: str, values: dict[str, float]) -> None:
        for processing_job_id, score in values.items():
            self.delayed_job_ids.append(processing_job_id)
            self.delayed_scores.append(score)


def _test_jwt(user_id) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": str(user_id), "exp": int(time.time()) + 3600}
    encoded_header = _b64url_json(header)
    encoded_payload = _b64url_json(payload)
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64url(signature)}"


def _b64url_json(value: dict) -> str:
    return _b64url(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


if __name__ == "__main__":
    unittest.main()
