import logging
import signal
import threading
from types import FrameType
from typing import Optional, Sequence

import uvicorn

from .api import create_api_app
from .config import load_config
from .ingestor import MeshweatherIngestor
from .storage import SqliteWeatherRepository

logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    config = load_config(argv)
    _configure_logging(config.log_level)

    repository = SqliteWeatherRepository(config.db_path)

    ingestor: MeshweatherIngestor | None = None
    ingestor_thread: threading.Thread | None = None

    if not config.api_only:
        if config.host is None:
            raise RuntimeError("host must be set when not using --api-only")
        ingestor = MeshweatherIngestor(
            host=config.host,
            port=config.port,
            repository=repository,
        )

    try:
        if config.api_enabled:
            if ingestor is not None:
                ingestor_thread = threading.Thread(
                    target=ingestor.run_forever,
                    daemon=True,
                    name="meshweather-ingestor",
                )
                ingestor_thread.start()

            app = create_api_app(repository)
            logger.info("Starting API on http://%s:%s", config.api_host, config.api_port)
            if config.api_only:
                if config.host is None:
                    logger.info(
                        "Running in API-only mode: Meshtastic host is not configured "
                        "(set MESHTASTIC_NODE_IP or use --host)."
                    )
                else:
                    logger.info("Running in API-only mode (no Meshtastic TCP connection)")

            server = uvicorn.Server(
                uvicorn.Config(
                    app,
                    host=config.api_host,
                    port=config.api_port,
                    log_level=config.log_level.lower(),
                )
            )
            server.run()
        else:
            if ingestor is None:
                logger.error("Nothing to run: API disabled and --api-only enabled.")
                return 2

            def _handle_signal(signum: int, frame: Optional[FrameType]) -> None:
                signal_name = signal.Signals(signum).name
                logger.info("Received %s, stopping ingestor", signal_name)
                ingestor.stop()

            signal.signal(signal.SIGINT, _handle_signal)
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, _handle_signal)

            ingestor.run_forever()
    finally:
        if ingestor is not None:
            ingestor.stop()
        if ingestor_thread is not None:
            ingestor_thread.join(timeout=5)
        repository.close()

    logger.info("meshweather-ingestor stopped")
    return 0
