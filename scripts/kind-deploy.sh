#!/usr/bin/env bash
# Deploy the invoice platform to a local kind cluster for end-to-end validation
# of the Kubernetes manifests. One command, self-contained (in-cluster Postgres
# + Redis via the overlays/local overlay). Requires: docker, kind, kubectl.
#
# Usage:
#   scripts/kind-deploy.sh            # build, create cluster, deploy, verify
#   scripts/kind-deploy.sh --delete   # tear the cluster down
#
# After a successful run the cockpit is served at http://localhost:8081
# (ingress-nginx routes / -> frontend, /api and /health -> backend).
set -euo pipefail

CLUSTER=invoice
NS=invoice-platform-local
INGRESS_HOST="http://localhost:8081"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OVERLAY="$REPO_ROOT/infra/k8s/overlays/local"
BACKEND_IMAGE=invoice-platform-backend:local
FRONTEND_IMAGE=invoice-platform-frontend:local
INGRESS_MANIFEST="https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml"

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: '$1' is required but not installed." >&2; exit 1; }; }

if [[ "${1:-}" == "--delete" ]]; then
  need kind
  kind delete cluster --name "$CLUSTER"
  echo "Cluster '$CLUSTER' deleted."
  exit 0
fi

need docker; need kind; need kubectl

echo "==> Building images"
docker build -f "$REPO_ROOT/backend/Dockerfile" --target runtime -t "$BACKEND_IMAGE" "$REPO_ROOT"
docker build -f "$REPO_ROOT/frontend/Dockerfile" --target production \
  --build-arg "VITE_API_BASE_URL=$INGRESS_HOST" -t "$FRONTEND_IMAGE" "$REPO_ROOT"

echo "==> Creating kind cluster '$CLUSTER' (if absent)"
if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  kind create cluster --name "$CLUSTER" --config "$OVERLAY/kind-cluster.yaml" --wait 120s
fi

echo "==> Loading images into the cluster"
# Pull the dev dependencies locally first so kind loads them from the daemon.
docker image inspect postgres:16 >/dev/null 2>&1 || docker pull postgres:16
docker image inspect redis:7 >/dev/null 2>&1 || docker pull redis:7
kind load docker-image "$BACKEND_IMAGE" "$FRONTEND_IMAGE" postgres:16 redis:7 --name "$CLUSTER"

echo "==> Installing ingress-nginx"
kubectl apply -f "$INGRESS_MANIFEST"
kubectl -n ingress-nginx wait --for=condition=available deploy/ingress-nginx-controller --timeout=180s

echo "==> Applying the local overlay"
kubectl apply -k "$OVERLAY"

echo "==> Waiting for Postgres and Redis"
kubectl -n "$NS" rollout status deploy/postgres --timeout=120s
kubectl -n "$NS" rollout status deploy/redis --timeout=120s

echo "==> Running database migrations"
# The migration Job is created by the overlay; wait for it to complete. If a
# previous run left a finished Job, recreate it.
kubectl -n "$NS" delete job backend-migrate --ignore-not-found
kubectl apply -k "$OVERLAY"
kubectl -n "$NS" wait --for=condition=complete job/backend-migrate --timeout=180s

echo "==> Waiting for application rollouts"
kubectl -n "$NS" rollout status deploy/backend --timeout=180s
kubectl -n "$NS" rollout status deploy/worker --timeout=180s
kubectl -n "$NS" rollout status deploy/frontend --timeout=180s

echo "==> Verifying readiness through the ingress"
for i in $(seq 1 30); do
  if curl -fsS "$INGRESS_HOST/health/ready" >/dev/null 2>&1; then break; fi
  sleep 3
done
echo "readiness: $(curl -fsS "$INGRESS_HOST/health/ready" || echo unreachable)"
echo "frontend:  HTTP $(curl -fsS -o /dev/null -w '%{http_code}' "$INGRESS_HOST/" || echo '000')"

echo
echo "Deployed. Cockpit: $INGRESS_HOST"
echo "Inspect:   kubectl -n $NS get pods,svc,ingress"
echo "Tear down: scripts/kind-deploy.sh --delete"
