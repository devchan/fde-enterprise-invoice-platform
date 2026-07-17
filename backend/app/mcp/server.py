"""MCP (Model Context Protocol) server for the invoice platform.

Exposes the shared tool layer (app.services.invoice_tools) to any MCP client —
Claude Desktop/Code, IDE agents, or custom hosts — over stdio:

    MCP_SERVICE_USER_EMAIL=ops@example.com python -m app.mcp.server

Every call acts as the configured service user: the tool layer scopes all reads
to that user's organization and enforces the same role rules as the HTTP API
(reprocess requires admin/reviewer), so an MCP client can never see or do more
than that user could through the cockpit. Each tool call runs on a fresh
database session, mirroring the per-request session pattern of the API.
"""

import json
from typing import Any

from app.core.config import settings
from app.db.session import SessionLocal
from app.services import invoice_tools
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "invoice-platform",
    instructions=(
        "Tools for an enterprise AI invoice processing platform. All data is "
        "scoped to the configured service user's organization. Amounts are "
        "decimal strings; identifiers are UUIDs."
    ),
)


def _run(tool: str, **arguments: Any) -> str:
    """Execute one tool call on a fresh session as the configured service user.

    Errors are returned as structured JSON (not raised) so the MCP client's
    model can read what went wrong and correct its next call.
    """
    db = SessionLocal()
    try:
        user = invoice_tools.resolve_tool_user(db, email=_service_email())
        if tool == "reprocess_job":
            from redis import Redis

            result = invoice_tools.tool_reprocess_job(
                db,
                Redis.from_url(settings.redis_url),
                user=user,
                **arguments,
            )
        else:
            result = getattr(invoice_tools, f"tool_{tool}")(db, user=user, **arguments)
        return json.dumps(result)
    except invoice_tools.ToolAccessError as exc:
        return json.dumps({"error": "permission_denied", "message": str(exc)})
    except (LookupError, ValueError) as exc:
        return json.dumps({"error": "invalid_request", "message": str(exc)})
    except Exception as exc:  # pragma: no cover - surfaced to the client model
        db.rollback()
        return json.dumps({"error": "tool_failed", "message": str(exc)})
    finally:
        db.close()


def _service_email() -> str:
    email = settings.mcp_service_user_email.strip()
    if not email:
        raise LookupError(
            "MCP_SERVICE_USER_EMAIL is not configured; set it to the platform "
            "user this MCP server should act as."
        )
    return email


@mcp.tool()
def search_invoices(query: str, limit: int = 20) -> str:
    """Search invoices with a natural-language query (e.g. "approved acme
    invoices over $10k from june"). Returns the interpreted filters and
    matching invoices."""
    return _run("search_invoices", query=query, limit=limit)


@mcp.tool()
def get_invoice(invoice_id: str) -> str:
    """Full detail for one invoice: fields, line items with AI categories,
    validation results with explanations, latest extraction confidences,
    processing jobs, and review decisions."""
    return _run("get_invoice", invoice_id=invoice_id)


@mcp.tool()
def find_similar_invoices(invoice_id: str, limit: int = 5) -> str:
    """Most similar invoices to the given one by embedding cosine similarity
    (same organization only). Useful for duplicate triage."""
    return _run("find_similar_invoices", invoice_id=invoice_id, limit=limit)


@mcp.tool()
def invoice_audit_trail(invoice_id: str, limit: int = 20) -> str:
    """Recent audit events for one invoice, newest first — who did what, when."""
    return _run("invoice_audit_trail", invoice_id=invoice_id, limit=limit)


@mcp.tool()
def extraction_accuracy() -> str:
    """Per-field AI extraction accuracy per prompt version, measured from
    reviewer corrections."""
    return _run("extraction_accuracy")


@mcp.tool()
def list_failed_jobs(limit: int = 20) -> str:
    """Failed invoice processing jobs in the organization, newest first."""
    return _run("list_failed_jobs", limit=limit)


@mcp.tool()
def reprocess_job(processing_job_id: str) -> str:
    """Requeue a failed processing job for another extraction attempt.
    Write action — requires the service user to be an admin or reviewer."""
    return _run("reprocess_job", processing_job_id=processing_job_id)


if __name__ == "__main__":
    mcp.run()
