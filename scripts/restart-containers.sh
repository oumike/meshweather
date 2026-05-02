#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.yml}"
TAIL_LINES="${TAIL_LINES:-120}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not on PATH." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Error: docker compose plugin is unavailable." >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Error: compose file not found at $COMPOSE_FILE" >&2
  exit 1
fi

echo "Validating compose config..."
docker compose -f "$COMPOSE_FILE" config >/dev/null

echo "Pulling latest images..."
docker compose -f "$COMPOSE_FILE" pull

echo "Stopping existing containers (if running)..."
docker compose -f "$COMPOSE_FILE" stop meshweather-frontend meshweather-ingestor || true

echo "Removing existing containers (if present)..."
docker compose -f "$COMPOSE_FILE" rm -f meshweather-frontend meshweather-ingestor || true

echo "Recreating containers..."
docker compose -f "$COMPOSE_FILE" up -d --force-recreate

echo "Current container status:"
docker compose -f "$COMPOSE_FILE" ps

echo
echo "Recent ingestor logs (last $TAIL_LINES lines):"
docker compose -f "$COMPOSE_FILE" logs meshweather-ingestor --tail="$TAIL_LINES"

echo
echo "Recent frontend logs (last $TAIL_LINES lines):"
docker compose -f "$COMPOSE_FILE" logs meshweather-frontend --tail="$TAIL_LINES"

echo
echo "Done. Frontend should be available at http://localhost:${MESHWEATHER_FRONTEND_PORT:-10090}"
