# meshweather-ingestor

Meshtastic weather telemetry ingestor that connects to a mesh node via TCP/IP and stores weather-focused telemetry in SQLite.

## Features

- Connects to Meshtastic node via host/IP and TCP port (default `4403`).
- Subscribes to packet stream using Meshtastic Python pubsub topics.
- Extracts weather/environment telemetry fields.
- Captures node identity with packet sender ID plus node short/long names when available.
- Captures node latitude/longitude from Meshtastic node state when available for map visualization.
- Persists parsed telemetry to SQLite.
- Uses dedup for packet identity using `from:id` (`packet_from` + `packet_id`) when packet IDs are present.
- Keeps full raw packet JSON for future reprocessing/migration (for example MongoDB).
- Exposes an HTTP API so frontend clients do not depend on database details.

## Quick Start

1. Create and activate a virtual environment.
2. Install package in editable mode.
3. Run ingestor.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
meshweather-ingestor --host 192.168.1.50
```

By default this runs both ingestion and the API.
API default address: `http://127.0.0.1:8080`.

## API Endpoints

- `GET /health`
- `GET /api/nodes?limit=500` (latest weather sample per node)
- `GET /api/observations?limit=500` (recent raw observations)
- `GET /api/nodes/{node_key}/history?limit=200`

Node keys are API-stable IDs, for example:

- `id:!001e240`
- `num:123456`

## Configuration

CLI options:

- `--host` Meshtastic node hostname or IP (required if env var not set)
- `--port` TCP port, default `4403`
- `--db-path` SQLite file path, default `data/meshweather.db`
- `--log-level` `DEBUG|INFO|WARNING|ERROR`, default `INFO`
- `--api-host` API bind host, default `127.0.0.1`
- `--api-port` API bind port, default `8080`
- `--disable-api` run ingestion without API
- `--api-only` run API without Meshtastic TCP connection (serve existing DB only)

Environment variables (optional):

- `MESHWEATHER_HOST`
- `MESHWEATHER_PORT`
- `MESHWEATHER_DB_PATH`
- `MESHWEATHER_LOG_LEVEL`
- `MESHWEATHER_API_ENABLED`
- `MESHWEATHER_API_HOST`
- `MESHWEATHER_API_PORT`

## Notes

- This project is intentionally SQLite-first for local simplicity.
- Storage is isolated in a repository class to make future MongoDB migration straightforward.

## Container

Build and run this project directly:

```bash
docker build -t meshweather-ingestor .
docker run --rm -p 18080:8080 \
	-e MESHWEATHER_HOST=192.168.1.50 \
	-e MESHWEATHER_API_HOST=0.0.0.0 \
	-v meshweather_data:/app/data \
	meshweather-ingestor
```

Or run both frontend + ingestor from the workspace root using `docker compose up --build`.
