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

NODE_LABEL_FROM_NODE_SQL = """
COALESCE(
    NULLIF(TRIM(n.node_long_name), ''),
    NULLIF(TRIM(n.node_short_name), ''),
    NULLIF(TRIM(n.packet_from_id), ''),
    CASE
        WHEN n.packet_from IS NOT NULL THEN 'Node ' || CAST(n.packet_from AS TEXT)
        ELSE 'Unknown node'
    END
)
"""

WEATHER_SORT_TS_SQL = """
COALESCE(
    packet_rx_time,
    telemetry_time,
    CAST(strftime('%s', ingested_at_utc) AS INTEGER)
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
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS discovered_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_key TEXT NOT NULL UNIQUE,
                    packet_from INTEGER,
                    packet_from_id TEXT,
                    node_long_name TEXT,
                    node_short_name TEXT,
                    node_latitude REAL,
                    node_longitude REAL,
                    first_seen_utc TEXT NOT NULL,
                    last_seen_utc TEXT NOT NULL,
                    last_packet_rx_time INTEGER,
                    last_telemetry_time INTEGER,
                    last_packet_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS weather_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ingested_at_utc TEXT NOT NULL,
                    node_id INTEGER,
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
                    raw_packet_json TEXT NOT NULL,
                    FOREIGN KEY(node_id) REFERENCES discovered_nodes(id)
                );

                CREATE INDEX IF NOT EXISTS ix_discovered_nodes_last_seen
                    ON discovered_nodes(last_seen_utc);

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
            self._ensure_column("node_id", "INTEGER")

            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_weather_telemetry_node_id
                    ON weather_telemetry(node_id)
                """
            )

            self._backfill_discovered_nodes()
            self._conn.commit()

    def _ensure_column(self, name: str, sql_type: str) -> None:
        cursor = self._conn.execute("PRAGMA table_info(weather_telemetry)")
        columns = {row[1] for row in cursor.fetchall()}
        if name in columns:
            return

        self._conn.execute(
            f"ALTER TABLE weather_telemetry ADD COLUMN {name} {sql_type}"
        )

    def _build_node_key(
        self,
        packet_from_id: str | None,
        packet_from: int | None,
    ) -> str | None:
        if packet_from_id:
            return f"id:{packet_from_id}"
        if packet_from is not None:
            return f"num:{packet_from}"
        return None

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    def _upsert_discovered_node_values(
        self,
        packet_from: int | None,
        packet_from_id: str | None,
        node_long_name: str | None,
        node_short_name: str | None,
        node_latitude: float | None,
        node_longitude: float | None,
        packet_rx_time: int | None,
        telemetry_time: int | None,
        packet_id: int | None,
        seen_at_utc: str,
    ) -> int | None:
        normalized_packet_from_id = self._normalize_optional_text(packet_from_id)
        normalized_long_name = self._normalize_optional_text(node_long_name)
        normalized_short_name = self._normalize_optional_text(node_short_name)
        node_key = self._build_node_key(normalized_packet_from_id, packet_from)

        if node_key is None:
            return None

        self._conn.execute(
            """
            INSERT INTO discovered_nodes (
                node_key,
                packet_from,
                packet_from_id,
                node_long_name,
                node_short_name,
                node_latitude,
                node_longitude,
                first_seen_utc,
                last_seen_utc,
                last_packet_rx_time,
                last_telemetry_time,
                last_packet_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_key) DO UPDATE SET
                packet_from = COALESCE(excluded.packet_from, discovered_nodes.packet_from),
                packet_from_id = COALESCE(excluded.packet_from_id, discovered_nodes.packet_from_id),
                node_long_name = COALESCE(excluded.node_long_name, discovered_nodes.node_long_name),
                node_short_name = COALESCE(excluded.node_short_name, discovered_nodes.node_short_name),
                node_latitude = COALESCE(excluded.node_latitude, discovered_nodes.node_latitude),
                node_longitude = COALESCE(excluded.node_longitude, discovered_nodes.node_longitude),
                last_seen_utc = excluded.last_seen_utc,
                last_packet_rx_time = COALESCE(excluded.last_packet_rx_time, discovered_nodes.last_packet_rx_time),
                last_telemetry_time = COALESCE(excluded.last_telemetry_time, discovered_nodes.last_telemetry_time),
                last_packet_id = COALESCE(excluded.last_packet_id, discovered_nodes.last_packet_id)
            """,
            (
                node_key,
                packet_from,
                normalized_packet_from_id,
                normalized_long_name,
                normalized_short_name,
                node_latitude,
                node_longitude,
                seen_at_utc,
                seen_at_utc,
                packet_rx_time,
                telemetry_time,
                packet_id,
            ),
        )

        cursor = self._conn.execute(
            "SELECT id FROM discovered_nodes WHERE node_key = ?",
            (node_key,),
        )
        row = cursor.fetchone()
        return int(row[0]) if row is not None else None

    def _upsert_discovered_node(
        self,
        observation: WeatherObservation,
        seen_at_utc: str,
    ) -> int | None:
        return self._upsert_discovered_node_values(
            packet_from=observation.packet_from,
            packet_from_id=observation.packet_from_id,
            node_long_name=observation.node_long_name,
            node_short_name=observation.node_short_name,
            node_latitude=observation.node_latitude,
            node_longitude=observation.node_longitude,
            packet_rx_time=observation.packet_rx_time,
            telemetry_time=observation.telemetry_time,
            packet_id=observation.packet_id,
            seen_at_utc=seen_at_utc,
        )

    def _backfill_discovered_nodes(self) -> None:
        cursor = self._conn.execute(
            """
            SELECT
                id,
                node_id,
                ingested_at_utc,
                packet_from,
                packet_from_id,
                node_long_name,
                node_short_name,
                node_latitude,
                node_longitude,
                packet_rx_time,
                telemetry_time,
                packet_id
            FROM weather_telemetry
            ORDER BY id ASC
            """
        )

        for row in cursor.fetchall():
            node_id = self._upsert_discovered_node_values(
                packet_from=row["packet_from"],
                packet_from_id=row["packet_from_id"],
                node_long_name=row["node_long_name"],
                node_short_name=row["node_short_name"],
                node_latitude=row["node_latitude"],
                node_longitude=row["node_longitude"],
                packet_rx_time=row["packet_rx_time"],
                telemetry_time=row["telemetry_time"],
                packet_id=row["packet_id"],
                seen_at_utc=row["ingested_at_utc"],
            )

            if row["node_id"] is None and node_id is not None:
                self._conn.execute(
                    "UPDATE weather_telemetry SET node_id = ? WHERE id = ?",
                    (node_id, row["id"]),
                )

    def insert_observation(
        self, observation: WeatherObservation, packet: Mapping[str, Any]
    ) -> bool:
        dedup_key = None
        if observation.packet_from is not None and observation.packet_id is not None:
            dedup_key = f"{observation.packet_from}:{observation.packet_id}"

        ingested_at_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with self._lock:
            node_id = self._upsert_discovered_node(observation, ingested_at_utc)
            row = (
                ingested_at_utc,
                node_id,
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
                self._conn.execute(
                    """
                    INSERT INTO weather_telemetry (
                        ingested_at_utc,
                        node_id,
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
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
            except sqlite3.IntegrityError:
                # Persist discovered node metadata updates even when packet dedup prevents insert.
                self._conn.commit()
                return False

            self._conn.commit()

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
                WITH latest_weather AS (
                    SELECT
                        weather_telemetry.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY weather_telemetry.node_id
                            ORDER BY {WEATHER_SORT_TS_SQL} DESC, id DESC
                        ) AS row_num
                    FROM weather_telemetry
                    WHERE weather_telemetry.node_id IS NOT NULL
                )
                SELECT
                    COALESCE(latest_weather.id, 0) AS id,
                    COALESCE(latest_weather.ingested_at_utc, n.last_seen_utc) AS ingested_at_utc,
                    COALESCE(latest_weather.packet_rx_time, n.last_packet_rx_time) AS packet_rx_time,
                    COALESCE(latest_weather.telemetry_time, n.last_telemetry_time) AS telemetry_time,
                    n.packet_from AS packet_from,
                    n.packet_from_id AS packet_from_id,
                    n.node_long_name AS node_long_name,
                    n.node_short_name AS node_short_name,
                    n.node_latitude AS node_latitude,
                    n.node_longitude AS node_longitude,
                    COALESCE(latest_weather.packet_id, n.last_packet_id) AS packet_id,
                    latest_weather.temperature_c AS temperature_c,
                    latest_weather.relative_humidity AS relative_humidity,
                    latest_weather.barometric_pressure_hpa AS barometric_pressure_hpa,
                    latest_weather.wind_direction_deg AS wind_direction_deg,
                    latest_weather.wind_speed_m_s AS wind_speed_m_s,
                    latest_weather.wind_gust_m_s AS wind_gust_m_s,
                    latest_weather.wind_lull_m_s AS wind_lull_m_s,
                    latest_weather.rainfall_1h_mm AS rainfall_1h_mm,
                    latest_weather.rainfall_24h_mm AS rainfall_24h_mm,
                    latest_weather.lux AS lux,
                    latest_weather.uv_lux AS uv_lux,
                    n.node_key AS node_key,
                    {NODE_LABEL_FROM_NODE_SQL} AS node_label,
                    COALESCE(
                        latest_weather.packet_rx_time,
                        latest_weather.telemetry_time,
                        CAST(strftime('%s', latest_weather.ingested_at_utc) AS INTEGER),
                        n.last_packet_rx_time,
                        n.last_telemetry_time,
                        CAST(strftime('%s', n.last_seen_utc) AS INTEGER)
                    ) AS sort_ts
                FROM discovered_nodes AS n
                LEFT JOIN latest_weather
                    ON latest_weather.node_id = n.id
                    AND latest_weather.row_num = 1
                ORDER BY sort_ts DESC, n.id DESC
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
                SELECT
                    w.id,
                    w.ingested_at_utc,
                    w.packet_rx_time,
                    w.telemetry_time,
                    COALESCE(w.packet_from, n.packet_from) AS packet_from,
                    COALESCE(w.packet_from_id, n.packet_from_id) AS packet_from_id,
                    COALESCE(w.node_long_name, n.node_long_name) AS node_long_name,
                    COALESCE(w.node_short_name, n.node_short_name) AS node_short_name,
                    COALESCE(w.node_latitude, n.node_latitude) AS node_latitude,
                    COALESCE(w.node_longitude, n.node_longitude) AS node_longitude,
                    w.packet_id,
                    w.temperature_c,
                    w.relative_humidity,
                    w.barometric_pressure_hpa,
                    w.wind_direction_deg,
                    w.wind_speed_m_s,
                    w.wind_gust_m_s,
                    w.wind_lull_m_s,
                    w.rainfall_1h_mm,
                    w.rainfall_24h_mm,
                    w.lux,
                    w.uv_lux,
                    n.node_key AS node_key,
                    {NODE_LABEL_FROM_NODE_SQL} AS node_label,
                    COALESCE(
                        w.packet_rx_time,
                        w.telemetry_time,
                        CAST(strftime('%s', w.ingested_at_utc) AS INTEGER)
                    ) AS sort_ts
                FROM weather_telemetry AS w
                JOIN discovered_nodes AS n
                    ON n.id = w.node_id
                WHERE n.node_key = ?
                ORDER BY sort_ts DESC, w.id DESC
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
