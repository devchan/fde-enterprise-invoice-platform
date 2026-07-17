# Production Readiness Checklist

An item is checked only when it is implemented, tested, and usable in the running product. Target-state design alone does not count as ready.

## Application

- [x] API has typed request and response schemas
- [x] API uses consistent error format
- [ ] Database migrations are repeatable and verified
- [ ] Critical state transitions are backend-enforced from persisted invoice state and covered by integration tests
- [ ] Uploads have file size limits
- [ ] Uploads validate MIME type and extension
- [ ] Duplicate uploads are detected by checksum
- [ ] Duplicate invoice numbers are detected per supplier and organization and covered by integration tests
- [x] Long-running work runs in background jobs with verified worker execution
- [x] Jobs have automatic retry policy
- [x] Failed jobs can be inspected
- [x] Failed invoices can be manually reprocessed

## Frontend

- [x] Review queue UI exists in the React frontend (responsive master-detail: full-width queue, xl rail+detail, drill-in below xl)
- [x] Invoice correction UI exists in the React frontend
- [x] Approve/reject UI exists in the React frontend
- [x] Signed file URL access exists in the React frontend
- [x] Login/session UI exists in the React frontend
- [x] Invoice upload UI exists in the React frontend
- [x] Processing dashboard UI exists in the React frontend
- [x] Audit-log UI exists in the React frontend
- [x] User-management UI exists in the React frontend
- [x] Browser smoke automation covers the reviewer cockpit shell
- [x] Browser automation covers authenticated cockpit workflows end to end
- [x] Operational tables are sortable and reusable across cockpit surfaces
- [x] Frontend has schema-backed form validation pattern
- [x] Frontend has a top-level error boundary
- [x] Frontend has unit tests (Vitest + Testing Library)
- [x] Assistant chat UI (conversation thread) with per-answer tool-trace chips is reachable globally via a floating launcher (and ⌘K) on every screen
- [x] Key UI surfaces carry accessibility roles/labels (nav, alerts, controls)

Frontend scope note: the previous static cockpit has been retired. The React/Vite cockpit now covers the implemented backend workflows. Production readiness still requires line-item correction UX, deterministic approve/reject browser fixtures, richer dashboard analytics, and continued design-system hardening.

## AI Extraction

- [x] Extraction uses a strict JSON schema
- [x] Prompt versions are stored
- [x] Model names are stored
- [ ] Token usage is tracked from production provider responses and verified with live provider tests
- [ ] Cost estimates are tracked from production provider responses and verified with live provider tests
- [x] Invalid AI responses are handled
- [x] Confidence scores are stored
- [x] Per-field confidence scores are stored and low-confidence fields route to review
- [x] Human corrections are recorded
- [x] Extraction accuracy is measurable per prompt version from reviewer corrections
- [x] Auto-approval is confidence-gated, anomaly-gated, and audited with a distinct action
- [x] Anomaly detection flags supplier amount outliers and near-duplicates before auto-approval
- [x] Failed validation rules carry reviewer-facing explanations and suggested fixes
- [x] Line items carry AI-assigned expense categories from a closed set
- [x] Extraction cost levers exist (model tiering, embedding reuse, image downscaling, few-shot cap)
- [ ] Auto-approval and anomaly thresholds are tuned against representative production invoices
- [ ] Per-field confidences and categories are verified with live provider tests

## Security

- [x] Authentication is required for current non-health API endpoints
- [x] RBAC is enforced by backend for current privileged actions
- [x] Tenant isolation is enforced in current invoice and processing-job queries
- [x] Tenant isolation is enforced in current user-admin queries
- [x] Password hashes are stored instead of plaintext passwords
- [x] First admin bootstrap path exists
- [x] Last admin demotion is blocked
- [ ] Secrets are not committed
- [x] Files are private by default
- [x] File access uses signed URLs
- [x] S3-compatible object storage adapter exists and is unit-tested
- [ ] S3-compatible storage is smoke-tested against the selected provider
- [ ] Sensitive data is not logged
- [x] Upload endpoints are rate-limited
- [x] Login endpoint is rate-limited
- [x] Rate limiting is distributed (Redis-backed) and enforced across replicas
- [x] Auth tokens are delivered in httpOnly cookies (not readable by JavaScript)
- [x] Tokens can be revoked (logout revokes via a Redis blocklist)
- [x] Refresh tokens rotate on use and replayed refresh tokens are rejected
- [x] Threat model (STRIDE) is documented with trust boundaries, mitigations, and residual risks
- [ ] Admin actions are audited
- [x] User-admin actions are audited

Security scope note: the checked items apply to the current implemented API surface. Future supplier, audit, and admin endpoints must add equivalent authentication, RBAC, and tenant checks before they are considered ready.

## Audit and Compliance

- [ ] Invoice upload is audited and verified in persistence tests
- [ ] Extraction completion is audited
- [ ] Validation result is audited
- [x] Field corrections are audited
- [x] Approval and rejection are audited and verified in persistence tests
- [x] Audit records include actor, timestamp, entity, action, and metadata
- [x] Audit log is append-only at application level

## Observability

- [x] Structured JSON logs are used
- [x] Request IDs are generated
- [x] Job IDs are logged
- [x] Invoice IDs are logged
- [x] API latency is measured
- [x] API latency percentiles (p95/p99) are available via histogram buckets
- [x] Distributed tracing (OpenTelemetry) is available for API, DB, and Redis (opt-in)
- [x] Queue depth is measured
- [x] Processing duration is measured
- [x] Extraction failure rate is measured
- [x] Validation failure rate is measured
- [x] AI cost is measured
- [x] Dashboards exist for operations
- [x] Service Level Objectives are defined, each mapped to a backing signal
- [ ] SLO attainment is measured against production telemetry

Observability scope note: structured JSON logs, request IDs, API request metrics, Redis queue depth, worker job/invoice log enrichment, failed extraction job totals, validation failure totals, completed processing duration totals, AI estimated cost totals, and an importable Grafana dashboard are implemented. Request-latency histogram buckets (p95/p99) and opt-in OpenTelemetry tracing for FastAPI, SQLAlchemy, and Redis are implemented; a hosted tracing/metrics backend deployment remains an operator step.

## Architecture and Documentation

- [x] System architecture is documented (client, edge, application, data, and observability planes)
- [x] Data model is documented as an ER view (entities, keys, relationships, constraints)
- [x] Invoice request lifecycle is documented
- [x] Request sequence (client, API, queue, worker, provider, database) is documented
- [x] Deployment topology is documented (ingress, services, workloads, config/secret plane, external datastores)
- [x] SLOs and the observability signal inventory are documented
- [x] Threat model (STRIDE) with trust boundaries and residual risks is documented
- [x] End-to-end architecture view is published and browsable (GitHub Pages)
- [x] Documentation separates current-state from target-state (documentation contract)

Architecture scope note: the end-to-end architect view (system, data model, request lifecycle, request sequence, deployment topology, SLOs and observability, threat model, readiness scorecard, and roadmap) is maintained as `docs/architecture-view.html` and published via GitHub Pages. It is a living snapshot regenerated from the source view; keep it in step with the code as the platform evolves.

## Deployment

- [x] Docker Compose works locally
- [x] CI runs tests
- [x] CI runs lint (ruff), type-check (tsc), and frontend unit tests (Vitest)
- [x] Backend dependencies are free of known CVEs (pip-audit) and gated in CI
- [x] Frontend dependency scan runs in CI (advisory; findings are build-time tooling)
- [x] Backend and frontend images are multi-stage and run as a non-root user
- [x] Liveness and readiness probes exist; readiness verifies database and Redis
- [x] Production Compose sets restart policies and resource limits
- [ ] Staging environment exists
- [x] Production environment variables are documented
- [x] Database backup process is documented
- [x] Rollback process is documented
- [x] Deployment guide exists
- [x] Runbook exists for common incidents
- [x] Production-oriented Compose deployment assets exist
- [x] Staging Compose overlay exists (docker-compose.staging.yml)
- [x] Kubernetes manifests exist (kustomize base + staging/production overlays)
- [x] Terraform skeleton exists for infrastructure provisioning
- [x] Release, migration, and smoke-test scripts exist

Deployment scope note: the checked items are repository-level deployment readiness assets. Container images are multi-stage and non-root, the production Compose file gates on a database/Redis readiness probe with restart policies and resource limits, and CI runs lint, type-check, and advisory dependency scanning alongside the Docker test suite. Kubernetes manifests (kustomize base + overlays), a Terraform skeleton, a staging Compose overlay, and distributed Redis-backed rate limiting are now present. The FastAPI/Starlette stack has been upgraded so backend dependencies are CVE-clean and pip-audit is a blocking CI gate. A live hosted staging/production cluster remains the main pending deployment step.
