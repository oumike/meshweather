# meshweather

Multi-project workspace for mesh-based weather data systems.

## Structure

- `meshweather-ingestor` - Meshtastic weather telemetry ingestor over TCP/IP into SQLite with a FastAPI HTTP layer.
- `meshweather` - React map dashboard that loads node telemetry from the ingestor API.

Additional projects can be added as top-level sibling folders as the solution grows.

## Docker Compose

This workspace includes one container for each project and a single compose file at the repo root.

1. Set Meshtastic host (required for ingestion mode):

```bash
export MESHWEATHER_HOST=192.168.1.50
```

2. Build and start both services:

```bash
docker compose up --build
```

3. Access services:

- Frontend: http://localhost:9090
- Ingestor API: http://localhost:18080

Optional environment variables:

- `MESHWEATHER_PORT` (default `4403`)
- `MESHWEATHER_LOG_LEVEL` (default `INFO`)
- `VITE_MESHWEATHER_API_BASE_URL` (frontend build-time API URL, default `http://127.0.0.1:18080`)

The SQLite database is persisted in the named volume `meshweather_data`.

## GitHub Container Registry (GHCR)

This repo includes a GitHub Actions workflow that builds and publishes both container images to GHCR on pushes to `main`, tags (`v*`), and manual dispatch.

Workflow file:

- `.github/workflows/publish-images.yml`

Published image names:

- `ghcr.io/<your-github-username>/meshweather-ingestor`
- `ghcr.io/<your-github-username>/meshweather-frontend`

Pull latest images:

```bash
docker pull ghcr.io/oumike/meshweather-ingestor:latest
docker pull ghcr.io/oumike/meshweather-frontend:latest
```

If packages are private, authenticate first:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u oumike --password-stdin
```
