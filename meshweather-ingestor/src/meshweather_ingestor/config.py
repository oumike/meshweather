import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


@dataclass(slots=True)
class IngestorConfig:
    host: Optional[str]
    port: int
    db_path: Path
    log_level: str
    api_enabled: bool
    api_host: str
    api_port: int
    api_only: bool


def _read_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer.") from exc


def _read_env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ValueError(f"Environment variable {name} must be a boolean-like value.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meshweather-ingestor",
        description="Ingest Meshtastic weather telemetry over TCP/IP into SQLite.",
    )

    parser.add_argument(
        "--host",
        default=os.getenv("MESHTASTIC_NODE_IP", os.getenv("MESHWEATHER_HOST")),
        help="Meshtastic node hostname or IP. Can also be set by MESHTASTIC_NODE_IP.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_read_env_int("MESHWEATHER_PORT", 4403),
        help="Meshtastic TCP port. Default: 4403.",
    )
    parser.add_argument(
        "--db-path",
        default=os.getenv("MESHWEATHER_DB_PATH", "data/meshweather.db"),
        help="SQLite database path. Default: data/meshweather.db.",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("MESHWEATHER_LOG_LEVEL", "INFO"),
        help="Logging level: DEBUG, INFO, WARNING, ERROR. Default: INFO.",
    )
    parser.add_argument(
        "--api-host",
        default=os.getenv("MESHWEATHER_API_HOST", "127.0.0.1"),
        help="API bind host. Default: 127.0.0.1.",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=_read_env_int("MESHWEATHER_API_PORT", 8080),
        help="API bind port. Default: 8080.",
    )
    parser.add_argument(
        "--disable-api",
        action="store_true",
        default=not _read_env_bool("MESHWEATHER_API_ENABLED", True),
        help="Disable HTTP API server and run ingestion only.",
    )
    parser.add_argument(
        "--api-only",
        action="store_true",
        default=False,
        help="Run API without connecting to Meshtastic radio (serves existing DB).",
    )
    return parser


def load_config(argv: Optional[Sequence[str]] = None) -> IngestorConfig:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.api_only and args.disable_api:
        parser.error("--api-only cannot be combined with --disable-api.")

    if not args.api_only and not args.host:
        parser.error("--host is required (or set MESHTASTIC_NODE_IP).")

    log_level = str(args.log_level).upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        parser.error("--log-level must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL.")

    return IngestorConfig(
        host=str(args.host) if args.host else None,
        port=int(args.port),
        db_path=Path(args.db_path),
        log_level=log_level,
        api_enabled=not bool(args.disable_api),
        api_host=str(args.api_host),
        api_port=int(args.api_port),
        api_only=bool(args.api_only),
    )
