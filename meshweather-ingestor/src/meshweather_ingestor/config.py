import argparse
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback for environments not yet refreshed
    load_dotenv = None


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestorConfig:
    host: Optional[str]
    port: int
    db_path: Path
    monitored_channel: str
    log_level: str
    api_enabled: bool
    api_host: str
    api_port: int
    api_only: bool


_ENV_LOADED = False


def _load_simple_dotenv(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        name, value = line.split("=", 1)
        name = name.strip()
        if not name:
            continue

        value = value.strip()
        quoted = (
            len(value) >= 2
            and value[0] in {'"', "'"}
            and value[-1] == value[0]
        )
        if quoted:
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()

        os.environ.setdefault(name, value)


def _load_dotenv_candidate(path: Path) -> None:
    if load_dotenv is not None:
        load_dotenv(dotenv_path=path, override=False)
        return

    _load_simple_dotenv(path)
    logger.warning(
        "python-dotenv not installed; using built-in .env parser for %s",
        path,
    )


def _load_env_file() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    env_file = os.getenv("MESHWEATHER_ENV_FILE")
    candidates: list[Path]

    if env_file:
        resolved = Path(env_file).expanduser()
        if not resolved.is_file():
            raise FileNotFoundError(
                f"MESHWEATHER_ENV_FILE points to a missing file: {resolved}"
            )
        candidates = [resolved]
    else:
        candidates = [
            Path.cwd() / ".env",
            Path.cwd() / "meshweather-ingestor" / ".env",
            Path(__file__).resolve().parents[2] / ".env",
        ]

    for candidate in candidates:
        if candidate.is_file():
            _load_dotenv_candidate(candidate)
            _ENV_LOADED = True
            return

    # Final fallback to python-dotenv default search behavior.
    if load_dotenv is not None:
        load_dotenv(override=False)

    _ENV_LOADED = True


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
        help=(
            "Meshtastic node hostname or IP. Can also be set by MESHTASTIC_NODE_IP. "
            "If omitted and API is enabled, runs in API-only mode."
        ),
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
        "--monitored-channel",
        default=os.getenv("MESHWEATHER_MONITORED_CHANNEL", "MetalOnes"),
        help="Meshtastic channel name to monitor for text messages. Default: MetalOnes.",
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
    _load_env_file()
    parser = build_parser()
    args = parser.parse_args(argv)

    host = str(args.host).strip() if args.host else None

    if args.api_only and args.disable_api:
        parser.error("--api-only cannot be combined with --disable-api.")

    if not args.api_only and args.disable_api and host is None:
        parser.error(
            "--disable-api requires --host (or MESHTASTIC_NODE_IP) for ingestion mode."
        )

    # If host is not configured, fall back to API-only mode instead of hard failing.
    api_only = bool(args.api_only or host is None)
    monitored_channel = str(args.monitored_channel).strip() or "MetalOnes"

    log_level = str(args.log_level).upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        parser.error("--log-level must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL.")

    return IngestorConfig(
        host=host,
        port=int(args.port),
        db_path=Path(args.db_path),
        monitored_channel=monitored_channel,
        log_level=log_level,
        api_enabled=not bool(args.disable_api),
        api_host=str(args.api_host),
        api_port=int(args.api_port),
        api_only=api_only,
    )
