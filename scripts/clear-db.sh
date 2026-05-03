#!/usr/bin/env bash
set -euo pipefail

SERVICE="meshweather-ingestor"
DB_PATH="/app/data/meshweather.db"
FORCE=0

show_help() {
  cat <<'EOF'
Clear meshweather ingested data from SQLite while preserving schema.

Usage:
  scripts/clear-db.sh [options]

Options:
  -s, --service NAME   Container name (default: meshweather-ingestor)
  -d, --db-path PATH   SQLite path in container (default: /app/data/meshweather.db)
  -f, --force          Skip confirmation prompt
  -h, --help           Show this help message and exit
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--service)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo "Error: --service requires a value." >&2
        exit 1
      fi
      SERVICE="$2"
      shift 2
      ;;
    -d|--db-path)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo "Error: --db-path requires a value." >&2
        exit 1
      fi
      DB_PATH="$2"
      shift 2
      ;;
    -f|--force)
      FORCE=1
      shift
      ;;
    -h|--help)
      show_help
      exit 0
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

if ! docker ps --format '{{.Names}}' | grep -Fxq "$SERVICE"; then
  echo "Error: container '$SERVICE' is not running." >&2
  exit 1
fi

if [[ "$FORCE" -ne 1 ]]; then
  echo "This will delete all rows from weather_telemetry in: $DB_PATH"
  read -r -p "Type 'yes' to continue: " confirm
  if [[ "$confirm" != "yes" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

docker exec -i "$SERVICE" python - "$DB_PATH" <<'PY'
import sqlite3
import sys

if len(sys.argv) < 2:
    raise SystemExit("missing db path")

db_path = sys.argv[1]

con = sqlite3.connect(db_path)
cur = con.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='weather_telemetry'")
exists = cur.fetchone() is not None
if not exists:
    raise SystemExit("Table 'weather_telemetry' does not exist in database")

cur.execute("SELECT COUNT(*) FROM weather_telemetry")
before = int(cur.fetchone()[0])

cur.execute("DELETE FROM weather_telemetry")
con.commit()

# VACUUM must run outside a transaction in SQLite.
con.execute("VACUUM")

cur.execute("SELECT COUNT(*) FROM weather_telemetry")
after = int(cur.fetchone()[0])

print(f"Cleared weather_telemetry: {before} -> {after} rows")
con.close()
PY
