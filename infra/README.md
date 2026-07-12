# Infrastructure

Infrastructure and operations assets.

Start simple:

- Docker Compose for local PostgreSQL and Redis
- GitHub Actions for tests
- environment variable documentation

Add later:

- object storage
- staging deployment
- production deployment
- OpenTelemetry collector
- Prometheus
- Grafana
- backup and restore scripts

## Deployment manifests

### Kubernetes (`k8s/`)

Kustomize-based manifests for deploying the platform to a Kubernetes cluster.

```
k8s/
  base/                 # namespace, deployments, services, ingress, config,
                        # secret example, HPA, and one-time migration Job
  overlays/staging/     # 1 replica each, staging image tags, APP_ENV=staging
  overlays/production/  # 3 backend replicas, production tags, APP_ENV=production
```

- Backend: liveness `GET /health`, readiness `GET /health/ready` (DB + Redis),
  runs as non-root uid 10001, read-only root filesystem, CPU-based HPA.
- Worker: same image, `python -m app.worker`, no ports/probes.
- Frontend: nginx-unprivileged (uid 101), readiness `GET /healthz`.
- Ingress routes `/api` and `/health` to the backend, everything else to the
  frontend.
- **Postgres and Redis are assumed to be external managed services** reached via
  `DATABASE_URL` / `REDIS_URL` in the Secret — there are no in-cluster
  StatefulSets. `base/secret.example.yaml` documents the required secret keys;
  supply real values via a secret manager / sealed-secrets, not plaintext.

Render/apply an environment:

```bash
kubectl apply -k infra/k8s/overlays/staging
kubectl apply -k infra/k8s/overlays/production
# or preview:
kustomize build infra/k8s/overlays/staging
```

Run migrations once per release via the `backend-migrate` Job (`alembic upgrade head`).

### Local kind deploy (`overlays/local` + `scripts/kind-deploy.sh`)

For a self-contained end-to-end validation of the manifests on a local
[kind](https://kind.sigs.k8s.io) cluster (requires `docker`, `kind`, `kubectl`):

```bash
scripts/kind-deploy.sh            # build images, create cluster, deploy, verify
scripts/kind-deploy.sh --delete   # tear the cluster down
```

Unlike staging/production (which assume external managed Postgres/Redis), the
`overlays/local` overlay is self-contained: it deploys in-cluster Postgres +
Redis, a throwaway dev Secret, local object storage, and `APP_ENV=local`. After
a successful run the cockpit is served at `http://localhost:8081` (ingress-nginx
routes `/` to the frontend and `/api` + `/health` to the backend). This overlay
is for local validation only — never point it at a real environment.

### Terraform (`terraform/`)

Cloud-neutral skeleton for the container-platform prerequisites (namespace,
in-cluster Secret, and commented stubs for managed Postgres/Redis/object
storage). See `terraform/README.md`. Backend state should be remote; secrets are
marked `sensitive`.

### Staging Docker Compose

`docker-compose.staging.yml` (repo root) mirrors `docker-compose.prod.yml` for a
self-contained single-replica staging stack:

```bash
docker compose --env-file .env.staging.example -f docker-compose.staging.yml up -d
```

