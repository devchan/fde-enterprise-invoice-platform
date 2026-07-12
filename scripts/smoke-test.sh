#!/usr/bin/env sh
set -eu

API_BASE_URL="${API_BASE_URL:-http://localhost:8010}"

curl -fsS "$API_BASE_URL/health"
printf '\n'
curl -fsS "$API_BASE_URL/metrics" >/dev/null
