# Deployment Guide

This guide documents the repeatable deployment contract for the current backend, worker, PostgreSQL, and Redis implementation. It assumes an environment that can run the same application images as Docker Compose, with managed production-grade PostgreSQL, Redis, object storage, secret management, logging, and metrics collection.

## Release Gates

Before promoting a release:

1. Run the CI pipeline successfully.
2. Build an immutable backend image from the exact commit being deployed.
3. Run database migrations against staging or a migration validation database.
4. Smoke-test `/health`, `/metrics`, invoice create/upload, queue processing, review approve/reject, and signed file download URL generation.
5. Confirm operational dashboards show API latency, queue depth, failed jobs, validation failures, processing duration, AI estimated cost, auto-approvals, anomaly flags, and reviewer field corrections.
6. When enabling or tuning auto-approval in production, review the auto-approval rate and the `invoice.auto_approved` audit trail after the first representative batch before raising thresholds.

## CI Pipeline

The repository includes `.github/workflows/ci.yml`.

The workflow:

- builds the Docker Compose stack
- verifies service status
- runs `scripts/check-release.sh`
- checks the Alembic migration head
- runs the backend pytest suite inside the backend container
- smoke-tests `/health`
- smoke-tests `/metrics`
- prints service logs on failure
- removes containers and volumes after every run

## Image Build

Build the backend image from the repository root:

```bash
docker build -f backend/Dockerfile -t invoice-platform-backend:<commit-sha> .
```

Use the same image for API and worker processes. The API command should run `uvicorn app.main:app`; the worker command should run `python -m app.worker`.

## Compose Deployment Assets

The repository includes a production-oriented Compose file:

```bash
docker compose --env-file .env.staging.example -f docker-compose.prod.yml config --quiet
```

`docker-compose.prod.yml` is standalone and avoids local development bind mounts and `--reload`. It can run the API, worker, PostgreSQL, Redis, and local private file storage for staging or a self-hosted proof of deployment.

For managed production infrastructure, keep the API and worker service definitions as the runtime contract and replace the bundled PostgreSQL, Redis, and local file-storage volume with managed services.

## Runtime Services

Required runtime components:

- API process
- worker process
- PostgreSQL database
- Redis instance
- private object storage location
- log collection for JSON application logs
- Prometheus-compatible metrics scraper for `/metrics`

The API and worker must use the same `DATABASE_URL`, `REDIS_URL`, object storage configuration, `JWT_SECRET`, and OpenAI settings.

## Environment Variables

Required:

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | Runtime environment name, for example `staging` or `production`. |
| `APP_DEBUG` | Must be `false` in production. |
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL. |
| `REDIS_URL` | Redis URL used by API and worker. |
| `JWT_SECRET` | HS256 bearer-token and signed-file URL secret. Use a strong secret from a secret manager. |
| `JWT_ACCESS_TOKEN_TTL_SECONDS` | Access-token lifetime in seconds. |
| `OBJECT_STORAGE_BUCKET` | Logical storage bucket name. |
| `OBJECT_STORAGE_BACKEND` | `local` for mounted private filesystem storage or `s3` for S3-compatible object storage. Production defaults to `s3`. |
| `OBJECT_STORAGE_LOCAL_PATH` | Filesystem storage path used only when `OBJECT_STORAGE_BACKEND=local`. |
| `OBJECT_STORAGE_ENDPOINT_URL` | Optional S3-compatible endpoint URL, for example a MinIO or non-AWS provider endpoint. |
| `OBJECT_STORAGE_REGION` | S3-compatible storage region. |
| `OBJECT_STORAGE_ACCESS_KEY_ID` | S3-compatible storage access key. Prefer secret-manager injection. |
| `OBJECT_STORAGE_SECRET_ACCESS_KEY` | S3-compatible storage secret key. Prefer secret-manager injection. |

Application behavior:

| Variable | Purpose |
| --- | --- |
| `PROCESSING_QUEUE_NAME` | Redis queue name. Defaults to `invoice_processing_jobs`. |
| `PROCESSING_RETRY_QUEUE_NAME` | Redis sorted set for delayed processing-job retries. Defaults to `invoice_processing_jobs:delayed`. |
| `WORKER_POLL_TIMEOUT_SECONDS` | Worker Redis polling timeout. |
| `WORKER_SLEEP_SECONDS` | Worker idle sleep interval. |
| `PROCESSING_JOB_MAX_ATTEMPTS` | Maximum worker attempts before a processing job is marked failed. Defaults to 3. |
| `PROCESSING_JOB_RETRY_BACKOFF_SECONDS` | Base delay before retrying failed processing jobs. Defaults to 30 seconds and doubles per failed attempt. |
| `INVOICE_UPLOAD_MAX_BYTES` | Maximum accepted invoice upload size. |
| `UPLOAD_RATE_LIMIT_ENABLED` | Enables in-process upload rate limiting. Defaults to true. |
| `UPLOAD_RATE_LIMIT_REQUESTS` | Upload requests allowed per client/window. Defaults to 20. |
| `UPLOAD_RATE_LIMIT_WINDOW_SECONDS` | Upload rate-limit window in seconds. Defaults to 60. |
| `INVOICE_FILE_DOWNLOAD_URL_TTL_SECONDS` | Signed file download URL lifetime. |

AI extraction:

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Enables production OpenAI extraction when set. Without it, the development extractor is used. |
| `OPENAI_EXTRACTION_MODEL` | Extraction model name. |
| `OPENAI_INPUT_COST_PER_MILLION_TOKENS` | Cost estimate input rate used for persisted extraction cost. |
| `OPENAI_OUTPUT_COST_PER_MILLION_TOKENS` | Cost estimate output rate used for persisted extraction cost. |
| `OPENAI_EMBEDDING_MODEL` | Embedding model for similar-invoice search (must produce 1536-dimension vectors). |
| `OPENAI_EMBEDDING_COST_PER_MILLION_TOKENS` | Cost estimate rate for persisted embedding cost. |
| `GEMINI_API_KEY` | Enables the alternative Gemini extraction provider when set. |
| `GEMINI_EXTRACTION_MODEL` | Gemini extraction model name. |

AI pipeline optimizations:

| Variable | Purpose |
| --- | --- |
| `AUTO_APPROVAL_ENABLED` | Enables confidence-gated auto-approval (touchless processing). Defaults to true. |
| `AUTO_APPROVAL_MIN_CONFIDENCE` | Minimum overall and per-field confidence for auto-approval. Defaults to 0.92. |
| `FIELD_CONFIDENCE_REVIEW_THRESHOLD` | Per-field confidence below this fails `field_confidence_low` and routes to review. Defaults to 0.75. |
| `EXTRACTION_FEW_SHOT_ENABLED` | Injects recent approved same-supplier invoices as few-shot prompt examples. Defaults to true. |
| `EXTRACTION_FEW_SHOT_EXAMPLES` | Number of few-shot examples per extraction. Defaults to 2. |
| `ANOMALY_DETECTION_ENABLED` | Enables post-extraction anomaly detection. Defaults to true. |
| `ANOMALY_AMOUNT_ZSCORE_THRESHOLD` | Z-score above which a supplier amount outlier is flagged. Defaults to 3.0. |
| `ANOMALY_MIN_HISTORY` | Minimum approved same-supplier invoices before the amount outlier rule applies. Defaults to 3. |
| `NEAR_DUPLICATE_SIMILARITY_THRESHOLD` | Embedding cosine similarity at/above which a near-duplicate is flagged. Defaults to 0.97. |
| `VALIDATION_EXPLANATIONS_LLM_ENABLED` | Uses the LLM to write validation explanations instead of deterministic templates. Defaults to false. |
| `EXTRACTION_TIERING_ENABLED` | Runs the cheaper tier-1 model first and escalates on low confidence. Defaults to false. |
| `OPENAI_EXTRACTION_TIER1_MODEL` | Tier-1 (cheaper) extraction model used when tiering is enabled. |
| `EXTRACTION_ESCALATION_CONFIDENCE` | Tier-1 confidence below this escalates to the primary model. Defaults to 0.85. |
| `EMBEDDING_REUSE_ENABLED` | Reuses stored embeddings for identical source text instead of a provider call. Defaults to true. |
| `EXTRACTION_IMAGE_MAX_DIMENSION` | Max image dimension (px) sent to the extractor; larger uploads are downscaled. 0 disables. Defaults to 2048. |

Agent layer:

| Variable | Purpose |
| --- | --- |
| `ASSISTANT_ENABLED` | Enables the read-only AP assistant endpoint. Defaults to true. |
| `ASSISTANT_MAX_TOOL_CALLS` | Tool-call budget per assistant question. Defaults to 6. |
| `OPENAI_ASSISTANT_MODEL` | Assistant reasoning model; empty uses `OPENAI_EXTRACTION_MODEL`. |
| `MCP_SERVICE_USER_EMAIL` | Platform user the stdio MCP server acts as; unset disables MCP tool calls. |

Local-only ports:

| Variable | Purpose |
| --- | --- |
| `BACKEND_PORT` | Host port for local Docker Compose API access. |
| `POSTGRES_PORT` | Host port for local PostgreSQL access. |
| `REDIS_PORT` | Host port for local Redis access. |

Templates:

- `.env.staging.example`
- `.env.production.example`

Copy a template into the deployment environment secret/config store and replace every `replace-with-*` value before use.

## Migration Procedure

1. Back up the target database before running migrations.
2. Deploy the new image to a one-off migration job or admin shell.
3. Run:

```bash
alembic upgrade head
```

4. Confirm the deployed revision:

```bash
alembic current
```

5. Start or roll API and worker processes only after migration success.

For Compose-based deployments, use:

```bash
ENV_FILE=.env.production scripts/run-migrations.sh
```

Migrations should be backward-compatible whenever possible. Destructive schema changes require a separate reviewed release with a restore plan.

## First Admin Bootstrap

After migrations and before opening the deployment to users, create the first organization admin:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm backend \
  python /app/scripts/bootstrap-admin.py \
  --organization "Example Enterprise" \
  --email admin@example.com \
  --password "replace-with-a-long-random-password"
```

The script creates the organization if it does not exist, refuses duplicate user emails, stores only a password hash, and assigns the `admin` role.

## Deployment Procedure

1. Confirm CI passed for the target commit.
2. Build and push the immutable image tagged with the commit SHA.
3. Apply production environment variables through the deployment platform secret/config mechanism.
4. Run database backup.
5. Run migrations.
6. Deploy API process.
7. Deploy worker process.
8. Smoke-test:

```bash
curl -fsS https://<api-host>/health
curl -fsS https://<api-host>/metrics
```

Or run:

```bash
API_BASE_URL=https://<api-host> scripts/smoke-test.sh
```

9. Watch logs and metrics for at least one worker cycle and one invoice workflow.

## Rollback Procedure

Application rollback:

1. Stop or drain workers to avoid processing with mixed versions.
2. Roll API and worker to the previous known-good image.
3. Keep the database at the current migrated version unless an approved database restore is required.
4. Run `/health` and `/metrics` smoke tests.
5. Verify queue depth and failed-job metrics are stable.

Database rollback:

- Prefer forward-fix migrations.
- Restore from backup only when data corruption or an incompatible destructive migration requires it.
- Before restore, capture the current failed jobs, queue depth, and affected invoice IDs for reconciliation.

Prompt/model rollback:

- Revert `OPENAI_EXTRACTION_MODEL` or activate the prior prompt version through code/config without deleting historical extraction rows.

## Backup Validation

Production must have:

- automated database backups
- documented retention period
- periodic restore drill in staging
- object storage backup or versioning policy
- restore evidence with timestamp, backup ID, restored database revision, and smoke-test result

## Security Review Checklist

Before production launch:

- verify `APP_DEBUG=false`
- verify `JWT_SECRET` is not a local default
- verify secrets are stored outside git
- verify production logs do not include bearer tokens, file signatures, or invoice document contents
- verify current business endpoints require auth and tenant isolation
- verify signed file URL TTL is short
- verify production CORS, TLS, rate limiting, and WAF/API gateway controls are configured at the edge
- verify operational `/health` and `/metrics` exposure matches the deployment network policy
