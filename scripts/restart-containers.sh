#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
ENV_FILE="$ROOT_DIR/meshweather-ingestor/.env"
TAIL_LINES=120

show_help() {
  cat <<'EOF'
Restart meshweather containers with latest images, using an env file.

Usage:
  scripts/restart-containers.sh [options]

Options:
  -e, --env PATH  Path to env file (default: <repo>/meshweather-ingestor/.env)
  -h, --help    Show this help message and exit.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      show_help
      exit 0
      ;;
    -e|--env)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo "Error: --env requires a path argument." >&2
        exit 1
      fi
      ENV_FILE="$2"
      shift 2
      ;;
    *)
      echo "Error: unknown argument '$1'" >&2
      echo "Run with --help for usage." >&2
      exit 1
      ;;
  esac
done

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

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: env file not found at $ENV_FILE" >&2
  exit 1
fi

COMPOSE_CMD=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

echo "Validating compose config..."
"${COMPOSE_CMD[@]}" config >/dev/null

echo "Pulling latest images..."
"${COMPOSE_CMD[@]}" pull

echo "Stopping existing containers (if running)..."
"${COMPOSE_CMD[@]}" stop meshweather-frontend meshweather-ingestor || true

echo "Removing existing containers (if present)..."
"${COMPOSE_CMD[@]}" rm -f meshweather-frontend meshweather-ingestor || true

echo "Recreating containers..."
"${COMPOSE_CMD[@]}" up -d --force-recreate

echo "Current container status:"
"${COMPOSE_CMD[@]}" ps

echo
echo "Recent ingestor logs (last $TAIL_LINES lines):"
"${COMPOSE_CMD[@]}" logs meshweather-ingestor --tail="$TAIL_LINES"

echo
echo "Recent frontend logs (last $TAIL_LINES lines):"
"${COMPOSE_CMD[@]}" logs meshweather-frontend --tail="$TAIL_LINES"

echo
echo "Done. Frontend should be available at http://localhost:${MESHWEATHER_FRONTEND_PORT:-10090}"
