# API Contract

This document records the intended API contract and current implementation status.

## Status Labels

- Implemented: endpoint exists and behavior is wired in code.
- Partial: endpoint exists but is not production behavior yet.
- Planned: endpoint does not exist yet.

## Current Endpoints

### Authentication

All current business API endpoints require:

```text
Authorization: Bearer <HS256 JWT>
```

The token must be signed with `JWT_SECRET`, use `alg` `HS256`, include `typ` `JWT`, include a UUID `sub` claim matching a row in `users`, and include a future `exp` timestamp.

Operational endpoints `/health` and `/metrics` do not require bearer authentication.

### `POST /api/v1/auth/login`

Status: Implemented.

Purpose: exchange database-backed user credentials for an access token.

Current behavior:

- accepts `email` and `password`
- normalizes email to lowercase for lookup
- verifies the supplied password against the stored PBKDF2-HMAC-SHA256 password hash
- returns an HS256 bearer access token with `sub`, `org`, `role`, `email`, `iat`, and `exp` claims
- returns user ID, organization ID, email, role, token type, and expiry duration
- rejects unknown users, bad passwords, and users without password hashes with `invalid_credentials`

Response fields:

| Field | Type | Notes |
| --- | --- | --- |
| `access_token` | string | HS256 JWT for API authorization |
| `token_type` | string | Always `bearer` |
| `expires_in` | integer | Token lifetime in seconds |
| `user_id` | UUID | Authenticated user |
| `organization_id` | UUID | User organization |
| `email` | string | User email |
| `role` | string | User role |

### `GET /api/v1/users`

Status: Implemented.

Purpose: list users in the authenticated admin's organization.

Current behavior:

- requires a valid bearer token for a database-backed `admin` user
- returns only users in the authenticated admin's organization
- returns user ID, organization ID, email, and role

### `POST /api/v1/users`

Status: Implemented.

Purpose: create a user in the authenticated admin's organization.

Current behavior:

- requires a valid bearer token for a database-backed `admin` user
- accepts `email`, `role`, and `password`
- normalizes email and role
- allows `admin`, `reviewer`, and `uploader` roles
- stores only a PBKDF2-HMAC-SHA256 password hash
- rejects duplicate emails
- writes a `user.created` audit event

### `PATCH /api/v1/users/{user_id}`

Status: Implemented.

Purpose: update a user email or role in the authenticated admin's organization.

Current behavior:

- requires a valid bearer token for a database-backed `admin` user
- scopes user lookup to the authenticated admin's organization
- rejects users outside the organization with `user_not_found`
- rejects duplicate emails
- prevents demoting the last admin in an organization
- writes a `user.updated` audit event when fields change

### `POST /api/v1/users/{user_id}/password`

Status: Implemented.

Purpose: allow an admin to set a user's password.

Current behavior:

- requires a valid bearer token for a database-backed `admin` user
- scopes user lookup to the authenticated admin's organization
- stores only a new password hash
- writes a `user.password_set` audit event

### `POST /api/v1/users/me/password`

Status: Implemented.

Purpose: allow an authenticated user to change their own password.

Current behavior:

- requires a valid bearer token for a database-backed user
- verifies the current password
- stores only a new password hash
- writes a `user.password_changed` audit event

### Request IDs

All HTTP responses include `X-Request-ID`. If the client sends `X-Request-ID`, that value is preserved. If the header is absent or blank, the API generates a UUID request ID. API error envelopes include the active request ID, and request completion logs include the same ID.

### `GET /metrics`

Status: Implemented.

Purpose: expose operational metrics in Prometheus text format.

Current behavior:

- does not require bearer authentication so local monitoring can scrape it
- includes `invoice_platform_http_requests_total`
- includes `invoice_platform_http_request_duration_seconds_sum`
- includes `invoice_platform_processing_queue_depth` when Redis is reachable
- includes `invoice_platform_processing_jobs_failed_total`
- includes `invoice_platform_processing_job_duration_seconds_sum`
- includes `invoice_platform_processing_job_duration_seconds_count`
- includes `invoice_platform_validation_failures_total`
- includes `invoice_platform_ai_estimated_cost_total`

### `GET /api/v1/audit-logs`

Status: Implemented.

Purpose: inspect tenant-scoped audit history.

Current behavior:

- requires a valid bearer token for a database-backed user
- returns only audit rows for the authenticated user's organization
- supports optional `entity_type`, `entity_id`, and `action` filters
- supports `limit` from 1 to 200, defaulting to 50
- returns actor, entity, action, metadata, request ID, and creation timestamp
- audit rows are append-only at the SQLAlchemy application layer

### `GET /health`

Status: Implemented.

Purpose: service health check.

### `POST /api/v1/invoices`

Status: Partial.

Purpose: create invoice metadata.

Current behavior:

- requires a valid bearer token for a database-backed `admin` or `uploader` user
- validates request shape through Pydantic
- derives `organization_id` and `uploaded_by` from the authenticated user
- ignores compatibility-only client-supplied `organization_id` and `uploaded_by` fields
- rejects `supplier_id` values outside the authenticated user's organization
- persists invoice metadata through SQLAlchemy
- writes an `invoice.uploaded` audit event in the same service path
- returns status `uploaded` and the generated invoice ID
- does not store a file
- does not enqueue processing

Request fields:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `organization_id` | UUID or null | no | compatibility-only; server uses authenticated user's organization |
| `supplier_id` | UUID or null | no | may be unknown during extraction |
| `uploaded_by` | UUID or null | no | compatibility-only; server uses authenticated user |
| `invoice_number` | string | yes | 1-100 characters |
| `total_amount` | decimal or null | no | must be non-negative if present |
| `currency` | string | no | 3-character currency code, defaults to `USD` |

Target production behavior:

- optionally enqueue processing job after file upload exists

### `POST /api/v1/invoices/{invoice_id}/status`

Status: Partial.

Purpose: validate invoice status transition.

Current behavior:

- requires a valid bearer token for a database-backed `admin` user
- accepts `requested_status`; `actor_id` is compatibility-only and ignored
- loads the invoice from the database by ID and authenticated organization
- applies workflow transition rules from persisted invoice status
- persists status changes
- writes an `invoice.status_changed` audit event with the authenticated user as actor
- returns conflict on invalid transition

Target production behavior:

- add more granular status-transition permissions if enterprise policy requires them

### `POST /api/v1/invoices/upload`

Status: Partial.

Purpose: upload an invoice file and create intake records.

Current behavior:

- requires a valid bearer token for a database-backed `admin` or `uploader` user
- accept multipart file upload
- derives `organization_id` and `uploaded_by` from the authenticated user
- ignores compatibility-only client-supplied `organization_id` and `uploaded_by` form fields
- rejects `supplier_id` values outside the authenticated user's organization
- validate file size, MIME type, and extension
- calculate checksum
- store original file through the configured private storage adapter
- create invoice and invoice file rows
- audit upload with file metadata
- reject duplicate file checksums per organization
- create a durable queued extraction job row
- publish job ID to Redis for the worker
- enforces a configurable upload rate limit and returns `rate_limit_exceeded` with HTTP 429 when exceeded
- runtime database, storage, Redis, and worker behavior has been smoke-tested through Docker

Target production behavior:

- use private S3-compatible object storage in production
- create invoice and invoice file rows transactionally with storage cleanup on failure
- enqueue extraction job
- audit upload and job creation

### `GET /api/v1/invoices/{invoice_id}/files/{file_id}/download-url`

Status: Implemented.

Purpose: create a short-lived signed URL for an uploaded invoice file.

Current behavior:

- requires a valid bearer token for a database-backed user
- scopes file lookup to the authenticated user's organization
- returns `invoice_file_not_found` for files outside the user's organization
- returns a URL signed with HMAC and an expiry timestamp
- default expiry is controlled by `INVOICE_FILE_DOWNLOAD_URL_TTL_SECONDS`

Response fields:

| Field | Type | Notes |
| --- | --- | --- |
| `file_id` | UUID | invoice file identifier |
| `download_url` | string | signed URL that can be used without a bearer token until expiry |
| `expires_at` | datetime | absolute expiry timestamp |

### `GET /api/v1/invoices/{invoice_id}/files/{file_id}/download`

Status: Implemented.

Purpose: download an uploaded invoice file using a signed URL.

Current behavior:

- accepts `expires_at` and `signature` query parameters
- validates expiry and HMAC signature before reading storage
- streams the stored file with the persisted MIME type
- returns `invoice_file_download_invalid` for expired or tampered signatures
- returns `invoice_file_not_found` when the file row does not exist
- returns `invoice_file_storage_missing` when the database row exists but the object is missing from storage

### `GET /api/v1/invoices/{invoice_id}/similar`

Status: Implemented and covered by API integration tests, including tenant isolation and ranking assertions.

Purpose: surface the most semantically similar invoices in the caller's organization for reviewer context and near-duplicate triage.

Current behavior:

- requires a valid bearer token for a database-backed user
- resolves the invoice through the same organization-scoped lookup as the detail endpoint (`invoice_not_found` outside the tenant)
- ranks candidates by pgvector cosine distance over the `invoice_embeddings` HNSW index, excluding the invoice itself
- accepts `limit` (1–20, default from `INVOICE_SIMILARITY_RESULT_LIMIT`, 5)
- returns an empty list when the invoice has no embedding yet (extraction not completed)
- responds with each candidate's id, invoice number, supplier, status, amount, currency, and a `similarity` score (1.0 = identical direction)

Target behavior:

- flag high-similarity pairs (e.g. >0.95) as potential duplicates directly in the review UI

### `GET /api/v1/invoices/{invoice_id}`

Status: Implemented for backend data retrieval with authenticated tenant enforcement.

Purpose: retrieve invoice detail for review.

Current behavior:

- requires a valid bearer token for a database-backed user
- filters by the authenticated user's organization
- returns `invoice_not_found` for invoices outside the user's organization
- returns invoice metadata, files, extracted fields, validation results, and review state

Target behavior:

- return invoice metadata, files, extracted fields, validation results, review state, and audit summary
- add fine-grained read permissions beyond tenant membership

### `GET /api/v1/invoices`

Status: Implemented and covered by API integration tests with `status`, `review_queue`, `limit`, authenticated user lookup, and tenant filtering. Full pagination is still pending.

Purpose: list invoices for dashboard/review queues.

Current behavior:

- requires a valid bearer token for a database-backed user
- returns only invoices belonging to the authenticated user's organization
- supports `status`, `review_queue`, and `limit` query parameters

Target behavior:

- support filtering by status, supplier, date range, and review queue
- paginate results
- add fine-grained read permissions beyond tenant membership

### `POST /api/v1/invoices/{invoice_id}/review`

Status: Implemented and covered by API integration tests for corrections, approve, reject, stale update conflict, unsupported corrected fields, duplicate invoice-number correction, authenticated reviewer attribution, reviewer role denial, and cross-tenant denial.

Purpose: save reviewer corrections and approve or reject.

Current behavior:

- requires a valid bearer token for a database-backed user
- requires the authenticated user to have `reviewer` or `admin` role
- scopes invoice lookup to the authenticated user's organization
- ignores any supplied `reviewer_id` request field and records the authenticated user as reviewer
- saves corrected fields
- creates a review record
- transitions invoice to `approved` or `rejected`
- appends correction, decision, and status-change audit events

Target behavior:

- add fine-grained approval limits and assignment rules if required by enterprise policy

### `GET /api/v1/processing-jobs/{processing_job_id}`

Status: Implemented.

Purpose: retrieve processing job state.

Current behavior:

- requires a valid bearer token for a database-backed user
- filters by the authenticated user's organization through the related invoice
- returns invoice ID, job type, status, attempts, and last error
- `attempts` is incremented when the worker records a failed attempt

### `GET /api/v1/processing-jobs/failed`

Status: Implemented.

Purpose: inspect failed processing jobs.

Current behavior:

- requires a valid bearer token for a database-backed user
- returns only failed jobs belonging to the authenticated user's organization
- returns recent failed jobs
- supports a `limit` query parameter from 1 to 200

### `POST /api/v1/processing-jobs/{processing_job_id}/reprocess`

Status: Implemented.

Purpose: manually retry a failed processing job.

Current behavior:

- requires a valid bearer token for a database-backed `admin` or `reviewer` user
- accepts optional `actor_id` as compatibility-only and ignores it
- only requeues failed jobs
- scopes the processing job through the authenticated user's organization
- clears `last_error`
- transitions the invoice back to `queued`
- writes audit events with the authenticated user as actor
- publishes the job ID to Redis
- worker consumes the job and moves it through `processing` to `review_required`

### Worker Automatic Retry Policy

Status: Implemented.

Current behavior:

- worker failures are recorded after rolling back in-progress processing state
- each recorded failure increments `processing_jobs.attempts`
- jobs are scheduled for delayed retry while attempts are below `PROCESSING_JOB_MAX_ATTEMPTS`
- retry scheduling writes `processing_job.retry_scheduled` audit events
- when attempts reach `PROCESSING_JOB_MAX_ATTEMPTS`, the job and invoice are marked `failed`
- default maximum attempts is 3
- default retry backoff is 30 seconds, doubling on each failed attempt before the cap
- worker persists extraction payload, prompt version, line items, and validation results

### `GET /api/v1/events/stream`

Status: Implemented.

Purpose: real-time, tenant-scoped event stream so clients can invalidate cached state instead of polling.

Current behavior:

- requires a valid bearer token (or httpOnly cookie) for a database-backed user
- responds `text/event-stream` (Server-Sent Events) and stays open until the client disconnects
- subscribes to a Redis pub/sub channel scoped to the authenticated user's organization (`org:{organization_id}:events`)
- forwards each published event as an SSE message; sends periodic keepalive pings so intermediary proxies do not time out the connection
- events are minimal signals, not full payloads: `{"type": "job.completed" | "job.failed" | "job.requeued" | "invoice.status_changed", "invoice_id", "processing_job_id"?, "status"?, "occurred_at"}`. Clients use the event only to decide what to refetch from the authoritative REST endpoints; the event itself is never the source of truth.
- events are published from `app/services/events.py::publish_event()` immediately after the relevant `db.commit()` in the worker's extraction job lifecycle (`app/services/processing_jobs.py`) and in invoice review submission (`app/services/invoice_review.py`), so both worker-driven and API-driven state changes emit consistently
- publishing never raises: a Redis outage degrades to "no live updates," not a failed business request

## Error Format

Target production error response:

```json
{
  "error": {
    "code": "invoice_status_transition_invalid",
    "message": "Invoice status cannot transition from approved to processing.",
    "details": {
      "invoice_id": "..."
    },
    "request_id": "..."
  }
}
```

API responses use this envelope for domain errors, framework HTTP errors, validation errors, and unexpected exceptions. The `request_id` value is the active `X-Request-ID`.
