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

REQUIRED_MODULES = ("fastapi", "sqlalchemy", "pydantic", "pgvector")
HAS_REQUIRED_MODULES = all(importlib.util.find_spec(module) is not None for module in REQUIRED_MODULES)

if importlib.util.find_spec("pydantic") is not None:
    from app.services.invoice_embedding import (
        EMBEDDING_DIMENSIONS,
        DevelopmentInvoiceEmbedder,
        cosine_similarity,
        embedding_source_text,
    )

if HAS_REQUIRED_MODULES:
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.main import app
    from app.models.invoice import Invoice, InvoiceEmbedding
    from app.models.organization import Organization
    from app.models.supplier import Supplier
    from app.models.user import User
    from app.services.invoice_embedding import persist_invoice_embedding
    from app.services.invoice_workflow import InvoiceStatus


class PayloadLineItemStub:
    def __init__(self, description: str) -> None:
        self.description = description
        self.quantity = Decimal("2")
        self.unit_price = Decimal("50.00")
        self.line_total = Decimal("100.00")


class PayloadStub:
    supplier_name = "Acme Office Supplies"
    invoice_number = "INV-500"
    invoice_date = "2026-07-01"
    total_amount = Decimal("100.00")
    currency = "USD"

    def __init__(self, line_items: list[PayloadLineItemStub] | None = None) -> None:
        self.line_items = line_items or []


class InvoiceStub:
    supplier = None
    invoice_number = "INV-FALLBACK"
    invoice_date = None
    total_amount = Decimal("75.00")
    currency = "EUR"


@unittest.skipIf(importlib.util.find_spec("pydantic") is None, "pydantic is not installed")
class InvoiceEmbeddingUnitTest(unittest.TestCase):
    def test_development_embedder_is_deterministic_and_normalized(self) -> None:
        embedder = DevelopmentInvoiceEmbedder()
        first = embedder.embed(text="supplier: Acme\nline item: paper")
        second = embedder.embed(text="supplier: Acme\nline item: paper")

        self.assertEqual(len(first.vector), EMBEDDING_DIMENSIONS)
        self.assertEqual(first.vector, second.vector)
        norm = sum(value * value for value in first.vector) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_development_embedder_ranks_shared_content_higher(self) -> None:
        embedder = DevelopmentInvoiceEmbedder()
        base = embedder.embed(text="supplier: Acme Office Supplies\nline item: copy paper a4")
        related = embedder.embed(text="supplier: Acme Office Supplies\nline item: copy paper a3")
        unrelated = embedder.embed(text="supplier: Globex Catering\nline item: lunch buffet")

        self.assertGreater(
            cosine_similarity(base.vector, related.vector),
            cosine_similarity(base.vector, unrelated.vector),
        )

    def test_cosine_similarity_bounds(self) -> None:
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0, places=6)
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0, places=6)
        self.assertEqual(cosine_similarity([0.0, 0.0], [1.0, 0.0]), 0.0)

    def test_embedding_source_text_prefers_extracted_payload(self) -> None:
        text = embedding_source_text(
            invoice=InvoiceStub(),
            payload=PayloadStub(line_items=[PayloadLineItemStub("Copy paper A4")]),
        )

        self.assertIn("supplier: Acme Office Supplies", text)
        self.assertIn("invoice number: INV-500", text)
        self.assertIn("line item: Copy paper A4", text)

    def test_embedding_source_text_falls_back_to_invoice_fields(self) -> None:
        text = embedding_source_text(invoice=InvoiceStub(), payload=None)

        self.assertIn("invoice number: INV-FALLBACK", text)
        self.assertIn("currency: EUR", text)
        self.assertIn("supplier: unknown", text)


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend integration dependencies are not installed")
class SimilarInvoicesApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.db = SessionLocal()
        self.org = Organization(name=f"Embedding Org {uuid4()}")
        self.other_org = Organization(name=f"Other Embedding Org {uuid4()}")
        self.db.add_all([self.org, self.other_org])
        self.db.flush()
        self.reviewer = User(
            organization_id=self.org.id,
            email=f"reviewer-{uuid4()}@example.com",
            role="reviewer",
        )
        self.other_user = User(
            organization_id=self.other_org.id,
            email=f"other-{uuid4()}@example.com",
            role="reviewer",
        )
        self.supplier = Supplier(organization_id=self.org.id, name=f"Embedding Supplier {uuid4()}")
        self.db.add_all([self.reviewer, self.other_user, self.supplier])
        self.db.commit()
        self.embedder = DevelopmentInvoiceEmbedder()

    def tearDown(self) -> None:
        self.db.close()

    def test_similar_invoices_ranked_by_shared_content_and_exclude_self(self) -> None:
        base = self._create_embedded_invoice("supplier: Acme Office\nline item: copy paper a4")
        related = self._create_embedded_invoice("supplier: Acme Office\nline item: copy paper a3")
        unrelated = self._create_embedded_invoice("supplier: Globex Catering\nline item: lunch buffet")

        response = self.client.get(
            f"/api/v1/invoices/{base.id}/similar",
            headers=self._auth_headers(self.reviewer),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["invoice_id"], str(base.id))
        returned_ids = [item["invoice_id"] for item in body["similar_invoices"]]
        self.assertNotIn(str(base.id), returned_ids)
        self.assertIn(str(related.id), returned_ids)
        # The same-supplier invoice must outrank the unrelated one.
        self.assertLess(returned_ids.index(str(related.id)), returned_ids.index(str(unrelated.id)))
        similarities = [item["similarity"] for item in body["similar_invoices"]]
        self.assertEqual(similarities, sorted(similarities, reverse=True))

    def test_similar_invoices_are_tenant_isolated(self) -> None:
        base = self._create_embedded_invoice("supplier: Acme Office\nline item: copy paper a4")
        foreign = self._create_embedded_invoice(
            "supplier: Acme Office\nline item: copy paper a4",
            organization_id=self.other_org.id,
            uploaded_by=self.other_user.id,
            supplier_id=None,
        )

        response = self.client.get(
            f"/api/v1/invoices/{base.id}/similar",
            headers=self._auth_headers(self.reviewer),
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = [item["invoice_id"] for item in response.json()["similar_invoices"]]
        self.assertNotIn(str(foreign.id), returned_ids)

        cross_tenant = self.client.get(
            f"/api/v1/invoices/{foreign.id}/similar",
            headers=self._auth_headers(self.reviewer),
        )
        self.assertEqual(cross_tenant.status_code, 404)

    def test_similar_invoices_empty_before_embedding_exists(self) -> None:
        invoice = self._create_invoice()

        response = self.client.get(
            f"/api/v1/invoices/{invoice.id}/similar",
            headers=self._auth_headers(self.reviewer),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["similar_invoices"], [])

    def test_persist_invoice_embedding_updates_in_place(self) -> None:
        invoice = self._create_invoice()
        first = persist_invoice_embedding(
            self.db,
            invoice=invoice,
            source_text="supplier: Acme",
            result=self.embedder.embed(text="supplier: Acme"),
        )
        second = persist_invoice_embedding(
            self.db,
            invoice=invoice,
            source_text="supplier: Acme Updated",
            result=self.embedder.embed(text="supplier: Acme Updated"),
        )
        self.db.commit()

        self.assertEqual(first.id, second.id)
        rows = self.db.query(InvoiceEmbedding).filter(InvoiceEmbedding.invoice_id == invoice.id).count()
        self.assertEqual(rows, 1)
        self.assertEqual(second.source_text, "supplier: Acme Updated")

    def test_similar_invoices_requires_authentication(self) -> None:
        invoice = self._create_invoice()

        response = self.client.get(f"/api/v1/invoices/{invoice.id}/similar")

        self.assertEqual(response.status_code, 401)

    def _create_invoice(self, *, organization_id=None, uploaded_by=None, supplier_id=None) -> Invoice:
        invoice = Invoice(
            organization_id=organization_id or self.org.id,
            supplier_id=self.supplier.id if supplier_id is None and organization_id is None else supplier_id,
            uploaded_by=uploaded_by or self.reviewer.id,
            invoice_number=f"INV-{uuid4()}",
            total_amount=Decimal("100.00"),
            currency="USD",
            status=InvoiceStatus.REVIEW_REQUIRED.value,
        )
        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)
        return invoice

    def _create_embedded_invoice(self, source_text: str, **invoice_kwargs) -> Invoice:
        invoice = self._create_invoice(**invoice_kwargs)
        persist_invoice_embedding(
            self.db,
            invoice=invoice,
            source_text=source_text,
            result=self.embedder.embed(text=source_text),
        )
        self.db.commit()
        return invoice

    def _auth_headers(self, user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {_test_jwt(user.id)}"}

    def test_worker_embed_invoice_persists_embedding(self) -> None:
        from app.services.processing_jobs import _embed_invoice

        invoice = self._create_invoice()
        _embed_invoice(self.db, invoice=invoice, payload=PayloadStub())

        row = self.db.query(InvoiceEmbedding).filter(InvoiceEmbedding.invoice_id == invoice.id).one()
        self.assertEqual(row.model_name, "development-embedder")
        self.assertIn("supplier: Acme Office Supplies", row.source_text)

    def test_worker_embed_invoice_swallows_provider_failure(self) -> None:
        from unittest.mock import patch

        from app.services.processing_jobs import _embed_invoice

        invoice = self._create_invoice()

        class ExplodingEmbedder:
            def embed(self, *, text: str):
                raise RuntimeError("provider down")

        # A provider outage must be non-fatal: the job already committed its
        # extraction, so _embed_invoice logs and moves on instead of raising.
        with patch(
            "app.services.invoice_embedding.build_invoice_embedder",
            return_value=ExplodingEmbedder(),
        ):
            _embed_invoice(self.db, invoice=invoice, payload=PayloadStub())

        rows = self.db.query(InvoiceEmbedding).filter(InvoiceEmbedding.invoice_id == invoice.id).count()
        self.assertEqual(rows, 0)


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
