#!/usr/bin/env sh
set -eu

APP_URL="${APP_URL:-http://localhost:3000/}"
E2E_API_BASE_URL="${E2E_API_BASE_URL:-http://localhost:8010}"
E2E_ADMIN_EMAIL="${E2E_ADMIN_EMAIL:-e2e-admin-$(date +%s)@example.com}"
E2E_ADMIN_PASSWORD="${E2E_ADMIN_PASSWORD:-production-grade-password-123}"
E2E_ORGANIZATION="${E2E_ORGANIZATION:-FDE E2E Organization}"

docker compose exec -T backend python /app/scripts/bootstrap-admin.py \
  --organization "$E2E_ORGANIZATION" \
  --email "$E2E_ADMIN_EMAIL" \
  --password "$E2E_ADMIN_PASSWORD" >/tmp/fde-cockpit-e2e-bootstrap.log 2>&1 || {
    cat /tmp/fde-cockpit-e2e-bootstrap.log >&2
    exit 1
  }

cd frontend
APP_URL="$APP_URL" \
E2E_API_BASE_URL="$E2E_API_BASE_URL" \
E2E_ADMIN_EMAIL="$E2E_ADMIN_EMAIL" \
E2E_ADMIN_PASSWORD="$E2E_ADMIN_PASSWORD" \
npm run e2e
