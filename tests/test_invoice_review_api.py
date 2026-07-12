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
    from app.models.invoice import Invoice, InvoiceLineItem, InvoiceReview
    from app.models.organization import Organization
    from app.models.supplier import Supplier
    from app.models.user import User
    from app.services.invoice_workflow import InvoiceStatus


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend integration dependencies are not installed")
class InvoiceReviewApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.db = SessionLocal()
        self.org = Organization(name=f"Review API Org {uuid4()}")
        self.db.add(self.org)
        self.db.flush()
        self.reviewer = User(
            organization_id=self.org.id,
            email=f"reviewer-{uuid4()}@example.com",
            role="reviewer",
        )
        self.supplier = Supplier(
            organization_id=self.org.id,
            name=f"Review API Supplier {uuid4()}",
        )
        self.uploader = User(
            organization_id=self.org.id,
            email=f"uploader-{uuid4()}@example.com",
            role="uploader",
        )
        self.other_org = Organization(name=f"Other Review API Org {uuid4()}")
        self.db.add(self.other_org)
        self.db.flush()
        self.other_reviewer = User(
            organization_id=self.other_org.id,
            email=f"other-reviewer-{uuid4()}@example.com",
            role="reviewer",
        )
        self.db.add_all([self.reviewer, self.supplier, self.uploader, self.other_reviewer])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_review_queue_and_detail_return_review_ready_invoice(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.REVIEW_REQUIRED)

        queue_response = self.client.get(
            "/api/v1/invoices",
            params={"review_queue": "true"},
            headers=self._auth_headers(self.reviewer),
        )
        self.assertEqual(queue_response.status_code, 200)
        self.assertTrue(
            any(item["invoice_id"] == str(invoice.id) for item in queue_response.json()["invoices"])
        )

        detail_response = self.client.get(
            f"/api/v1/invoices/{invoice.id}",
            headers=self._auth_headers(self.reviewer),
        )
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertEqual(detail["invoice_id"], str(invoice.id))
        self.assertEqual(detail["status"], InvoiceStatus.REVIEW_REQUIRED.value)
        self.assertEqual(len(detail["line_items"]), 1)

    def test_invoice_list_is_limited_to_authenticated_user_tenant(self) -> None:
        own_invoice = self._create_invoice(status=InvoiceStatus.REVIEW_REQUIRED)
        other_invoice = self._create_invoice(
            status=InvoiceStatus.REVIEW_REQUIRED,
            organization_id=self.other_org.id,
            uploaded_by=self.other_reviewer.id,
            supplier_id=None,
        )

        response = self.client.get(
            "/api/v1/invoices",
            params={"review_queue": "true"},
            headers=self._auth_headers(self.reviewer),
        )

        self.assertEqual(response.status_code, 200)
        invoice_ids = {item["invoice_id"] for item in response.json()["invoices"]}
        self.assertIn(str(own_invoice.id), invoice_ids)
        self.assertNotIn(str(other_invoice.id), invoice_ids)

    def test_cross_tenant_invoice_detail_returns_not_found(self) -> None:
        other_invoice = self._create_invoice(
            status=InvoiceStatus.REVIEW_REQUIRED,
            organization_id=self.other_org.id,
            uploaded_by=self.other_reviewer.id,
            supplier_id=None,
        )

        response = self.client.get(
            f"/api/v1/invoices/{other_invoice.id}",
            headers=self._auth_headers(self.reviewer),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "invoice_not_found")

    def test_invoice_list_requires_authentication(self) -> None:
        response = self.client.get("/api/v1/invoices", params={"review_queue": "true"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "authentication_required")

    def test_review_approve_applies_corrections_and_writes_audit_events(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.REVIEW_REQUIRED)
        detail = self.client.get(
            f"/api/v1/invoices/{invoice.id}",
            headers=self._auth_headers(self.reviewer),
        ).json()

        response = self.client.post(
            f"/api/v1/invoices/{invoice.id}/review",
            headers=self._auth_headers(self.reviewer),
            json={
                "decision": "approve",
                "expected_updated_at": detail["updated_at"],
                "notes": "Approved after correction.",
                "corrected_fields": {
                    "total_amount": "125.00",
                    "currency": "usd",
                    "line_items": [
                        {
                            "description": "Corrected service",
                            "quantity": "1",
                            "unit_price": "125.00",
                            "line_total": "125.00",
                        }
                    ],
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], InvoiceStatus.APPROVED.value)
        self.assertEqual(body["total_amount"], "125.00")
        self.assertEqual(body["currency"], "USD")
        self.assertEqual(body["line_items"][0]["description"], "Corrected service")
        self.assertEqual(body["reviews"][0]["decision"], "approve")

        self.db.expire_all()
        review_count = self.db.query(InvoiceReview).filter_by(invoice_id=invoice.id).count()
        audit_actions = [
            row.action
            for row in self.db.query(AuditLog).filter_by(entity_id=invoice.id).all()
        ]
        self.assertEqual(review_count, 1)
        self.assertIn("invoice.review_corrections_saved", audit_actions)
        self.assertIn("invoice.review_decision", audit_actions)
        self.assertIn("invoice.status_changed", audit_actions)

    def test_review_uses_authenticated_user_as_reviewer(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.REVIEW_REQUIRED)

        response = self.client.post(
            f"/api/v1/invoices/{invoice.id}/review",
            headers=self._auth_headers(self.reviewer),
            json={
                "reviewer_id": str(self.other_reviewer.id),
                "decision": "reject",
                "corrected_fields": {},
            },
        )

        self.assertEqual(response.status_code, 200)
        self.db.expire_all()
        review = self.db.query(InvoiceReview).filter_by(invoice_id=invoice.id).one()
        self.assertEqual(review.reviewer_id, self.reviewer.id)

    def test_review_requires_reviewer_role(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.REVIEW_REQUIRED)

        response = self.client.post(
            f"/api/v1/invoices/{invoice.id}/review",
            headers=self._auth_headers(self.uploader),
            json={
                "decision": "reject",
                "corrected_fields": {},
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "permission_denied")

    def test_review_reject_records_decision(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.REVIEW_REQUIRED)

        response = self.client.post(
            f"/api/v1/invoices/{invoice.id}/review",
            headers=self._auth_headers(self.reviewer),
            json={
                "decision": "reject",
                "notes": "Rejected by reviewer.",
                "corrected_fields": {},
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], InvoiceStatus.REJECTED.value)
        self.assertEqual(body["reviews"][0]["decision"], "reject")

    def test_review_rejects_stale_expected_updated_at(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.REVIEW_REQUIRED)
        detail = self.client.get(
            f"/api/v1/invoices/{invoice.id}",
            headers=self._auth_headers(self.reviewer),
        ).json()
        invoice.total_amount = Decimal("99.00")
        self.db.commit()

        response = self.client.post(
            f"/api/v1/invoices/{invoice.id}/review",
            headers=self._auth_headers(self.reviewer),
            json={
                "decision": "approve",
                "expected_updated_at": detail["updated_at"],
                "corrected_fields": {},
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "invoice_review_conflict")

    def test_review_rejects_unsupported_corrected_field(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.REVIEW_REQUIRED)

        response = self.client.post(
            f"/api/v1/invoices/{invoice.id}/review",
            headers=self._auth_headers(self.reviewer),
            json={
                "decision": "approve",
                "corrected_fields": {"supplier_id": str(uuid4())},
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "invoice_review_invalid")

    def test_review_duplicate_invoice_number_returns_conflict(self) -> None:
        existing_invoice = self._create_invoice(status=InvoiceStatus.APPROVED)
        review_invoice = self._create_invoice(status=InvoiceStatus.REVIEW_REQUIRED)

        response = self.client.post(
            f"/api/v1/invoices/{review_invoice.id}/review",
            headers=self._auth_headers(self.reviewer),
            json={
                "decision": "approve",
                "corrected_fields": {
                    "invoice_number": existing_invoice.invoice_number,
                },
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "invoice_duplicate")

    def _create_invoice(
        self,
        *,
        status: InvoiceStatus,
        organization_id=None,
        uploaded_by=None,
        supplier_id=None,
    ) -> "Invoice":
        invoice = Invoice(
            organization_id=organization_id or self.org.id,
            supplier_id=self.supplier.id if supplier_id is None and organization_id is None else supplier_id,
            uploaded_by=uploaded_by or self.reviewer.id,
            invoice_number=f"INV-{uuid4()}",
            total_amount=Decimal("100.00"),
            currency="USD",
            status=status.value,
        )
        self.db.add(invoice)
        self.db.flush()
        self.db.add(
            InvoiceLineItem(
                invoice_id=invoice.id,
                description="Original service",
                quantity=Decimal("1"),
                unit_price=Decimal("100.00"),
                line_total=Decimal("100.00"),
            )
        )
        self.db.commit()
        self.db.refresh(invoice)
        return invoice

    def _auth_headers(self, user: "User") -> dict[str, str]:
        return {"Authorization": f"Bearer {_test_jwt(user.id)}"}


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
