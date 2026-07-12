#!/usr/bin/env sh
set -eu

COMPOSE_FILE_PATH="${COMPOSE_FILE_PATH:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
SERVICE="${MIGRATION_SERVICE:-backend}"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE_PATH" run --rm "$SERVICE" alembic upgrade head
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE_PATH" run --rm "$SERVICE" alembic current
