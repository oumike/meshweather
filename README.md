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

3. Open the app:

- Frontend: http://localhost:10090

4. Stop the stack:

```bash
docker compose down
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
