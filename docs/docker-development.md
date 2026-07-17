# Docker Development

The project is dockerized for local development. Use Docker Compose as the primary runtime instead of installing backend dependencies on the host.

## Services

Compose starts:

- `backend`: FastAPI application on host port `8010` by default
- `worker`: background invoice processing worker
- `postgres`: PostgreSQL 16 on host port `55432` by default
- `redis`: Redis 7 on host port `56380` by default

The backend runs Alembic migrations on startup when `RUN_MIGRATIONS_ON_START=true`.

## Start

```bash
docker compose up -d --build
```

Health check:

```bash
docker compose exec -T backend curl -fsS http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Run Tests

```bash
docker compose exec -T backend python -m pytest -q
```

## Run Migrations Manually

```bash
docker compose exec -T backend alembic upgrade head
```

## OpenAI Extraction

By default, Docker runs without `OPENAI_API_KEY` and the worker uses the deterministic development extractor. To exercise the production OpenAI extractor, export the provider settings before starting Compose:

```bash
OPENAI_API_KEY=sk-... \
OPENAI_EXTRACTION_MODEL=gpt-4.1 \
OPENAI_INPUT_COST_PER_MILLION_TOKENS=0 \
OPENAI_OUTPUT_COST_PER_MILLION_TOKENS=0 \
docker compose up -d --build
```

Set the cost values to the current pricing for the selected model when you want estimated extraction cost persisted with each invoice extraction.

`GEMINI_API_KEY` enables the alternative Gemini provider the same way; the upload form lets users pick between configured providers.

## AI Pipeline Toggles

The worker's AI optimizations (auto-approval, per-field confidence routing, few-shot extraction, anomaly detection, model tiering, embedding reuse, image downscaling) are all environment-driven with safe defaults — see the "AI pipeline optimizations" block in `.env.example` and the variable inventory in [the deployment guide](deployment-guide.md). All of them pass through `docker compose` from the host environment or `.env`, for example:

```bash
AUTO_APPROVAL_ENABLED=false docker compose up -d worker
```

The deterministic development extractor reports 0.8 overall confidence by design, which is below the default 0.92 auto-approval bar — so local invoices never auto-approve unless the threshold is lowered explicitly.

## Logs

```bash
docker compose logs -f backend
```

Worker logs:

```bash
docker compose logs -f worker
```

## Stop

```bash
docker compose down
```

To remove database and uploaded-file volumes:

```bash
docker compose down -v
```

## Ports

Host defaults:

- API: `8010`
- PostgreSQL: `55432`
- Redis: `56380`

Override ports:

```bash
BACKEND_PORT=8011 POSTGRES_PORT=55433 REDIS_PORT=56381 docker compose up -d
```

## Frontend

The `frontend` service (`docker-compose.yml`, `frontend/Dockerfile`'s `dev` target) has **no bind mount**: `COPY frontend ./` and `npm ci` both run at image build time, so the running container is a snapshot of `frontend/` (source and `node_modules`) as of the last build. Editing frontend source on the host does not affect the running container — **any** frontend change, not only a dependency change, requires a rebuild to be reflected:

```bash
docker compose build frontend
docker compose up -d --force-recreate frontend
```

For iterative frontend development, it is usually faster to run `npm run dev` directly on the host (against the same source) than to rebuild the image on every change; use the container rebuild when you specifically need to verify the Dockerized build.

The image's builder stage uses `node:20.18.1-bookworm-slim`, so it satisfies dependencies (such as `@tanstack/react-router`) that require Node >=20 even when the host development machine runs an older Node version.

## Local File Storage

Uploaded files are stored in the Docker volume `invoice_storage` at `/app/.local-storage` inside the backend container. This is the development storage adapter. The same API can use private S3-compatible object storage by setting `OBJECT_STORAGE_BACKEND=s3` plus the bucket, region, endpoint, and credentials.

## Container User and Volume Ownership

The backend and frontend images are multi-stage and run as a **non-root** user (backend `app`, uid `10001`; frontend `nginx`, uid `101`). Fresh environments work automatically: the image creates `/app/.local-storage` owned by the `app` user, so a newly created `invoice_storage` volume inherits writable ownership.

### One-time migration for pre-existing environments

If you built the stack with an **older root-based backend image**, the existing `invoice_storage` volume is owned by `root` and the non-root process cannot write to it. Local invoice uploads then fail with a permission error (`500`), and the `test_security_api.py` upload/download tests fail. Production is unaffected because it uses the S3 storage backend, not local storage.

Re-initialize the volume once so it is recreated with the correct ownership from the new image. This deletes only ephemeral local development upload scratch data — it does not touch the database:

```bash
docker compose stop backend worker
docker volume rm fde-enterprise-invoice-platform_invoice_storage
docker compose up -d backend worker
```

After recreating the volume, the full backend suite passes inside the non-root container:

```bash
docker compose exec -T backend python -m pytest -q
```

> The volume name is the Compose project prefix (the repository directory name) plus `_invoice_storage`. Confirm the exact name with `docker volume ls | grep invoice_storage`.
