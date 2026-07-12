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
- `POST /api/v1/invoices`
- `POST /api/v1/invoices/{invoice_id}/status`
- `GET /api/v1/processing-jobs/{processing_job_id}`
- `GET /api/v1/processing-jobs/failed`
- `POST /api/v1/processing-jobs/{processing_job_id}/reprocess`

The current invoice endpoints establish request/response contracts and workflow transition rules. The backend also has testable domain services for invoice validation routing and audit-event construction.

Invoice metadata persistence, file upload persistence, audit log persistence, upload-time processing job creation, Redis worker execution, extraction persistence, validation result persistence, failed-job inspection, manual reprocess, and persisted status transitions are wired in code and backed by Alembic migrations.

Production OpenAI extraction and review workflows are the next implementation milestones.
