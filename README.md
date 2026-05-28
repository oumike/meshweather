# meshweather

Mesh weather ingestion and dashboard workspace.

## Prerequisites

- Docker with Compose plugin
- Python 3.11+
- Node.js 20+

## Run With Containers

1. Create the ingestor environment file:

```bash
cp meshweather-ingestor/.env.example meshweather-ingestor/.env
```

2. Start the stack:

```bash
docker compose up --build
```

To force running from locally built source (without pulling GHCR images), use:

```bash
scripts/start-containers-from-source.sh
```

3. Open the app:

- Frontend: http://localhost:10090

4. Stop the stack:

```bash
docker compose down
```

If you started with local source builds and want a one-command stop + clean:

```bash
scripts/stop-containers-from-source.sh
```

To also remove the persisted compose volume data:

```bash
scripts/stop-containers-from-source.sh --volumes
```

## Local Development Setup

1. Create the ingestor environment file:

```bash
cp meshweather-ingestor/.env.example meshweather-ingestor/.env
```

2. Set up the backend:

```bash
cd meshweather-ingestor
python -m venv .venv
source .venv/bin/activate
pip install -e .
cd ..
```

3. Set up the frontend:

```bash
cd meshweather
npm install
cd ..
```

4. Run the backend (terminal 1):

```bash
cd meshweather-ingestor
source .venv/bin/activate
meshweather-ingestor
```

5. Run the frontend (terminal 2):

```bash
cd meshweather
npm run dev
```

- Frontend URL: http://localhost:5173

During local frontend development, Vite proxies `/api/*` and `/health` to `http://127.0.0.1:8080`.

## Use of AI

Hello!  I've been a developer professionally since about 2001 working on a large list of technologies.  I've created this project in my spare time so I could contribute to my favorite new hobby (mesh networking) and try out coding with an AI partner (Claude, Codex).  Lots of this code has been touched by AI but as I go through the process I'm reviewing the code.  AI is tool, and like any other tool can be used well or used poorly.

This project is a bit more than a proof of concept but not something that has any commercial value.  I'm doing this for fun and to learn.  Feel free to contribute, use or ignore.
