#!/usr/bin/env bash
set -euo pipefail

SERVICE="${SERVICE:-meshweather-ingestor}"
DB_PATH="${DB_PATH:-/app/data/meshweather.db}"
LIMIT="${LIMIT:-10}"
TABLE="${TABLE:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)
      SERVICE="$2"
      shift 2
      ;;
    --db-path)
      DB_PATH="$2"
      shift 2
      ;;
    --limit)
      LIMIT="$2"
      shift 2
      ;;
    --table)
      TABLE="$2"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Inspect meshweather SQLite data inside a running container.

Usage:
  scripts/inspect-db.sh [--service NAME] [--db-path PATH] [--limit N] [--table NAME]

Examples:
  scripts/inspect-db.sh
  scripts/inspect-db.sh --table weather_telemetry --limit 20
  SERVICE=meshweather-ingestor scripts/inspect-db.sh
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
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

docker exec -i "$SERVICE" python - "$DB_PATH" "$LIMIT" "$TABLE" <<'PY'
import sqlite3
import sys

if len(sys.argv) < 4:
    raise SystemExit("missing required args")

db_path = sys.argv[1]
limit = int(sys.argv[2])
table = sys.argv[3].strip()

con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row
cur = con.cursor()

try:
    tables = [
        row[0]
        for row in cur.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]

    if not tables:
        print("No user tables found.")
        raise SystemExit(0)

    if table:
        if table not in tables:
            print(f"Table '{table}' not found. Available: {', '.join(tables)}")
            raise SystemExit(1)

        rows = cur.execute(f"SELECT * FROM {table} LIMIT ?", (limit,)).fetchall()
        print(f"Table: {table}")
        print(f"Rows returned: {len(rows)}")
        for row in rows:
            print(dict(row))
        raise SystemExit(0)

    print("Tables:")
    for name in tables:
        count = cur.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"- {name}: {count}")

    if "discovered_nodes" in tables:
      print("\nLatest discovered nodes:")
      rows = cur.execute(
        """
        SELECT
          node_key,
          node_long_name,
          node_short_name,
          node_latitude,
          node_longitude,
          last_packet_id,
          last_seen_utc
        FROM discovered_nodes
        ORDER BY last_seen_utc DESC, id DESC
        LIMIT ?
        """,
        (limit,),
      ).fetchall()
      for row in rows:
        print(dict(row))

    if "weather_telemetry" in tables:
      print("\nLatest weather telemetry:")
      rows = cur.execute(
        """
        SELECT
          wt.id,
          COALESCE(dn.node_key, wt.packet_from_id, wt.packet_from, 'unknown') AS node_ref,
          wt.packet_id,
          wt.temperature_c,
          wt.relative_humidity,
          wt.barometric_pressure_hpa,
          wt.ingested_at_utc
        FROM weather_telemetry AS wt
        LEFT JOIN discovered_nodes AS dn
          ON dn.id = wt.node_id
        ORDER BY
          COALESCE(
            wt.packet_rx_time,
            wt.telemetry_time,
            CAST(strftime('%s', wt.ingested_at_utc) AS INTEGER)
          ) DESC,
          wt.id DESC
        LIMIT ?
        """,
        (limit,),
      ).fetchall()
      for row in rows:
        print(dict(row))
finally:
    con.close()
PY
