"""AP assistant: agentic question answering over the invoice platform.

Takes a reviewer's question ("why is invoice INV-1042 stuck?"), lets the model
chain tool calls over the shared tool layer (search, detail, similar, audit
trail, accuracy, failed jobs), and returns a grounded answer plus the tool
trace so the user can see exactly what data the answer came from.

The agent acts as the authenticated API user — tools scope to their
organization and role, so the model can never read past the caller's own
permissions. Without an OpenAI key a deterministic fallback answers from the
same tools, keeping the endpoint fully functional in development.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.core.config import settings
from app.services import invoice_tools

logger = structlog.get_logger("app.services.ap_assistant")

INSTRUCTIONS = (
    "You are an accounts-payable operations assistant for an enterprise invoice "
    "platform. Answer the user's question using the provided tools; chain calls "
    "when needed (e.g. search first, then fetch detail or audit trail). Ground "
    "every claim in tool results — never invent invoice data. Reference invoices "
    "by invoice number. Be concise and actionable: if an invoice is blocked, say "
    "why (failed validation rules, low confidence, anomaly flags, failed jobs) "
    "and what the reviewer should do next. Amounts are decimal strings."
)

# The assistant deliberately gets no write tools: reprocessing/approving stay
# behind explicit human clicks in the cockpit. Read-only tools mean a prompt-
# injected or confused model can waste tokens, not mutate invoice state.
_READ_TOOLS: dict[str, Any] = {
    "search_invoices": invoice_tools.tool_search_invoices,
    "get_invoice": invoice_tools.tool_get_invoice,
    "find_similar_invoices": invoice_tools.tool_find_similar_invoices,
    "invoice_audit_trail": invoice_tools.tool_invoice_audit_trail,
    "extraction_accuracy": invoice_tools.tool_extraction_accuracy,
    "list_failed_jobs": invoice_tools.tool_list_failed_jobs,
}

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "search_invoices",
        "description": (
            "Search invoices with a natural-language query; returns interpreted filters and matching invoices."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_invoice",
        "description": (
            "Full detail for one invoice by UUID: fields, line items, validation results with "
            "explanations, extraction confidences, processing jobs, reviews."
        ),
        "parameters": {
            "type": "object",
            "properties": {"invoice_id": {"type": "string"}},
            "required": ["invoice_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "find_similar_invoices",
        "description": "Most similar invoices to one invoice by embedding similarity (duplicate triage).",
        "parameters": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["invoice_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "invoice_audit_trail",
        "description": "Recent audit events for one invoice, newest first.",
        "parameters": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["invoice_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "extraction_accuracy",
        "description": "Per-field AI extraction accuracy per prompt version, from reviewer corrections.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "list_failed_jobs",
        "description": "Failed invoice processing jobs in the organization, newest first.",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            "additionalProperties": False,
        },
    },
]


class AssistantError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssistantAnswer:
    answer: str
    model_name: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


def ask_assistant(db: Any, *, user: Any, question: str) -> AssistantAnswer:
    question = question.strip()
    if not question:
        raise AssistantError("Question must not be empty.")
    if not settings.assistant_enabled:
        raise AssistantError("The assistant is disabled for this deployment.")

    if settings.openai_api_key:
        try:
            return _ask_with_llm(db, user=user, question=question)
        except AssistantError:
            raise
        except Exception as exc:
            # Provider hiccups degrade to the deterministic path instead of a 500.
            logger.warning("assistant.llm_failed", error_message=str(exc))
    return _ask_fallback(db, user=user, question=question)


def _execute_tool(db: Any, *, user: Any, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    tool = _READ_TOOLS.get(name)
    if tool is None:
        return {"error": "unknown_tool", "message": f"Tool '{name}' does not exist."}
    try:
        return tool(db, user=user, **arguments)
    except (LookupError, ValueError) as exc:
        # Returned (not raised) so the model can read the error and self-correct.
        return {"error": "invalid_request", "message": str(exc)}


def _ask_with_llm(db: Any, *, user: Any, question: str) -> AssistantAnswer:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    model_name = settings.openai_assistant_model or settings.openai_extraction_model
    input_items: list[Any] = [{"role": "user", "content": question}]
    trace: list[dict[str, Any]] = []

    # One extra round always remains for the model to produce the final text
    # after its last tool result, so the cap bounds tool calls, not the answer.
    for _ in range(max(settings.assistant_max_tool_calls, 1) + 1):
        response = client.responses.create(
            model=model_name,
            instructions=INSTRUCTIONS,
            input=input_items,
            tools=TOOL_DEFINITIONS,
        )
        function_calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
        if not function_calls or len(trace) >= settings.assistant_max_tool_calls:
            answer = (response.output_text or "").strip()
            if not answer:
                raise AssistantError("The assistant did not produce an answer.")
            return AssistantAnswer(answer=answer, model_name=model_name, tool_calls=trace)

        input_items.extend(response.output)
        for call in function_calls:
            try:
                arguments = json.loads(call.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            result = _execute_tool(db, user=user, name=call.name, arguments=arguments)
            trace.append({"tool": call.name, "arguments": arguments})
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result),
                }
            )

    raise AssistantError("The assistant exceeded its tool-call budget without answering.")


_UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def _ask_fallback(db: Any, *, user: Any, question: str) -> AssistantAnswer:
    """Deterministic keyless path: pick the obviously-relevant tool from the
    question's shape and format its result as a readable answer."""
    trace: list[dict[str, Any]] = []
    lowered = question.lower()

    uuid_match = _UUID_PATTERN.search(question)
    if uuid_match:
        invoice_id = uuid_match.group(0)
        detail = _execute_tool(db, user=user, name="get_invoice", arguments={"invoice_id": invoice_id})
        trace.append({"tool": "get_invoice", "arguments": {"invoice_id": invoice_id}})
        if "error" in detail:
            return AssistantAnswer(
                answer=f"I couldn't load that invoice: {detail['message']}",
                model_name="assistant-fallback",
                tool_calls=trace,
            )
        return AssistantAnswer(
            answer=_format_invoice_answer(detail),
            model_name="assistant-fallback",
            tool_calls=trace,
        )

    if any(word in lowered for word in ("fail", "stuck", "error", "broken")):
        jobs = _execute_tool(db, user=user, name="list_failed_jobs", arguments={"limit": 10})
        trace.append({"tool": "list_failed_jobs", "arguments": {"limit": 10}})
        failed = jobs.get("failed_jobs", [])
        if not failed:
            answer = "No failed processing jobs right now — nothing looks stuck."
        else:
            lines = [f"{len(failed)} failed processing job(s):"]
            lines += [
                f"- invoice {job['invoice_id']}: {job['last_error'] or 'no error recorded'} "
                f"(attempts: {job['attempts']})"
                for job in failed[:5]
            ]
            lines.append("These can be reprocessed from the failed-jobs dashboard once the cause is fixed.")
            answer = "\n".join(lines)
        return AssistantAnswer(answer=answer, model_name="assistant-fallback", tool_calls=trace)

    if "accura" in lowered or "quality" in lowered:
        report = _execute_tool(db, user=user, name="extraction_accuracy", arguments={})
        trace.append({"tool": "extraction_accuracy", "arguments": {}})
        versions = report.get("prompt_versions", [])
        if not versions:
            answer = "No reviewed invoices yet, so extraction accuracy cannot be measured."
        else:
            latest = versions[-1]
            lines = [
                f"Extraction accuracy for prompt {latest['prompt_version']} "
                f"({latest['reviewed_invoices']} reviewed invoice(s)):"
            ]
            lines += [
                f"- {entry['field']}: {entry['accuracy'] if entry['accuracy'] is not None else 'n/a'}"
                for entry in latest["fields"]
            ]
            answer = "\n".join(lines)
        return AssistantAnswer(answer=answer, model_name="assistant-fallback", tool_calls=trace)

    results = _execute_tool(db, user=user, name="search_invoices", arguments={"query": question, "limit": 10})
    trace.append({"tool": "search_invoices", "arguments": {"query": question, "limit": 10}})
    invoices = results.get("invoices", [])
    if not invoices:
        answer = "No invoices matched that question. Try an invoice number, supplier name, status, or amount."
    else:
        lines = [f"{len(invoices)} matching invoice(s):"]
        lines += [
            f"- {invoice['invoice_number']}: {invoice['status']}, "
            f"{invoice['total_amount'] or '?'} {invoice['currency']}"
            for invoice in invoices[:10]
        ]
        answer = "\n".join(lines)
    return AssistantAnswer(answer=answer, model_name="assistant-fallback", tool_calls=trace)


def _format_invoice_answer(detail: dict[str, Any]) -> str:
    lines = [
        f"Invoice {detail['invoice_number']} is in status '{detail['status']}' "
        f"({detail['total_amount'] or '?'} {detail['currency']})."
    ]
    failures = [result for result in detail.get("validation_results", []) if not result["passed"]]
    if failures:
        lines.append("Open validation issues:")
        for failure in failures:
            explanation = failure.get("explanation") or failure["message"]
            fix = failure.get("suggested_fix")
            lines.append(f"- {failure['rule_code']}: {explanation}" + (f" Fix: {fix}" if fix else ""))
    failed_jobs = [job for job in detail.get("processing_jobs", []) if job["status"] == "failed"]
    for job in failed_jobs:
        lines.append(f"Processing job {job['processing_job_id']} failed: {job['last_error'] or 'no error recorded'}.")
    if not failures and not failed_jobs:
        lines.append("No open validation issues or failed jobs.")
    return "\n".join(lines)
