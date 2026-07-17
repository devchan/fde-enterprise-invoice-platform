# Operational Runbook

This runbook describes how the production platform should be operated. Some procedures are target-state until the related implementation phases are complete.

## Local Development

Start the dockerized stack:

```bash
docker compose up -d --build
```

Run tests:

```bash
docker compose exec -T backend python -m pytest -q
```

Run the reviewer cockpit browser smoke from the host:

```bash
APP_URL=http://localhost:3000/ scripts/check-cockpit-smoke.sh
```

Health check:

```bash
docker compose exec -T backend curl -fsS http://localhost:8000/health
```

From the host, the default API URL is `http://localhost:8010`.

Metrics:

```bash
docker compose exec -T backend curl -fsS http://localhost:8000/metrics
```

An importable Grafana dashboard is available at `infra/monitoring/grafana/dashboards/invoice-platform-overview.json`.

Local uploaded files are written under `OBJECT_STORAGE_LOCAL_PATH`, which defaults to `.local-storage`. Production should set `OBJECT_STORAGE_BACKEND=s3` and configure bucket, region, endpoint, and credentials for the private S3-compatible provider.

## Health Checks

Current:

- `GET /health`

Target:

- API readiness check should verify database connectivity.
- Worker readiness check should verify Redis connectivity.
- Storage readiness check should verify bucket access without exposing file contents.

## Common Incidents

### API is unavailable

Check:

- container or process status
- recent deploy
- environment variables
- database connectivity
- application logs by request ID

Target remediation:

- roll back last deploy if the failure began immediately after release
- scale API replicas if saturation is confirmed
- fail over database only under an approved database incident procedure

### Invoices stuck in `queued`

Check:

- Redis availability
- worker process status
- queue depth
- `invoice_platform_processing_queue_depth`
- `invoice_platform_processing_jobs_failed_total`
- processing job table for failed locks
- recent worker exceptions

Target remediation:

- restart worker if it is unhealthy
- confirm automatic retries are not exhausted before manual intervention
- requeue jobs manually only after confirming they are idempotent
- mark jobs failed with audit trail if manual intervention is required

### Invoices stuck in `processing`

Check:

- worker logs by invoice ID and job ID
- `invoice_platform_processing_job_duration_seconds_sum`
- `invoice_platform_processing_job_duration_seconds_count`
- AI API latency/errors
- object storage access
- job lock age

Target remediation:

- let automatic retry handle bounded transient failures
- move invoice to `failed` with error metadata if processing cannot complete
- use manual reprocess endpoint after the root cause is fixed

### AI extraction cost spike

Check:

- extraction volume
- model name
- prompt version
- average input/output tokens
- `invoice_platform_ai_estimated_cost_total`
- `invoice_platform_extraction_escalations_total` (tiering escalations double the calls for affected invoices)
- retry count

Target remediation:

- disable automatic extraction if spend is uncontrolled
- roll back prompt version if token usage changed unexpectedly
- cap retry policy for repeated provider failures
- enable `EXTRACTION_TIERING_ENABLED` (cheap model first) or lower `EXTRACTION_IMAGE_MAX_DIMENSION` to cut per-invoice cost
- reduce `EXTRACTION_FEW_SHOT_EXAMPLES` if few-shot examples inflated prompt tokens
- confirm `EMBEDDING_REUSE_ENABLED` is on so duplicate content is not re-embedded

### Auto-approval approving invoices it should not

Check:

- audit log for `invoice.auto_approved` actions on the affected invoices (confidence values are in the event metadata)
- `invoice_platform_invoices_auto_approved_total` rate against the expected volume
- whether anomaly detection was enabled (`ANOMALY_DETECTION_ENABLED`) and its validation rows on the invoices
- current `AUTO_APPROVAL_MIN_CONFIDENCE` and `FIELD_CONFIDENCE_REVIEW_THRESHOLD`

Remediation:

- set `AUTO_APPROVAL_ENABLED=false` and restart the worker to route everything to human review immediately (extraction is unaffected)
- raise `AUTO_APPROVAL_MIN_CONFIDENCE` before re-enabling
- auto-approved invoices are terminal (`approved`); handle incorrect ones through the normal financial reversal process and keep the audit trail intact

### Anomaly detection flagging too many invoices

Check:

- `invoice_platform_anomalies_flagged_total` by `rule_code`
- whether flagged suppliers have enough approved history (`ANOMALY_MIN_HISTORY`)
- validation rows with `amount_anomaly` / `near_duplicate_similarity` on sampled invoices

Remediation:

- raise `ANOMALY_AMOUNT_ZSCORE_THRESHOLD` or `NEAR_DUPLICATE_SIMILARITY_THRESHOLD`
- raise `ANOMALY_MIN_HISTORY` so young suppliers are not scored on thin history
- set `ANOMALY_DETECTION_ENABLED=false` only as a last resort; it also disables the near-duplicate guard in front of auto-approval

### Cross-tenant access report

Check:

- affected user ID
- organization ID
- endpoint and request ID
- database query path
- audit log entries

Target remediation:

- revoke affected sessions
- patch tenant-scope enforcement
- run access-log audit for affected time window
- notify stakeholders according to security incident policy

## Backup and Restore

Target requirements:

- daily database backups
- point-in-time recovery if supported by hosting provider
- regular restore drill in staging
- object storage lifecycle and versioning policy
- documented retention period

## Deployment

Target safe deployment procedure:

1. Run unit and integration tests.
2. Build immutable image.
3. Deploy to staging.
4. Run migration dry-run or compatibility check.
5. Smoke-test health, invoice create, upload, queue, and review paths.
6. Deploy to production.
7. Run post-deploy smoke tests.
8. Watch error rate, latency, queue depth, and failed jobs.

## Rollback

Target rollback rules:

- application rollback must be possible without data loss
- migrations must be backward-compatible where possible
- destructive migrations require a separate approved release
- prompt version rollback should activate an earlier prompt without deleting history
