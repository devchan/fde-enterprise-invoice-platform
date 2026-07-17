"""Tests for the agent layer: the shared tool layer (tenant scoping, role
rules), the AP assistant fallback answerer, its API endpoint, and the MCP
server's tool registry."""

import base64
import hashlib
import hmac
import importlib.util
import json
import time
import unittest
from decimal import Decimal
from uuid import UUID, uuid4

REQUIRED_MODULES = ("fastapi", "sqlalchemy", "pydantic", "pgvector", "app")
HAS_REQUIRED_MODULES = all(importlib.util.find_spec(module) is not None for module in REQUIRED_MODULES)
HAS_MCP = importlib.util.find_spec("mcp") is not None

if HAS_REQUIRED_MODULES:
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.main import app
    from app.models.invoice import Invoice, InvoiceValidationResult
    from app.models.organization import Organization
    from app.models.processing import ProcessingJob
    from app.models.user import User
    from app.services import invoice_tools
    from app.services.ap_assistant import _READ_TOOLS, TOOL_DEFINITIONS, ask_assistant
    from app.services.invoice_intake import InvoiceNotFoundError
    from app.services.invoice_workflow import InvoiceStatus


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend integration dependencies are not installed")
class AgentLayerTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.db = SessionLocal()
        self.org = Organization(name=f"Agent Org {uuid4()}")
        self.other_org = Organization(name=f"Other Agent Org {uuid4()}")
        self.db.add_all([self.org, self.other_org])
        self.db.flush()
        self.reviewer = User(
            organization_id=self.org.id,
            email=f"agent-reviewer-{uuid4()}@example.com",
            role="reviewer",
        )
        self.uploader = User(
            organization_id=self.org.id,
            email=f"agent-uploader-{uuid4()}@example.com",
            role="uploader",
        )
        self.other_user = User(
            organization_id=self.other_org.id,
            email=f"agent-other-{uuid4()}@example.com",
            role="reviewer",
        )
        self.db.add_all([self.reviewer, self.uploader, self.other_user])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def _create_invoice(self, *, organization_id=None, uploaded_by=None, status=None) -> "Invoice":
        invoice = Invoice(
            organization_id=organization_id or self.org.id,
            uploaded_by=uploaded_by or self.reviewer.id,
            invoice_number=f"INV-AGENT-{uuid4()}",
            total_amount=Decimal("120.00"),
            currency="USD",
            status=(status or InvoiceStatus.REVIEW_REQUIRED).value,
        )
        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)
        return invoice

    def _auth_headers(self, user: "User") -> dict[str, str]:
        return {"Authorization": f"Bearer {_test_jwt(user.id)}"}


class InvoiceToolsTest(AgentLayerTestBase):
    def test_get_invoice_returns_detail_shape(self) -> None:
        invoice = self._create_invoice()
        self.db.add(
            InvoiceValidationResult(
                invoice_id=invoice.id,
                rule_code="supplier_found",
                severity="error",
                message="Supplier must be matched before approval.",
                passed=False,
                explanation="This invoice is not linked to a known supplier.",
                suggested_fix="Match the invoice to an existing supplier record.",
            )
        )
        self.db.commit()

        detail = invoice_tools.tool_get_invoice(self.db, user=self.reviewer, invoice_id=str(invoice.id))

        self.assertEqual(detail["invoice_number"], invoice.invoice_number)
        failure = detail["validation_results"][0]
        self.assertFalse(failure["passed"])
        self.assertTrue(failure["explanation"])
        self.assertTrue(failure["suggested_fix"])

    def test_get_invoice_is_tenant_isolated(self) -> None:
        foreign = self._create_invoice(organization_id=self.other_org.id, uploaded_by=self.other_user.id)

        with self.assertRaises(InvoiceNotFoundError):
            invoice_tools.tool_get_invoice(self.db, user=self.reviewer, invoice_id=str(foreign.id))

    def test_get_invoice_rejects_malformed_uuid(self) -> None:
        with self.assertRaises(ValueError):
            invoice_tools.tool_get_invoice(self.db, user=self.reviewer, invoice_id="not-a-uuid")

    def test_search_invoices_scopes_to_organization(self) -> None:
        mine = self._create_invoice()
        self._create_invoice(organization_id=self.other_org.id, uploaded_by=self.other_user.id)

        result = invoice_tools.tool_search_invoices(self.db, user=self.reviewer, query="all invoices")

        returned = {row["invoice_id"] for row in result["invoices"]}
        self.assertIn(str(mine.id), returned)
        for row in result["invoices"]:
            found = self.db.get(Invoice, UUID(row["invoice_id"]))
            self.assertEqual(found.organization_id, self.org.id)

    def test_reprocess_requires_privileged_role(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.FAILED)
        job = ProcessingJob(
            invoice_id=invoice.id,
            job_type="invoice_extraction",
            status="failed",
            attempts=3,
            last_error="boom",
        )
        self.db.add(job)
        self.db.commit()

        with self.assertRaises(invoice_tools.ToolAccessError):
            invoice_tools.tool_reprocess_job(
                self.db,
                _NullRedis(),
                user=self.uploader,
                processing_job_id=str(job.id),
            )

    def test_audit_trail_rejects_cross_tenant_invoice(self) -> None:
        foreign = self._create_invoice(organization_id=self.other_org.id, uploaded_by=self.other_user.id)

        with self.assertRaises(InvoiceNotFoundError):
            invoice_tools.tool_invoice_audit_trail(self.db, user=self.reviewer, invoice_id=str(foreign.id))


class AssistantFallbackTest(AgentLayerTestBase):
    def setUp(self) -> None:
        super().setUp()
        # Force the deterministic path even when the environment has a key.
        self._previous_key = settings.openai_api_key
        settings.openai_api_key = ""

    def tearDown(self) -> None:
        settings.openai_api_key = self._previous_key
        super().tearDown()

    def test_invoice_uuid_question_answers_with_detail(self) -> None:
        invoice = self._create_invoice()
        self.db.add(
            InvoiceValidationResult(
                invoice_id=invoice.id,
                rule_code="extraction_confidence",
                severity="warning",
                message="Extraction confidence is below review threshold.",
                passed=False,
                explanation="The AI extractor was not confident in this document.",
                suggested_fix="Compare each extracted field against the document.",
            )
        )
        self.db.commit()

        result = ask_assistant(self.db, user=self.reviewer, question=f"Why is invoice {invoice.id} stuck?")

        self.assertEqual(result.model_name, "assistant-fallback")
        self.assertIn(invoice.invoice_number, result.answer)
        self.assertIn("extraction_confidence", result.answer)
        self.assertEqual(result.tool_calls[0]["tool"], "get_invoice")

    def test_failure_question_lists_failed_jobs(self) -> None:
        invoice = self._create_invoice(status=InvoiceStatus.FAILED)
        self.db.add(
            ProcessingJob(
                invoice_id=invoice.id,
                job_type="invoice_extraction",
                status="failed",
                attempts=3,
                last_error="provider exploded",
            )
        )
        self.db.commit()

        result = ask_assistant(self.db, user=self.reviewer, question="what jobs failed today?")

        self.assertIn("provider exploded", result.answer)
        self.assertEqual(result.tool_calls[0]["tool"], "list_failed_jobs")

    def test_generic_question_falls_back_to_search(self) -> None:
        result = ask_assistant(self.db, user=self.reviewer, question="show me approved invoices")

        self.assertEqual(result.tool_calls[0]["tool"], "search_invoices")

    def test_assistant_tools_are_read_only(self) -> None:
        # The agent must never get a mutating tool; reprocess/approve stay
        # behind explicit human actions in the cockpit.
        self.assertNotIn("reprocess_job", _READ_TOOLS)
        self.assertEqual(
            sorted(_READ_TOOLS),
            sorted(definition["name"] for definition in TOOL_DEFINITIONS),
        )


class AssistantApiTest(AgentLayerTestBase):
    def test_ask_requires_authentication(self) -> None:
        response = self.client.post("/api/v1/assistant/ask", json={"question": "hello"})

        self.assertEqual(response.status_code, 401)

    def test_ask_answers_with_tool_trace(self) -> None:
        previous_key = settings.openai_api_key
        settings.openai_api_key = ""
        try:
            invoice = self._create_invoice()
            response = self.client.post(
                "/api/v1/assistant/ask",
                json={"question": f"why is invoice {invoice.id} stuck?"},
                headers=self._auth_headers(self.reviewer),
            )
        finally:
            settings.openai_api_key = previous_key

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(invoice.invoice_number, body["answer"])
        self.assertEqual(body["tool_calls"][0]["tool"], "get_invoice")

    def test_ask_rejects_blank_question(self) -> None:
        response = self.client.post(
            "/api/v1/assistant/ask",
            json={"question": "   "},
            headers=self._auth_headers(self.reviewer),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "assistant_request_invalid")


@unittest.skipIf(not (HAS_REQUIRED_MODULES and HAS_MCP), "mcp SDK is not installed")
class McpServerTest(AgentLayerTestBase):
    def test_registered_tools_match_contract(self) -> None:
        import anyio

        from app.mcp.server import mcp

        tools = anyio.run(mcp.list_tools)
        names = sorted(tool.name for tool in tools)
        self.assertEqual(
            names,
            sorted(
                [
                    "search_invoices",
                    "get_invoice",
                    "find_similar_invoices",
                    "invoice_audit_trail",
                    "extraction_accuracy",
                    "list_failed_jobs",
                    "reprocess_job",
                ]
            ),
        )

    def test_tool_call_runs_as_configured_service_user(self) -> None:
        from app.mcp.server import search_invoices

        invoice = self._create_invoice()
        previous = settings.mcp_service_user_email
        settings.mcp_service_user_email = self.reviewer.email
        try:
            payload = json.loads(search_invoices(query="all invoices", limit=50))
        finally:
            settings.mcp_service_user_email = previous

        returned = {row["invoice_id"] for row in payload["invoices"]}
        self.assertIn(str(invoice.id), returned)

    def test_tool_call_without_service_user_returns_structured_error(self) -> None:
        from app.mcp.server import search_invoices

        previous = settings.mcp_service_user_email
        settings.mcp_service_user_email = ""
        try:
            payload = json.loads(search_invoices(query="anything"))
        finally:
            settings.mcp_service_user_email = previous

        self.assertEqual(payload["error"], "invalid_request")

    def test_reprocess_permission_error_is_structured(self) -> None:
        from app.mcp.server import reprocess_job

        invoice = self._create_invoice(status=InvoiceStatus.FAILED)
        job = ProcessingJob(
            invoice_id=invoice.id,
            job_type="invoice_extraction",
            status="failed",
            attempts=3,
            last_error="boom",
        )
        self.db.add(job)
        self.db.commit()

        previous = settings.mcp_service_user_email
        settings.mcp_service_user_email = self.uploader.email
        try:
            payload = json.loads(reprocess_job(processing_job_id=str(job.id)))
        finally:
            settings.mcp_service_user_email = previous

        self.assertEqual(payload["error"], "permission_denied")


class _NullRedis:
    def rpush(self, *args, **kwargs) -> None:  # pragma: no cover - never reached
        raise AssertionError("reprocess must fail before touching the queue")


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
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


if __name__ == "__main__":
    unittest.main()
