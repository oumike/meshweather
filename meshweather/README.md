# meshweather

React app that visualizes telemetry data exposed by `meshweather-ingestor` HTTP API.

## Current UI

- Map with one pin per node that has coordinates.
- Pin popup with latest ingested weather telemetry.
- Side panel for searchable/sortable node list.

## Run

```bash
npm install
npm run dev
```

Then open the local URL shown by Vite (typically `http://localhost:5173`).

## API Configuration

In containerized deployments, API requests are proxied through the frontend container to `meshweather-ingestor` over the internal Docker network.

The API base URL is not user-editable in the UI.

## Notes

- The map requires `node_latitude` and `node_longitude` values from API node records.
- Nodes without coordinates are not shown in the right-side node list.

## Container

Build and run this project directly:

```bash
docker build -t meshweather-frontend .
docker run --rm -p 10090:80 meshweather-frontend
```

Or run both frontend + ingestor from the workspace root using `docker compose up --build`.
