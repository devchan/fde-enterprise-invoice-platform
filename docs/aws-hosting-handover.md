# AWS Hosting Handover

**For:** the DevOps engineer who will host this platform on AWS.
**After reading you should be able to:** choose a hosting option, provision the AWS
resources it needs, deploy a release, and know what is not built yet.

This document is AWS-specific. The platform-neutral contract (every environment
variable, migration, first-admin bootstrap, rollback, and the security checklist)
is in [`deployment-guide.md`](deployment-guide.md). Incident handling is in
[`operational-runbook.md`](operational-runbook.md). Read those alongside this one.

---

## 1. Pick an option

| | Option A: EKS (recommended for production) | Option B: single EC2 box (demo / low volume) |
|---|---|---|
| What's in the repo | `infra/k8s/` (Kustomize base + staging/production overlays) | `infra/aws-micro/` (compose, cloud-init, Caddy, frontend script) |
| Postgres | RDS for PostgreSQL 16 + `vector` extension | Container on the box |
| Redis (job queue) | ElastiCache for Redis | Container on the box |
| Invoice files | S3 | Local EBS disk (S3 optional) |
| Frontend | Container behind the same ingress | S3 + CloudFront |
| High availability | Yes (multi-replica, HPA on backend) | No |
| Rough cost | Cluster + RDS + ElastiCache; size to load | ~$5/mo (t3.micro) – ~$12–18/mo (2 GB box) |
| Validated so far | On a local `kind` cluster only (`scripts/kind-deploy.sh`) | Compose stack run locally; not yet run on EC2 |

If your team does not already run EKS, **ECS Fargate** with the same RDS,
ElastiCache and S3 is a reasonable alternative, but there are no ECS task
definitions in the repo — you would write them from the Kubernetes manifests
(same image, same env, same commands; see section 3).

---

## 2. What runs

One backend image, used three ways, plus a frontend image:

| Process | Image | Command | Port / probes |
|---|---|---|---|
| API | `backend/Dockerfile` | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir /app/backend` | 8000; liveness `GET /health`, readiness `GET /health/ready` (checks DB + Redis) |
| Worker | same backend image | `python -m app.worker` | none; consumes the Redis queue |
| Migrations | same backend image | `alembic upgrade head` | one-off per release |
| Frontend (EKS) | `frontend/Dockerfile` | nginx-unprivileged | 8080 in the pod; readiness `GET /healthz` |

Build both images **from the repository root** (the Dockerfiles copy `backend/`,
`infra/`, `scripts/`, `alembic.ini`):

```bash
docker build -f backend/Dockerfile  -t <ecr>/invoice-platform-backend:<git-sha> .
docker build -f frontend/Dockerfile --build-arg VITE_API_BASE_URL=https://<app-host> \
  -t <ecr>/invoice-platform-frontend:<git-sha> .
```

`VITE_API_BASE_URL` is **baked into the frontend at build time**. You need a
separate frontend build per environment (staging, production).

API routes live under `/api/v1/...`; `/health`, `/health/ready` and `/metrics` are
unversioned at the root.

---

## 3. Option A: EKS

### 3.1 AWS resources to provision

`infra/terraform/` is a cloud-neutral skeleton (it creates a namespace only).
None of the AWS resources below exist in code yet — you will need to write them.

| Resource | Settings that matter |
|---|---|
| VPC | Private subnets for EKS nodes, RDS and ElastiCache |
| EKS cluster | An ingress controller. The manifests assume **ingress-nginx** (`ingressClassName: nginx`). If you use the AWS Load Balancer Controller instead, change the class and annotations in `infra/k8s/base/ingress.yaml`. |
| ECR | Two repositories: `invoice-platform-backend`, `invoice-platform-frontend` |
| RDS PostgreSQL 16 | Run `CREATE EXTENSION vector;` once (pgvector is required by migration `20260717_0005`). Automated backups on. |
| ElastiCache for Redis | **Parameter group with `maxmemory-policy noeviction`.** Redis is the invoice processing queue; an evicting policy silently drops queued jobs. |
| S3 bucket | Private; versioning recommended (see backup notes in `deployment-guide.md`). Default bucket name in config is `invoice-platform-production`. |
| IAM role for pods (IRSA or EKS Pod Identity) | `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on the bucket. Attach to the backend, worker and migration service account. |
| Secrets Manager | Holds the values in 3.2, synced into the cluster (e.g. External Secrets Operator). |
| ACM certificate + DNS | For the public app hostname. |

S3 credentials: leave `OBJECT_STORAGE_ACCESS_KEY_ID` and
`OBJECT_STORAGE_SECRET_ACCESS_KEY` **empty**. The S3 client
(`backend/app/services/file_storage.py`) then uses the standard AWS credential
chain, so the pod's IAM role is picked up — no static keys needed.

### 3.2 Secrets

The pods read a Kubernetes Secret named `invoice-platform-secrets`
(`envFrom` in the deployments). Keys, as listed in
`infra/k8s/base/secret.example.yaml`:

| Key | Value |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://<user>:<password>@<rds-endpoint>:5432/invoice_platform` |
| `REDIS_URL` | `redis://<elasticache-endpoint>:6379/0` (use `rediss://` if in-transit encryption is on) |
| `JWT_SECRET` | Long random string; must not be the local default |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` | At least one, for invoice extraction |
| `OBJECT_STORAGE_ACCESS_KEY_ID` / `..._SECRET_ACCESS_KEY` | Empty when using the IAM role |

Do **not** `kubectl apply` the example file with real values.

### 3.3 Config to change before first deploy

All in `infra/k8s/`:

1. **Image names.** The base manifests use bare names (`invoice-platform-backend:latest`).
   In each overlay's `images:` block add `newName: <account>.dkr.ecr.<region>.amazonaws.com/invoice-platform-backend`
   (and the frontend equivalent) and set `newTag` to the git SHA. The production
   overlay currently pins `1.0.0`.
2. **`CORS_ALLOWED_ORIGINS`** in `base/configmap.yaml` (placeholder
   `https://replace-with-production-frontend.example.com`) → your real app origin.
3. **`OBJECT_STORAGE_BUCKET`** and **`OBJECT_STORAGE_REGION`** in the configmap.
4. **Ingress host and TLS** in `base/ingress.yaml` — there is no `host:` or `tls:`
   block yet.

### 3.4 Release procedure

1. Build and push both images tagged with the commit SHA.
2. Back up RDS (snapshot).
3. Run migrations. `backend-migrate` is a Kubernetes Job and its pod template is
   immutable, so delete the previous one first:
   ```bash
   kubectl -n invoice-platform-production delete job backend-migrate --ignore-not-found
   kubectl apply -k infra/k8s/overlays/production
   kubectl -n invoice-platform-production wait --for=condition=complete job/backend-migrate --timeout=300s
   ```
   `RUN_MIGRATIONS_ON_START` is `false` in the configmap, so API pods never migrate.
   Note: `kubectl apply -k` applies the Job **and** the deployments together, so
   new pods can start before the migration finishes. That is safe only for
   backward-compatible migrations. For strict ordering, apply the Job on its own
   first (or use a Helm/Argo pre-sync hook) — this ordering is not automated yet.
4. Watch the rollout:
   `kubectl -n invoice-platform-production rollout status deploy/backend deploy/worker deploy/frontend`
5. Smoke test: `API_BASE_URL=https://<app-host> scripts/smoke-test.sh`
6. **First deploy only:** create the first admin (section "First Admin Bootstrap"
   in `deployment-guide.md`), run inside a backend pod:
   ```bash
   kubectl -n invoice-platform-production exec deploy/backend -- \
     python /app/scripts/bootstrap-admin.py --organization "<org>" --email <admin-email> --password '<long-random>'
   ```

Rollback: roll the deployments back to the previous image tag; keep the database
at the current revision (prefer forward-fix migrations). Full procedure in
`deployment-guide.md`.

### 3.5 Production overlay sizing

Backend 3 replicas (HPA min 2 / max 6, CPU-based), worker 2, frontend 2. Each
worker opens its own DB connections — size RDS `max_connections` for
(backend + worker replicas) × pool size.

---

## 4. Option B: single EC2 box

Everything is in `infra/aws-micro/`; follow its `README.md`. In short:

1. Push the backend image to ECR.
2. Fill every `__PLACEHOLDER__` in `cloud-init.yaml` (prefer pulling secrets from
   SSM Parameter Store via the instance role rather than inlining them).
3. Launch an Ubuntu 24.04 `t3.micro` (or `t3.small`; switch the compose file to
   `docker-compose.small.yml`) with that user-data and an instance role with ECR
   pull. Open 80/443 (and 22 from your IP only).
4. Point a DNS A record at the box for `API_DOMAIN`; Caddy gets the TLS cert.
5. Deploy the frontend: `API_BASE_URL=https://<api-domain> BUCKET=<name> ./frontend-deploy.sh`,
   then create the CloudFront distribution as the script prints.

The backend runs migrations on start (`RUN_MIGRATIONS_ON_START=true`) on this option.
Back up the `postgres_data` volume (EBS snapshots) — the database lives on the box.

**Watch out — cookies across domains (unverified):** auth uses cookies with
`COOKIE_SAMESITE=lax`. If the frontend is on `*.cloudfront.net` and the API on
your own domain, the browser treats them as different sites and may not send the
auth cookies on API calls. Serve both under the same registrable domain (e.g.
`app.example.com` via CloudFront and `api.example.com` via Caddy) to avoid this.
Test login and token refresh before handing the URL to users.

---

## 5. Not built yet

| Gap | Impact | Owner action |
|---|---|---|
| CI does not push images | `.github/workflows/ci.yml` runs lint, tests, audits and a compose smoke test only | Add a build → push to ECR → deploy job (GitHub OIDC to an AWS role; no long-lived keys) |
| No AWS Terraform | RDS, ElastiCache, S3, ECR, IAM, VPC, EKS must be written | Extend `infra/terraform/` (stubs are commented in `main.tf`) |
| Ingress has no host/TLS | Not reachable on a real hostname | Add host, TLS secret / ACM annotations |
| Image names are placeholders | Pods won't pull | `newName`/`newTag` in overlays |
| Monitoring not wired | `infra/monitoring/grafana/` has a dashboard; nothing scrapes `/metrics` | Prometheus (or Amazon Managed Prometheus) scraping the backend `/metrics` |
| Backups / restore drill | Required by `production-readiness-checklist.md` | RDS automated backups + S3 versioning + one restore drill in staging |

## 6. What has been verified

- `infra/aws-micro/docker-compose.micro.yml` was run locally (2026-11-25) with a
  locally built backend image: migrations applied through `20260717_0006`,
  `/health/ready` returned `{"status":"ready","checks":{"database":"ok","redis":"ok"}}`,
  idle memory ~165 MB across the four containers. No AI key was set, so
  extraction was not exercised.
- The Kubernetes manifests are documented as validated on a local `kind` cluster
  (`scripts/kind-deploy.sh`), not on EKS.
- Nothing in this document has been run against a real AWS account yet.

## 7. Questions to bring to the app team

- Which AI provider(s) and models to use in production, and the monthly spend cap.
- Expected invoice volume (drives worker replica count and RDS size).
- Data residency / AWS region requirements for invoice files and the database.
