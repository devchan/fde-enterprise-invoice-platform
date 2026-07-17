# FDE Enterprise AI Invoice Processing Platform

Production-grade learning project for becoming a Forward Deployed Engineer.

The goal is to build an enterprise invoice processing platform that accepts invoice uploads, extracts structured data with AI, validates the invoice against business rules, routes uncertain cases to human review, and keeps a complete audit trail.

## Target Stack

- Backend: Python, FastAPI, Pydantic, SQLAlchemy
- Database: PostgreSQL
- Queue/cache: Redis
- Worker: Celery or RQ
- AI: OpenAI API
- Vector search: pgvector
- Storage: local development storage and S3-compatible object storage
- Frontend: React with Vite
- DevOps: Docker Compose, GitHub Actions
- Observability: structured logs, OpenTelemetry, Prometheus, Grafana

## Project Structure

```text
backend/     FastAPI backend and worker code
frontend/    Web application
infra/       Docker, deployment, and operations assets
docs/        Architecture, diagrams, and production readiness docs
tests/       Automated tests
```

## Product Documentation

Start with [docs/README.md](docs/README.md). The documentation is organized as an enterprise product spec:

- current implementation status
- target architecture
- API contract
- data model specification
- implementation roadmap
- operational runbook
- engineering standards
- production readiness checklist

## First Milestone

Build this flow first:

```text
Login
-> upload invoice
-> store file securely
-> queue processing job
-> AI extracts structured invoice JSON
-> validation engine runs
-> reviewer edits fields
-> reviewer approves or rejects
-> audit log records every step
```

## Current Implementation Status

- FastAPI application shell
- Health endpoint
- Invoice API route structure
- SQLAlchemy database base/session setup
- Alembic migration scaffold and initial schema migration
- Core invoice, supplier, user, and organization models
- Audit log model
- Explicit invoice status workflow rules
- Database-backed invoice metadata intake service
- Secure invoice upload policy for PDF/JPEG/PNG files
- Configurable rate limiting for invoice upload attempts
- Local and S3-compatible storage adapters with organization/invoice-scoped storage keys
- SHA-256 checksum calculation and duplicate upload guard
- Short-lived signed invoice file download URLs
- Processing job model and upload-time extraction job creation
- Redis-backed worker service for queued invoice extraction jobs
- Strict invoice extraction schema and prompt version persistence
- OpenAI Responses API extractor wiring with development fallback
- Provider token usage and configurable cost estimate persistence
- Worker persists extraction payloads, line items, and validation results
- pgvector-backed invoice embeddings (OpenAI text-embedding-3-small with deterministic dev fallback) written by the worker after extraction
- Tenant-scoped similar-invoice search endpoint using pgvector cosine distance over an HNSW index
- Similar-invoices panel in the reviewer cockpit with near-duplicate flagging and click-through navigation
- Failed processing job inspection and manual reprocess endpoints
- Bounded automatic retry policy for worker processing failures
- Invoice list, detail, review correction, approve, and reject endpoints
- Password-hash-backed login endpoint that issues HS256 bearer tokens
- Tenant-scoped user-admin endpoints for user list/create/update/password management
- First-admin bootstrap script for deployments
- HS256 bearer-token user lookup for current non-health API endpoints
- Tenant-scoped invoice and processing-job API queries
- Role enforcement for upload, status transition, review, and reprocess actions
- Generated/preserved `X-Request-ID` headers and JSON request completion logs
- Prometheus-style `/metrics` endpoint for API request counts, API latency, and Redis queue depth
- Metrics for failed extraction jobs, validation failures, processing duration, and AI estimated cost
- Importable Grafana dashboard for operational metrics
- Worker JSON logs include processing job IDs, invoice IDs, status, errors, and duration
- Docker-backed GitHub Actions CI workflow for migrations, tests, health, and metrics smoke checks
- Production-oriented Compose file, staging/production env templates, and release/migration/smoke scripts
- Deployment guide with environment inventory, migration procedure, rollback, backup validation, and security review checklist
- Dockerized React/Vite frontend scaffold in `frontend/` for the reviewer cockpit
- Invoice upload UI in the static reviewer cockpit
- Failed processing-job dashboard and manual reprocess UI in the static reviewer cockpit
- Tenant-scoped audit-log API and audit-log UI in the static reviewer cockpit
- Application-level append-only enforcement for audit log records
- Admin user-management UI in the static reviewer cockpit
- Review correction and decision audit events
- Persisted status-transition service using invoice state from the database
- Unit tests for critical status transitions
- Validation engine for first-pass invoice review routing
- Audit-event builders for invoice upload and status changes
- Unit tests for validation routing and audit metadata
- Unit tests for invoice file validation
- Docker-backed API integration tests for the invoice workflow, signed file downloads, processing jobs, and tenant/RBAC guards
- Reviewer cockpit data layer fully migrated to TanStack Query (per-resource hooks, centralized session-expiry/optimistic-concurrency handling)
- TanStack Router URL-based navigation with deep-linkable invoice review URLs
- shadcn/ui design system (Radix + Tailwind) with a light/dark theme toggle
- Data tables with column visibility, CSV export, resizing, and bulk row actions (client-side batched) for invoices and failed jobs
- `GET /api/v1/events/stream` Server-Sent Events endpoint (Redis pub/sub) for live invoice/job status updates in the cockpit, replacing polling
- Confirmation dialogs for reject-invoice and password-reset actions; accessibility fixes for form errors and icon-only controls
- Cmd/Ctrl+K command palette and invoice-review breadcrumb navigation in the cockpit

## Local Development

Docker is the recommended local runtime.

Build and start the full stack:

```bash
docker compose up -d --build
```

Run tests inside the backend container:

```bash
docker compose exec -T backend python -m pytest -q
```

Run cockpit browser smoke from the host:

```bash
scripts/check-cockpit-smoke.sh
```

Health check:

```bash
docker compose exec -T backend curl -fsS http://localhost:8000/health
```

Frontend:

```bash
docker compose up -d frontend
```

Then open:

```text
http://localhost:3000/
```

API URL:

```text
http://localhost:8010
```

See [Docker Development](docs/docker-development.md) for operations commands.

### Host Python Option

Copy the example environment file:

```bash
cp .env.example .env
```

Start local services:

```bash
docker compose up -d
```

Run the backend locally:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Health check:

```text
GET http://localhost:8000/health
```
