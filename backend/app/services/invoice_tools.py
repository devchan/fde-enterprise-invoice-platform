"""Shared tool layer for AI consumers (the MCP server and the AP assistant).

Each tool is a plain function taking an authenticated ``user`` and returning a
JSON-serializable dict. Tools call the existing service layer — never raw SQL —
so tenant isolation and role rules are enforced exactly as they are for the
HTTP API. Keeping this layer transport-agnostic means MCP, the in-app agent,
and any future consumer expose byte-identical behavior.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.invoice import Invoice
from app.models.user import User
from app.services.extraction_accuracy import extraction_accuracy_report
from app.services.invoice_embedding import find_similar_invoices
from app.services.invoice_nl_search import parse_search_query, search_invoices
from app.services.invoice_review import get_invoice_detail
from app.services.processing_jobs import (
    list_failed_processing_jobs_for_organization,
    requeue_processing_job,
)

# Mirrors the HTTP API's require_roles("admin", "reviewer") on the reprocess
# endpoint; read-only tools need only an authenticated user, like the API.
REPROCESS_ROLES = {"admin", "reviewer"}


class ToolAccessError(PermissionError):
    """The user's role does not allow this tool (maps to HTTP 403 semantics)."""


def tool_search_invoices(db: Session, *, user: User, query: str, limit: int = 20) -> dict[str, Any]:
    """Natural-language invoice search; returns interpreted filters + compact rows."""
    filters = parse_search_query(query)
    filters = filters.model_copy(update={"limit": min(filters.limit, limit)})
    invoices = search_invoices(db, organization_id=user.organization_id, filters=filters)
    return {
        "filters": filters.model_dump(mode="json", exclude_none=True),
        "invoices": [_invoice_summary(invoice) for invoice in invoices],
    }


def tool_get_invoice(db: Session, *, user: User, invoice_id: str) -> dict[str, Any]:
    """Full invoice detail: fields, validation results (with explanations),
    latest extraction summary, processing jobs, and reviews."""
    invoice = get_invoice_detail(db, _parse_uuid(invoice_id), organization_id=user.organization_id)
    latest_extraction = (
        max(invoice.extractions, key=lambda extraction: extraction.created_at)
        if invoice.extractions
        else None
    )
    return {
        **_invoice_summary(invoice),
        "line_items": [
            {
                "description": item.description,
                "quantity": _json(item.quantity),
                "unit_price": _json(item.unit_price),
                "line_total": _json(item.line_total),
                "category": item.category,
            }
            for item in invoice.line_items
        ],
        "validation_results": [
            {
                "rule_code": result.rule_code,
                "severity": result.severity,
                "passed": result.passed,
                "message": result.message,
                "explanation": result.explanation,
                "suggested_fix": result.suggested_fix,
            }
            for result in invoice.validation_results
        ],
        "latest_extraction": (
            {
                "model_name": latest_extraction.model_name,
                "prompt_version": latest_extraction.prompt_version,
                "confidence_score": _json(latest_extraction.confidence_score),
                "field_confidences": (latest_extraction.extracted_payload or {}).get("field_confidences"),
                "estimated_cost": _json(latest_extraction.estimated_cost),
            }
            if latest_extraction is not None
            else None
        ),
        "processing_jobs": [
            {
                "processing_job_id": str(job.id),
                "job_type": job.job_type,
                "status": job.status,
                "attempts": job.attempts,
                "last_error": job.last_error,
            }
            for job in invoice.processing_jobs
        ],
        "reviews": [
            {
                "decision": review.decision,
                "notes": review.notes,
                "corrected_fields": sorted((review.corrected_fields or {}).keys()),
                "created_at": _json(review.created_at),
            }
            for review in invoice.reviews
        ],
    }


def tool_find_similar_invoices(db: Session, *, user: User, invoice_id: str, limit: int = 5) -> dict[str, Any]:
    """Nearest invoices by embedding similarity within the user's organization."""
    invoice = get_invoice_detail(db, _parse_uuid(invoice_id), organization_id=user.organization_id)
    similar = find_similar_invoices(db, invoice=invoice, limit=max(1, min(limit, 20)))
    return {
        "invoice_id": str(invoice.id),
        "similar_invoices": [
            {
                "invoice_id": str(item.invoice_id),
                "invoice_number": item.invoice_number,
                "status": item.status,
                "total_amount": _json(item.total_amount),
                "currency": item.currency,
                "similarity": item.similarity,
            }
            for item in similar
        ],
    }


def tool_invoice_audit_trail(db: Session, *, user: User, invoice_id: str, limit: int = 20) -> dict[str, Any]:
    """Recent audit events for one invoice, newest first."""
    # Resolve through the org-scoped detail lookup first so a cross-tenant id
    # fails with not-found before any audit rows are touched.
    invoice = get_invoice_detail(db, _parse_uuid(invoice_id), organization_id=user.organization_id)
    events = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.organization_id == user.organization_id,
            AuditLog.entity_id == invoice.id,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    return {
        "invoice_id": str(invoice.id),
        "events": [
            {
                "action": event.action,
                "created_at": _json(event.created_at),
                "metadata": event.event_metadata,
            }
            for event in events
        ],
    }


def tool_extraction_accuracy(db: Session, *, user: User) -> dict[str, Any]:
    """Per-field extraction accuracy per prompt version from reviewer corrections."""
    report = extraction_accuracy_report(db, organization_id=user.organization_id)
    return {
        "prompt_versions": [
            {
                "prompt_version": entry.prompt_version,
                "model_names": entry.model_names,
                "reviewed_invoices": entry.reviewed_invoices,
                "fields": [
                    {
                        "field": field.field,
                        "corrected_count": field.corrected_count,
                        "accuracy": field.accuracy,
                    }
                    for field in entry.fields
                ],
            }
            for entry in report
        ]
    }


def tool_list_failed_jobs(db: Session, *, user: User, limit: int = 20) -> dict[str, Any]:
    """Failed processing jobs in the user's organization, newest first."""
    jobs = list_failed_processing_jobs_for_organization(
        db,
        organization_id=user.organization_id,
        limit=max(1, min(limit, 100)),
    )
    return {
        "failed_jobs": [
            {
                "processing_job_id": str(job.id),
                "invoice_id": str(job.invoice_id),
                "job_type": job.job_type,
                "attempts": job.attempts,
                "last_error": job.last_error,
            }
            for job in jobs
        ]
    }


def tool_reprocess_job(
    db: Session,
    redis_client: Any,
    *,
    user: User,
    processing_job_id: str,
) -> dict[str, Any]:
    """Requeue a failed processing job. Write action — admin/reviewer only."""
    if user.role.lower() not in REPROCESS_ROLES:
        raise ToolAccessError("Only admin or reviewer users can reprocess jobs.")
    job = requeue_processing_job(
        db,
        redis_client,
        processing_job_id=_parse_uuid(processing_job_id),
        organization_id=user.organization_id,
        actor_id=user.id,
    )
    return {
        "processing_job_id": str(job.id),
        "invoice_id": str(job.invoice_id),
        "status": job.status,
    }


def resolve_tool_user(db: Session, *, email: str) -> User:
    """Look up the principal a headless tool consumer (the MCP server) acts as.
    All tool calls are then scoped to this user's organization and role."""
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise LookupError(f"Tool service user '{email}' was not found.")
    return user


def _invoice_summary(invoice: Invoice) -> dict[str, Any]:
    return {
        "invoice_id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "supplier_id": str(invoice.supplier_id) if invoice.supplier_id else None,
        "status": invoice.status,
        "invoice_date": _json(invoice.invoice_date),
        "total_amount": _json(invoice.total_amount),
        "currency": invoice.currency,
        "updated_at": _json(invoice.updated_at),
    }


def _parse_uuid(value: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise ValueError(f"'{value}' is not a valid UUID.") from exc


def _json(value: Any) -> Any:
    # Compact JSON-safe coercion for the few non-serializable column types.
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value
