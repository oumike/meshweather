#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
ENV_FILE="$ROOT_DIR/meshweather-ingestor/.env"
REMOVE_VOLUMES=0
REMOVE_IMAGES=1

INGESTOR_IMAGE="ghcr.io/oumike/meshweather-ingestor:latest"
FRONTEND_IMAGE="ghcr.io/oumike/meshweather-frontend:latest"

show_help() {
  cat <<'EOF'
Stop meshweather containers and clean source-built images.

Usage:
  scripts/stop-containers-from-source.sh [options]

Options:
  -e, --env PATH    Path to env file (default: <repo>/meshweather-ingestor/.env)
      --volumes     Remove compose volumes (includes meshweather_data).
      --keep-images Keep images instead of removing source-built tags.
  -h, --help        Show this help message and exit.
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
    --volumes)
      REMOVE_VOLUMES=1
      shift
      ;;
    --keep-images)
      REMOVE_IMAGES=0
      shift
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

DOWN_ARGS=(down --remove-orphans)
if [[ "$REMOVE_VOLUMES" -eq 1 ]]; then
  DOWN_ARGS+=(--volumes)
fi

echo "Stopping and removing containers..."
"${COMPOSE_CMD[@]}" "${DOWN_ARGS[@]}"

if [[ "$REMOVE_IMAGES" -eq 1 ]]; then
  echo "Removing source-built images (if present)..."
  for image in "$INGESTOR_IMAGE" "$FRONTEND_IMAGE"; do
    if docker image inspect "$image" >/dev/null 2>&1; then
      docker image rm -f "$image" >/dev/null
      echo "Removed image: $image"
    else
      echo "Image not found, skipping: $image"
    fi
  done
else
  echo "Keeping source-built images."
fi

echo
if [[ "$REMOVE_VOLUMES" -eq 1 ]]; then
  echo "Done. Containers, source-built images, and compose volumes were cleaned."
else
  echo "Done. Containers and source-built images were cleaned. Data volume was preserved."
fi
