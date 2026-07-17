# Backend

FastAPI backend for the enterprise AI invoice processing platform.

## Responsibilities

- Authentication and RBAC
- Invoice upload API
- Invoice status workflow
- Supplier and validation rules
- Audit logging
- Background job creation
- AI extraction orchestration

## Development

Recommended Docker workflow from repository root:

```bash
docker compose up -d --build
docker compose exec -T backend python -m pytest -q
```

Host Python workflow:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## API Surface

- `GET /health`
- `POST /api/v1/auth/login` (plus refresh/logout session endpoints)
- `GET`/`POST /api/v1/invoices` and `POST /api/v1/invoices/upload`
- `POST /api/v1/invoices/nl-search` — natural-language invoice search
- `GET /api/v1/invoices/{invoice_id}` and `POST /api/v1/invoices/{invoice_id}/review`
- `POST /api/v1/invoices/{invoice_id}/status`
- `GET /api/v1/invoices/{invoice_id}/similar` — pgvector similar-invoice search
- `GET /api/v1/invoices/{invoice_id}/files/{file_id}/download-url` and signed `/download`
- `GET /api/v1/extraction/providers` and `GET /api/v1/extraction/accuracy`
- `POST /api/v1/assistant/ask` — read-only tool-calling AP assistant with tool trace
- `GET /api/v1/processing-jobs/{processing_job_id}`, `GET /api/v1/processing-jobs/failed`, `POST /api/v1/processing-jobs/{processing_job_id}/reprocess`
- `GET /api/v1/audit-logs`, user-admin endpoints under `/api/v1/users`
- `GET /api/v1/events/stream` (Server-Sent Events), `GET /metrics`

See [docs/api-contract.md](../docs/api-contract.md) for the full contract.

An MCP server exposes the same capabilities to Model Context Protocol clients:

```bash
MCP_SERVICE_USER_EMAIL=ops@example.com python -m app.mcp.server
```

The worker pipeline runs AI extraction (OpenAI/Gemini with a deterministic development fallback) with per-field confidences, line-item categorization, retrieval-augmented few-shot prompting, optional model tiering, business validation with reviewer-facing explanations, embedding persistence for similarity search, post-extraction anomaly detection, and confidence-gated auto-approval — all audited and backed by Alembic migrations.
