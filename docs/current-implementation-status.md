# Current Implementation Status

This document describes what is implemented in the repository today. It intentionally does not describe target-state behavior unless the behavior exists in code and tests.

## Implemented

### Backend application shell

- FastAPI app factory in `backend/app/main.py`.
- API router in `backend/app/api/router.py`.
- Health endpoint.
- Invoice route group under `/api/v1/invoices`.

### Invoice API contract skeleton

- `POST /api/v1/invoices` accepts invoice metadata.
- `POST /api/v1/invoices/{invoice_id}/status` validates a requested status transition.
- The create endpoint is wired to persist invoice metadata and an upload audit log through the database session.
- `POST /api/v1/invoices/upload` is wired to validate and store invoice files with metadata.
- Upload creates a durable `processing_jobs` row for invoice extraction.
- Upload publishes queued processing jobs to Redis.
- A Docker worker service consumes queued jobs and updates job/invoice status.
- Worker failures are recorded with a bounded automatic retry policy controlled by `PROCESSING_JOB_MAX_ATTEMPTS`; retryable failures are scheduled through a Redis delayed-retry set using `PROCESSING_JOB_RETRY_BACKOFF_SECONDS`.
- The worker persists extraction payloads, prompt version references, line items, and validation results.
- The worker uses a production OpenAI Responses API extractor when `OPENAI_API_KEY` is configured, otherwise it uses the development extractor.
- Extraction persistence stores provider token usage and configurable estimated cost when provider usage is returned.
- Processing job lookup, failed-job listing, and manual reprocess endpoints exist.
- Invoice list and detail endpoints expose review-ready invoice state.
- Current business API endpoints require a valid HS256 bearer token for a database-backed user. Operational `/health` and `/metrics` endpoints are unauthenticated.
- `POST /api/v1/auth/login` verifies database-backed password hashes and issues HS256 bearer tokens.
- Admin user-management endpoints list, create, update, and set passwords for users within the authenticated admin's organization.
- Users can change their own password after current-password verification.
- User-management actions write audit events, and role updates protect against demoting the last organization admin.
- A bootstrap script creates the first organization admin for deployments.
- Invoice, supplier, and processing-job API paths enforce the authenticated user's organization boundary.
- Invoice file download URL creation is tenant-scoped and returns short-lived HMAC-signed URLs.
- Signed invoice file download validates expiry and signature before reading from private local storage.
- Invoice upload attempts are rate-limited by client and path with configurable in-process limits.
- Requests receive generated or preserved `X-Request-ID` response headers.
- API error envelopes are applied globally and include the active request ID.
- The FastAPI app emits structured JSON request completion logs with request ID, method, path, status code, and duration.
- `GET /metrics` exposes Prometheus-style API request count, API request duration, and Redis processing queue depth metrics.
- Tenant-scoped audit-log listing exists with entity, action, and limit filters.
- Audit log rows are append-only at the SQLAlchemy application layer; update and delete attempts raise an application error.
- Worker logs include processing job IDs, invoice IDs, completion status, error messages, and processing duration.
- An importable Grafana dashboard exists at `infra/monitoring/grafana/dashboards/invoice-platform-overview.json`.
- A GitHub Actions CI workflow builds the Docker Compose stack, verifies migrations, runs backend tests, and smoke-tests `/health` and `/metrics`.
- Production-oriented Compose, staging/production env templates, release-check, migration, and smoke-test scripts exist.
- A deployment guide documents release gates, image build, Compose deployment assets, environment variables, migration procedure, rollback procedure, backup validation, and a security review checklist.
- Review submission requires a reviewer/admin user, uses the authenticated user as the reviewer, stores corrected fields, creates review records, transitions invoices to approved/rejected, and audits corrections and decisions.
- Upload and invoice create use the authenticated user's organization and user ID instead of trusting client-supplied tenant or actor fields.
- The status endpoint is wired to load persisted invoice state by authenticated tenant before applying transition rules.
- Processing-job inspection and reprocess endpoints are tenant-scoped, and reprocess uses the authenticated user as actor.
- `GET /api/v1/events/stream` provides an authenticated, tenant-scoped Server-Sent Events stream backed by Redis pub/sub (`app/services/events.py`); the worker and review/reprocess service paths publish a minimal `{type, invoice_id, processing_job_id, status}` signal after each relevant commit so the frontend can invalidate and refetch, rather than push full payloads over the wire.
- A Dockerized React, Vite, TypeScript, and Tailwind frontend scaffold exists in `frontend/`.
- The previous FastAPI-served static cockpit has been retired; FastAPI is API-only.
- A host-side headless Chrome smoke script verifies the React frontend shell renders the cockpit workflow surfaces.
- Runtime database behavior has been smoke-tested through Docker for metadata create and multipart upload.

### Domain models

SQLAlchemy models exist for:

- organizations
- users
- suppliers
- invoices
- invoice files
- invoice line items
- invoice extractions
- invoice validation results
- invoice reviews
- audit logs
- processing jobs
- prompt versions

### Domain services

Implemented pure-Python services:

- invoice workflow transition rules
- invoice validation checks for required fields, supplier match, duplicate flag, total amount, approval threshold, confidence threshold, and line item totals
- audit-event construction for upload and status-change events
- append-only audit-log model guard for update/delete attempts
- database-backed invoice metadata intake
- database-backed invoice status transition with audit log creation
- invoice file validation for allowed extension, MIME type, empty files, and max file size
- upload request rate limiting with configurable request/window thresholds
- SHA-256 checksum duplicate upload guard
- local filesystem and S3-compatible storage adapters using organization/invoice-scoped storage keys
- signed invoice file download URL generation and validation
- request context propagation for request IDs
- global API error-envelope handlers for domain, framework, validation, and unexpected errors
- structured JSON request logging middleware
- in-process API request metrics registry
- Redis processing queue depth metric collection
- processing job payload rules and upload-time extraction job creation
- Redis queue publish/consume flow
- worker-driven processing job status transitions
- bounded automatic retry policy for failed worker attempts
- failed-job inspection and manual reprocess flow
- strict extraction payload schema
- OpenAI Responses API extractor with structured JSON schema output configuration
- development extractor fallback for local Docker runs without external API access
- prompt version persistence
- extraction and validation result persistence
- review queue/detail retrieval
- HS256 bearer-token authentication dependency for database-backed users
- PBKDF2-HMAC-SHA256 password hashing and verification
- credential login and access-token issuance
- tenant-scoped user administration
- first-admin bootstrap script
- backend role dependency for privileged actions
- tenant-scoped invoice intake, review, status-transition, and processing-job queries
- review correction persistence
- review approve/reject workflow
- review correction and decision audit events
- provider response parsing, invalid-response errors, token usage parsing, and cost estimate helpers
- invoice embedding service with OpenAI `text-embedding-3-small` and a deterministic development fallback embedder
- best-effort worker embedding persistence after extraction (failures logged, never fail the job)
- pgvector-backed tenant-scoped similar-invoice search (cosine distance over an HNSW index)

### Tests

The current test suite uses `unittest` and covers:

- allowed and blocked invoice status transitions
- validation pass/review routing
- duplicate invoice number validation result
- line item total mismatch validation result
- audit-event metadata
- file validation rules
- local storage round-trip/delete behavior and S3-compatible storage client calls
- processing job payload rules
- extraction schema parsing, response text parsing, file data URL formatting, and token cost estimates
- review correction and decision audit-event metadata
- login success, bad password rejection, missing password-hash rejection, login-token access to review queue, tenant-scoped user administration, user password changes, user-management audit events, last-admin protection, review queue/detail, approve correction, reject, stale update conflict, unsupported correction field, duplicate invoice-number correction, missing authentication, role denial, authenticated actor attribution, cross-tenant invoice isolation, cross-tenant supplier rejection, signed file download, request ID propagation, global error envelope handling, metrics output, and tenant-scoped processing-job API paths

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

## Partially Implemented

### Database layer

SQLAlchemy base/session configuration exists. Alembic configuration and an initial schema migration now exist. The migration has been executed successfully through Docker.

### Production readiness checklist

The checklist exists and is updated as each slice becomes implemented, tested, and operationally usable. Staging, production infrastructure, and deployment-specific S3/MinIO smoke validation remain open.

### Security and multi-tenancy

All current business API endpoints now have authenticated user lookup where bearer auth is the access mechanism. Invoice create/upload/list/detail/status/review, file download URL creation, and processing-job list/detail/reprocess paths are scoped to the authenticated user's organization, privileged actions have backend role checks, and signed file downloads validate short-lived HMAC signatures. Operational `/health` and `/metrics` endpoints are intentionally unauthenticated. Future supplier, audit, and admin surfaces still need equivalent enforcement when those endpoints are added.

### Observability

Request IDs, structured JSON request completion logs, API request count/duration metrics, Redis queue depth metrics, failed extraction job totals, validation failure totals, completed processing duration totals, AI estimated cost totals, worker job/invoice log enrichment, and an importable Grafana dashboard are implemented. Distributed traces remain pending.

### Local infrastructure

Docker Compose starts the FastAPI backend, worker, PostgreSQL, and Redis. The backend runs migrations on startup. Local Compose uses filesystem-backed private storage by default; the production Compose contract can switch API and worker storage to S3-compatible object storage with environment variables. It does not yet run monitoring.

### Frontend

The frontend is a Dockerized React/Vite/TypeScript application under `frontend/` and runs as a separate web service on port 3000. It implements httpOnly-cookie-backed login/logout with silent token refresh, self-service password change, invoice upload, review queue with header-field corrections, approve/reject decisions with `expected_updated_at` optimistic-concurrency handling, failed-job recovery, signed file opening, audit-log filtering, and admin user creation/listing/update/password reset.

Data layer: all data fetching and mutation runs through `@tanstack/react-query` (`frontend/src/queries/`), one hook file per resource (invoices, jobs, audit, users, auth, realtime), replacing an earlier single-hook manual-state controller. Mutations invalidate the relevant query keys; a 409 `invoice_review_conflict` response surfaces a distinct "updated by someone else" toast instead of a generic error; a `SessionExpiredError` from any query/mutation is handled once, globally, rather than per call site.

Navigation: `@tanstack/react-router` provides URL-synced routing (`/`, `/upload`, `/review`, `/failed`, `/audit`, `/users`), browser back/forward, and deep-linkable invoice review links (`/review?invoiceId=...`). The route tree is assembled in code (`frontend/src/app/router.ts`) rather than via the file-based codegen plugin, since that plugin requires Node >=20 and the primary local dev flow historically ran on Node 18; the Docker frontend image itself uses Node 20 and could adopt file-based routing later if desired.

Design system: shadcn/ui (Radix primitives + Tailwind) provides Button, Card, Badge, Alert, AlertDialog, Table, Dropdown Menu, Command, Checkbox, Skeleton, and Dialog components, replacing hand-rolled CSS classes; a light/dark theme toggle is wired through CSS custom properties.

Data tables (`frontend/src/components/common/DataTable.tsx`, backing invoices, failed jobs, audit logs, and users): client-side sorting, pagination, and column resizing; opt-in column-visibility toggling and CSV export on all four tables; opt-in row selection with bulk actions (approve/reject invoices, reprocess jobs) on the invoices and failed-jobs tables. Bulk actions are client-side batched (one request per row via `Promise.allSettled`) since the backend has no bulk endpoints, and report a single summary toast.

Real-time updates: the frontend subscribes to `GET /api/v1/events/stream` (Server-Sent Events) while signed in and invalidates the matching react-query cache entries on receipt, so job/invoice status changes made in one browser tab (or by the worker) appear in other open tabs without a manual refresh. A connection indicator in the header shows live/reconnecting state.

Safety and accessibility: confirmation dialogs gate reject-invoice (single and bulk) and password-reset actions; form fields wire `aria-invalid`/`aria-describedby` for validation errors; icon-only buttons carry `aria-label`; a skip-to-content link and a `Cmd/Ctrl+K` command palette (RBAC-aware tab navigation plus quick actions) support keyboard-first use; a breadcrumb appears on the invoice review drill-down.

Browser smoke automation and authenticated Playwright workflow coverage exist. Line-item editing and richer dashboard analytics remain pending.

### Deployment

The repository includes a Docker-backed GitHub Actions CI workflow, a production-oriented Compose file, staging/production env templates, release scripts, and a production deployment guide. Actual hosted staging and production environments are not provisioned in this repository.

## Not Implemented Yet

- distributed tracing
- staging environment
- production deployment manifests for a specific managed hosting platform

## Important Gap

The architecture diagrams are target-state diagrams. They intentionally include components that are not provisioned by the local stack yet, such as managed S3-compatible object storage and monitoring.

The persisted invoice intake, upload, worker processing, automatic retry behavior, extraction persistence, failed-job inspection, reprocess, review, user administration, current security-boundary paths, and reviewer cockpit static serving have been smoke-tested through the dockerized backend, worker, Redis, and PostgreSQL. Broader provider-specific failure classification and deeper browser automation are still needed.
