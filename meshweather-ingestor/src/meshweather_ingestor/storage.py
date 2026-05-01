import base64
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .models import WeatherObservation


NODE_KEY_SQL = """
CASE
    WHEN packet_from_id IS NOT NULL AND TRIM(packet_from_id) <> '' THEN 'id:' || packet_from_id
    WHEN packet_from IS NOT NULL THEN 'num:' || CAST(packet_from AS TEXT)
    ELSE 'unknown:' || CAST(id AS TEXT)
END
"""

NODE_LABEL_SQL = """
COALESCE(
    NULLIF(TRIM(node_long_name), ''),
    NULLIF(TRIM(node_short_name), ''),
    NULLIF(TRIM(packet_from_id), ''),
    CASE
        WHEN packet_from IS NOT NULL THEN 'Node ' || CAST(packet_from AS TEXT)
        ELSE 'Unknown node'
    END
)
"""

SORT_TS_SQL = """
COALESCE(
    packet_rx_time,
    telemetry_time,
    CAST(strftime('%s', ingested_at_utc) AS INTEGER)
)
"""

BASE_FIELDS_SQL = """
id,
ingested_at_utc,
packet_rx_time,
telemetry_time,
packet_from,
packet_from_id,
node_long_name,
node_short_name,
node_latitude,
node_longitude,
packet_id,
temperature_c,
relative_humidity,
barometric_pressure_hpa,
wind_direction_deg,
wind_speed_m_s,
wind_gust_m_s,
wind_lull_m_s,
rainfall_1h_mm,
rainfall_24h_mm,
lux,
uv_lux
"""


class SqliteWeatherRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS weather_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ingested_at_utc TEXT NOT NULL,
                    packet_rx_time INTEGER,
                    telemetry_time INTEGER,
                    packet_from INTEGER,
                    packet_from_id TEXT,
                    node_long_name TEXT,
                    node_short_name TEXT,
                    node_latitude REAL,
                    node_longitude REAL,
                    packet_id INTEGER,
                    dedup_key TEXT,
                    temperature_c REAL,
                    relative_humidity REAL,
                    barometric_pressure_hpa REAL,
                    wind_direction_deg INTEGER,
                    wind_speed_m_s REAL,
                    wind_gust_m_s REAL,
                    wind_lull_m_s REAL,
                    rainfall_1h_mm REAL,
                    rainfall_24h_mm REAL,
                    lux REAL,
                    uv_lux REAL,
                    raw_packet_json TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS uq_weather_telemetry_dedup_key
                    ON weather_telemetry(dedup_key)
                    WHERE dedup_key IS NOT NULL;

                CREATE INDEX IF NOT EXISTS ix_weather_telemetry_packet_rx_time
                    ON weather_telemetry(packet_rx_time);

                CREATE INDEX IF NOT EXISTS ix_weather_telemetry_ingested_at
                    ON weather_telemetry(ingested_at_utc);
                """
            )

            self._ensure_column("node_long_name", "TEXT")
            self._ensure_column("node_short_name", "TEXT")
            self._ensure_column("node_latitude", "REAL")
            self._ensure_column("node_longitude", "REAL")
            self._conn.commit()

    def _ensure_column(self, name: str, sql_type: str) -> None:
        cursor = self._conn.execute("PRAGMA table_info(weather_telemetry)")
        columns = {row[1] for row in cursor.fetchall()}
        if name in columns:
            return

        self._conn.execute(
            f"ALTER TABLE weather_telemetry ADD COLUMN {name} {sql_type}"
        )

    def insert_observation(
        self, observation: WeatherObservation, packet: Mapping[str, Any]
    ) -> bool:
        dedup_key = None
        if observation.packet_from is not None and observation.packet_id is not None:
            dedup_key = f"{observation.packet_from}:{observation.packet_id}"

        row = (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            observation.packet_rx_time,
            observation.telemetry_time,
            observation.packet_from,
            observation.packet_from_id,
            observation.node_long_name,
            observation.node_short_name,
            observation.node_latitude,
            observation.node_longitude,
            observation.packet_id,
            dedup_key,
            observation.temperature_c,
            observation.relative_humidity,
            observation.barometric_pressure_hpa,
            observation.wind_direction_deg,
            observation.wind_speed_m_s,
            observation.wind_gust_m_s,
            observation.wind_lull_m_s,
            observation.rainfall_1h_mm,
            observation.rainfall_24h_mm,
            observation.lux,
            observation.uv_lux,
            json.dumps(_to_jsonable(packet), separators=(",", ":"), sort_keys=True),
        )

        try:
            with self._lock:
                self._conn.execute(
                    """
                    INSERT INTO weather_telemetry (
                        ingested_at_utc,
                        packet_rx_time,
                        telemetry_time,
                        packet_from,
                        packet_from_id,
                        node_long_name,
                        node_short_name,
                        node_latitude,
                        node_longitude,
                        packet_id,
                        dedup_key,
                        temperature_c,
                        relative_humidity,
                        barometric_pressure_hpa,
                        wind_direction_deg,
                        wind_speed_m_s,
                        wind_gust_m_s,
                        wind_lull_m_s,
                        rainfall_1h_mm,
                        rainfall_24h_mm,
                        lux,
                        uv_lux,
                        raw_packet_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
                self._conn.commit()
        except sqlite3.IntegrityError:
            return False

        return True

    def count_observations(self) -> int:
        with self._lock:
            cursor = self._conn.execute("SELECT COUNT(1) FROM weather_telemetry")
            count = cursor.fetchone()[0]
        return int(count)

    def fetch_recent_observations(self, limit: int = 500) -> list[dict[str, Any]]:
        query_limit = _normalize_limit(limit, default=500, max_value=10000)

        with self._lock:
            cursor = self._conn.execute(
                f"""
                SELECT
                    {BASE_FIELDS_SQL},
                    {NODE_KEY_SQL} AS node_key,
                    {NODE_LABEL_SQL} AS node_label,
                    {SORT_TS_SQL} AS sort_ts
                FROM weather_telemetry
                ORDER BY sort_ts DESC, id DESC
                LIMIT ?
                """,
                (query_limit,),
            )
            rows = cursor.fetchall()

        return [_row_to_dict(row) for row in rows]

    def fetch_latest_nodes(self, limit: int = 500) -> list[dict[str, Any]]:
        query_limit = _normalize_limit(limit, default=500, max_value=10000)

        with self._lock:
            cursor = self._conn.execute(
                f"""
                WITH source AS (
                    SELECT
                        {BASE_FIELDS_SQL},
                        {NODE_KEY_SQL} AS node_key,
                        {NODE_LABEL_SQL} AS node_label,
                        {SORT_TS_SQL} AS sort_ts
                    FROM weather_telemetry
                ),
                ranked AS (
                    SELECT
                        source.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY node_key
                            ORDER BY sort_ts DESC, id DESC
                        ) AS row_num
                    FROM source
                )
                SELECT
                    {BASE_FIELDS_SQL},
                    node_key,
                    node_label,
                    sort_ts
                FROM ranked
                WHERE row_num = 1
                ORDER BY sort_ts DESC, id DESC
                LIMIT ?
                """,
                (query_limit,),
            )
            rows = cursor.fetchall()

        return [_row_to_dict(row) for row in rows]

    def fetch_node_history(self, node_key: str, limit: int = 200) -> list[dict[str, Any]]:
        query_limit = _normalize_limit(limit, default=200, max_value=5000)

        with self._lock:
            cursor = self._conn.execute(
                f"""
                WITH source AS (
                    SELECT
                        {BASE_FIELDS_SQL},
                        {NODE_KEY_SQL} AS node_key,
                        {NODE_LABEL_SQL} AS node_label,
                        {SORT_TS_SQL} AS sort_ts
                    FROM weather_telemetry
                )
                SELECT
                    {BASE_FIELDS_SQL},
                    node_key,
                    node_label,
                    sort_ts
                FROM source
                WHERE node_key = ?
                ORDER BY sort_ts DESC, id DESC
                LIMIT ?
                """,
                (node_key, query_limit),
            )
            rows = cursor.fetchall()

        return [_row_to_dict(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _normalize_limit(value: int, default: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 1:
        return default
    if parsed > max_value:
        return max_value
    return parsed


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        jsonable: dict[str, Any] = {}
        for key, nested in value.items():
            if key == "raw":
                continue
            jsonable[str(key)] = _to_jsonable(nested)
        return jsonable

    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]

    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return str(value)
