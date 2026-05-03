# meshweather

Multi-project workspace for mesh-based weather data systems.

## Structure

- `meshweather-ingestor` - Meshtastic weather telemetry ingestor over TCP/IP into SQLite with a FastAPI HTTP layer.
- `meshweather` - React map dashboard that loads node telemetry from the ingestor API.

Additional projects can be added as top-level sibling folders as the solution grows.

## Development Environment Setup

Prerequisites:

- Python `3.11+`
- Node.js `20+` and npm
- Docker with Compose plugin (optional, for container workflow)

1. Configure ingestor environment values:

```bash
cp meshweather-ingestor/.env.example meshweather-ingestor/.env
```

2. Set up the ingestor Python environment:

```bash
cd meshweather-ingestor
python -m venv .venv
source .venv/bin/activate
pip install -e .
cd ..
```

3. Install frontend dependencies:

```bash
cd meshweather
npm install
cd ..
```

4. Run locally in two terminals:

Terminal 1 (ingestor):

```bash
cd meshweather-ingestor
source .venv/bin/activate
meshweather-ingestor
```

Terminal 2 (frontend):

```bash
cd meshweather
npm run dev
```

5. Open the frontend at `http://localhost:5173`.

During local frontend development, Vite proxies `/api/*` and `/health` to
`http://127.0.0.1:8080` by default.

## Docker Compose

This workspace includes one container for each project and a single compose file at the repo root.

1. Configure ingestor settings in `meshweather-ingestor/.env` (Meshtastic host, ports, log level, etc.).

2. Start both services:

```bash
docker compose up
```

3. Access services:

- Frontend: http://localhost:10090
- Ingestor API: internal-only via frontend reverse proxy (`/api/*`)

Optional environment variables:

- `MESHWEATHER_FRONTEND_PORT` (default `10090`)

The SQLite database is persisted in the named volume `meshweather_data`.

## GitHub Container Registry (GHCR)

This repo includes a GitHub Actions workflow that builds and publishes both container images to GHCR only when a new tag (`v*`) is pushed or a GitHub release is published.

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

## Raspberry Pi 5

Raspberry Pi 5 uses `linux/arm64`. The publish workflow now pushes multi-arch images (`linux/amd64` and `linux/arm64`) so the Pi will pull the correct image automatically.

Steps on Pi:

1. Install Docker + Docker Compose plugin.
2. Clone this repo.
3. Set Meshtastic host in `meshweather-ingestor/.env`.

4. Start services:

```bash
docker compose pull
docker compose up -d
```

5. Open frontend:

- `http://<pi-ip>:10090`
