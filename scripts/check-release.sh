#!/usr/bin/env sh
set -eu

docker compose config --quiet
docker compose exec -T backend alembic current
docker compose exec -T backend python -m pytest -q
docker compose exec -T backend python /app/scripts/bootstrap-admin.py --help >/dev/null
docker compose exec -T backend curl -fsS http://localhost:8000/health
docker compose exec -T backend curl -fsS http://localhost:8000/metrics >/dev/null
