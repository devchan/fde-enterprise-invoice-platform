# Implementation Roadmap

The platform should be built in production-grade slices. Each slice must add behavior, tests, and documentation together.

## Phase 1: Durable Invoice Intake

Goal: make invoice creation real and auditable.

Status: implemented in code and smoke-tested through Docker. Full integration tests still need to be added.

Deliverables:

- Alembic migration setup
- database-backed invoice create endpoint
- database-backed duplicate invoice number handling per organization and supplier
- audit log model and migration
- persisted `invoice.uploaded` audit event
- consistent API error format
- tests for successful create, duplicate create, and audit write

Exit criteria:

- `POST /api/v1/invoices` writes an invoice row.
- duplicate invoice numbers return a controlled conflict response.
- audit events are persisted in the same transaction as the invoice.
- tests run from a clean checkout.

Remaining hardening before Phase 1 is production-complete:

- add integration tests using a real or disposable test database
- verify foreign-key failure responses for missing organization, supplier, and uploader
- apply the consistent error envelope globally, not only invoice endpoints

## Phase 2: Secure File Upload

Goal: accept invoice documents safely.

Status: implemented in code with local filesystem storage, an S3-compatible storage adapter, tenant-scoped signed download URLs, and Docker-backed integration tests. A live S3/MinIO smoke test is still pending for deployment-specific validation.

Deliverables:

- upload endpoint using multipart form data
- file size limits
- MIME type and extension validation
- SHA-256 checksum calculation
- duplicate upload detection by checksum
- local development storage and configurable S3-compatible production storage
- private storage keys scoped by organization and invoice
- signed download URL contract

Exit criteria:

- invalid files are rejected before storage.
- duplicate files are detected deterministically.
- stored files are private by default.

Remaining hardening before Phase 2 is production-complete:

- run deployment-specific S3/MinIO smoke tests before production cutover
- add antivirus/malware scanning decision if required by deployment context

## Phase 3: Queue and Processing Jobs

Goal: move slow work out of API requests.

Status: implemented and smoke-tested through Docker. Upload creates queued jobs, the worker consumes Redis jobs, retryable failures are delayed with exponential backoff up to `PROCESSING_JOB_MAX_ATTEMPTS`, final failures can be inspected, and failed jobs can be manually reprocessed.

Deliverables:

- processing job model
- worker process
- Redis-backed queue
- retry policy
- failed job inspection
- manual reprocess endpoint
- job status transitions and audit events

Exit criteria:

- invoice upload returns quickly.
- extraction jobs run asynchronously.
- failed processing can be inspected and retried.

Remaining hardening before Phase 3 is production-complete:

- broaden worker failure-mode coverage for provider-specific transient/permanent error classification

## Phase 4: AI Extraction

Goal: extract structured invoice data with traceability.

Status: extraction schema, prompt version persistence, extraction rows, line items, validation rows, worker integration, and OpenAI Responses API client wiring are implemented. The schema now also carries per-field confidences and line-item categories, and extraction is retrieval-augmented with approved same-supplier examples (see Phase 9). The flow has been smoke-tested with the development extractor; live OpenAI verification still requires a configured API key and representative invoice fixtures.

Deliverables:

- strict extraction JSON schema
- OpenAI extraction service
- prompt version model
- model name, prompt version, token usage, confidence, and cost persistence
- invalid AI response handling
- extraction completion and failure audit events

Exit criteria:

- every AI result is explainable by prompt version and model.
- invalid model output cannot corrupt invoice state.

Remaining hardening before Phase 4 is production-complete:

- run live provider integration tests with `OPENAI_API_KEY` and representative PDF/image fixtures
- verify provider token usage and cost persistence from real responses
- classify transient provider errors separately from permanent extraction errors
- add integration tests around extraction persistence

## Phase 5: Validation and Human Review

Goal: route invoices to approval or review based on policy.

Status: backend review workflow is implemented and a Dockerized React/Vite frontend application now lives in `frontend/`. Invoice list/detail endpoints, review correction persistence, approve/reject decisions, optimistic `updated_at` conflict checks, correction/decision audit events, authenticated reviewer attribution, tenant-scoped review queries, reviewer/admin role checks, and API integration tests exist. The previous static cockpit has been retired; the React frontend now covers email/password login, logout, self-service password change, invoice upload, failed processing-job dashboard and reprocess actions, audit-log viewing/filtering, admin user creation/listing/update/password reset, review queue loading, invoice detail, header-field corrections, approve/reject submission, signed file URL creation, and validation/extraction panels. The frontend's data layer is fully migrated to TanStack Query (per-resource hooks, centralized session-expiry and 409-conflict handling, replacing an earlier single manual-state controller), navigation runs on TanStack Router (URL-synced tabs, deep-linkable review URLs), the design system is shadcn/ui (Radix + Tailwind, with a light/dark toggle), and the reviewer cockpit subscribes to a Server-Sent Events stream (`GET /api/v1/events/stream`, Redis pub/sub) so job/invoice status changes appear live instead of requiring a manual refresh. Line-item editing and richer dashboard analytics remain pending.

Deliverables:

- persisted validation results
- review queue endpoint
- invoice detail endpoint
- reviewer correction endpoint
- approve/reject endpoint
- correction audit events
- approval/rejection audit events
- optimistic concurrency protection for review edits
- frontend review queue and correction UI

Implemented slice:

- React, Vite, TypeScript, and Tailwind frontend application in `frontend/`
- email/password login against `POST /api/v1/auth/login`
- token-backed browser session storage and logout
- self-service password change through `POST /api/v1/users/me/password`
- multipart invoice upload against `POST /api/v1/invoices/upload`
- failed-job dashboard from `GET /api/v1/processing-jobs/failed`
- manual reprocess action against `POST /api/v1/processing-jobs/{processing_job_id}/reprocess`
- audit-log panel from `GET /api/v1/audit-logs`
- admin user-management panel from `GET`, `POST`, `PATCH`, and password reset paths under `/api/v1/users`
- review queue loading from `GET /api/v1/invoices`
- invoice detail view
- correction form for invoice number, invoice date, total amount, and currency
- approve/reject submission with `expected_updated_at`
- validation, extraction, and file panels
- signed file URL opening from the review screen
- host-side headless Chrome smoke coverage for the served cockpit shell
- host-side authenticated Playwright workflow coverage for sign-in, protected navigation, upload, review queue visibility, audit filtering, and user creation
- TanStack Table-backed operational tables for invoices, failed jobs, audit logs, and users, with column visibility, CSV export, resizing, and bulk row actions (client-side batched) on invoices and failed jobs
- React Hook Form and Zod sign-in validation pattern
- TanStack Query data layer (`frontend/src/queries/`) for all reads/writes, replacing manual `useState`/`useEffect` fetching
- TanStack Router URL-based navigation (`/`, `/upload`, `/review`, `/failed`, `/audit`, `/users`), assembled in code rather than via file-based codegen
- shadcn/ui component library with a light/dark theme toggle
- `GET /api/v1/events/stream` Server-Sent Events subscription with react-query cache invalidation for live updates
- confirmation dialogs for reject-invoice and password-reset actions
- Cmd/Ctrl+K command palette and invoice-review breadcrumb
- AI review signals in the cockpit: low-confidence field highlighting, validation explanations with suggested fixes, anomaly badges, line-item category badges, an auto-approved badge, and an "Ask AI" natural-language search bar (see Phase 9)

Exit criteria:

- reviewers can correct fields and approve/reject invoices.
- every correction and decision is auditable.

Remaining hardening before Phase 5 is production-complete:

- add line-item correction UX
- add reviewer assignment and approval-limit policy if enterprise rules require them
- extend browser coverage to approve/reject and failed-job reprocess paths with deterministic fixtures

## Phase 6: Security and Multi-Tenancy

Goal: make enterprise access boundaries enforceable.

Status: implemented for all current business API endpoints. HS256 bearer tokens identify database-backed users; password-hash-backed login issues access tokens; invoice create/upload/list/detail/status/review, file download URL creation, processing-job list/detail/reprocess, and user-admin paths are scoped to the authenticated user's organization; signed file downloads validate short-lived HMAC signatures; privileged actions enforce backend roles. Operational `/health` and `/metrics` endpoints are unauthenticated. Future supplier and audit endpoints still need equivalent enforcement when they are added.

Deliverables:

- JWT authentication
- role model and permissions
- backend RBAC dependencies
- tenant-scoped repository layer
- security tests for cross-tenant access denial
- secret management documentation

Implemented slice:

- bearer-token authentication dependency
- role dependency for upload, status transition, review, and reprocess actions
- tenant-scoped invoice intake, file URL creation, review, status-transition, and processing-job service queries
- password-hash-backed login and access-token issuance
- tenant-scoped user administration endpoints
- user password change and admin password set endpoints
- first-admin bootstrap script
- last-admin demotion protection
- security tests for missing authentication, role denial, authenticated actor attribution, cross-tenant invoice denial, cross-tenant supplier rejection, signed file downloads, and tenant-scoped processing-job access

Exit criteria:

- users cannot access other organizations' invoices, suppliers, files, jobs, or audit logs.

## Phase 7: Observability and Operations

Goal: make the system operable.

Status: implemented except for distributed tracing. FastAPI requests receive generated or preserved `X-Request-ID` response headers, error envelopes include the active request ID, request completion is emitted as structured JSON with method/path/status/duration/request ID, `/metrics` exposes API request count, API request duration, Redis queue depth, failed extraction jobs, completed processing duration, validation failures, and AI estimated cost, worker logs include processing job IDs, invoice IDs, status, errors, and duration, failed-job and audit-log panels exist in the reviewer cockpit, and an importable Grafana dashboard exists for operations.

Deliverables:

- structured JSON logs
- request/correlation IDs
- job IDs in logs
- metrics for API latency, queue depth, extraction failures, validation failures, processing duration, and AI cost
- dashboards
- runbooks for common incidents
- backup and restore documentation

Implemented slice:

- request ID context middleware
- structured JSON API request completion logs
- request ID propagation into API error envelopes
- Prometheus-style `/metrics` endpoint
- API request count and duration metrics
- Redis processing queue depth metric
- failed extraction job metric
- completed processing duration metrics
- validation failure metric
- AI estimated cost metric
- worker job lifecycle logs with processing job ID, invoice ID, status, errors, and duration
- importable Grafana dashboard for the implemented metrics
- API integration tests for generated request IDs, preserved inbound request IDs, and error-envelope request IDs

Exit criteria:

- an operator can identify stuck invoices, failed jobs, and cost spikes without reading application code.

## Phase 8: Production Deployment

Goal: deploy safely and repeatedly.

Status: partially implemented. A Docker-backed GitHub Actions CI workflow exists for migrations, tests, health, and metrics smoke checks. Production-oriented Compose, staging/production env templates, release-check, migration, and smoke-test scripts exist. A deployment guide documents release gates, image build, environment variables, migration procedure, rollback procedure, backup validation, and security review. Actual hosted staging and production environments are still pending.

Deliverables:

- CI test pipeline
- image build pipeline
- staging environment
- production environment variable inventory
- migration run procedure
- rollback procedure
- backup validation
- security review checklist

Implemented slice:

- GitHub Actions workflow for Docker Compose build/start, Alembic head verification, backend tests, `/health` smoke test, and `/metrics` smoke test
- production-oriented standalone Compose file without development bind mounts or reload
- staging and production env templates
- release-check script for migration head, tests, health, and metrics
- migration script for Compose-based deployments
- smoke-test script for deployed API health and metrics
- image build command and API/worker runtime command documented
- production environment variable inventory documented
- migration run procedure documented
- deployment smoke-test procedure documented
- application rollback, database rollback, and prompt/model rollback procedures documented
- backup validation requirements documented
- production security review checklist documented

Exit criteria:

- production deploys are repeatable, observable, and reversible.

## Phase 9: AI-Assisted Review Optimization

Goal: raise touchless throughput and extraction quality while keeping humans in control of uncertain cases.

Status: implemented and covered by unit tests, the Docker test suite, and a live end-to-end smoke (upload → worker → review → accuracy report). Auto-approval and anomaly thresholds still need tuning against representative production data.

Deliverables:

- per-field extraction confidences in the strict schema (prompt version `2026-07-17.v2`)
- `field_confidence_low` validation rule routing weak fields to review
- confidence-gated auto-approval with `invoice.auto_approved` audit action and metric
- post-extraction anomaly detection (supplier amount z-score outliers, embedding near-duplicates) that demotes passing invoices back to review
- plain-language explanations and suggested fixes persisted on failed validation rules
- AI line-item expense categorization (closed category set)
- retrieval-augmented extraction from approved same-supplier invoices
- extraction accuracy analytics from reviewer corrections (`GET /api/v1/extraction/accuracy`) plus per-field correction metrics
- natural-language invoice search (`POST /api/v1/invoices/nl-search`) with a deterministic no-key fallback parser
- optional extraction model tiering with escalation on low confidence and aggregated cost
- embedding reuse for identical source text and pre-extraction image downscaling
- cockpit UI: low-confidence field highlighting, validation explanations, anomaly badges, category badges, auto-approved badge, and an "Ask AI" search bar
- Grafana panels and Prometheus counters for auto-approvals, anomalies, corrections, and escalations

Exit criteria:

- clean high-confidence invoices approve without human touch, and every machine approval is auditable.
- anomalous or low-confidence invoices always reach a human with actionable guidance.
- extraction quality per prompt version is measurable from reviewer corrections.

Remaining hardening before Phase 9 is production-complete:

- tune `AUTO_APPROVAL_MIN_CONFIDENCE`, anomaly z-score, and near-duplicate thresholds against representative production invoices
- run live-provider verification of per-field confidences and categories with real invoice fixtures
- consider reviewer feedback capture on explanation quality if LLM-written explanations are enabled

## Phase 10: Agent Layer (MCP + Tool Calling)

Goal: expose the platform's capabilities to AI agents — external (MCP clients) and in-product (AP assistant) — without weakening tenant isolation or RBAC.

Status: implemented and covered by unit/integration tests plus live smokes (assistant over HTTP, MCP over real stdio JSON-RPC).

Deliverables:

- shared transport-agnostic tool layer (`app/services/invoice_tools.py`) calling the existing service layer only — tenant scoping and role rules are inherited, never reimplemented
- stdio MCP server (`python -m app.mcp.server`, official `mcp` SDK) with seven tools, acting as a configured service user (`MCP_SERVICE_USER_EMAIL`)
- structured JSON tool errors so client models can self-correct instead of crashing the session
- `POST /api/v1/assistant/ask`: OpenAI Responses tool-calling loop (capped by `ASSISTANT_MAX_TOOL_CALLS`) running as the authenticated caller, returning the answer plus the ordered tool trace
- deterministic keyless fallback answerer so the endpoint works in development and degrades gracefully on provider failure
- the assistant is read-only by design — reprocess/approve stay behind explicit human actions in the cockpit
- cockpit Assistant panel on the review screen: a conversational chat thread (question and answer turns rendered together as user/assistant bubbles, answers keep their line breaks), per-answer tool-trace chips and model name, starter prompts on the empty thread, a clear-conversation control, and a one-click "Why is this invoice stuck?" quick question on the invoice drill-down

Exit criteria:

- an MCP client can search, inspect, and triage invoices with exactly the configured user's permissions.
- the assistant answers operational questions grounded in tool results, with a visible trace.
- no agent surface can mutate invoice state beyond what the acting user's role allows.

Remaining hardening before Phase 10 is production-complete:

- MCP over streamable HTTP with per-client authentication, if remote MCP clients are required
- assistant token/cost accounting per organization if usage grows
- live-provider exercise of the LLM tool-calling path (local verification used the deterministic fallback)
