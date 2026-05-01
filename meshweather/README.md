# meshweather

React app that visualizes telemetry data exposed by `meshweather-ingestor` HTTP API.

## Current UI

- Map with one pin per node that has coordinates.
- Pin popup with latest ingested weather telemetry.
- Side panel for node list and nodes without coordinates.

## Run

```bash
npm install
npm run dev
```

Then open the local URL shown by Vite (typically `http://localhost:5173`).

## API Configuration

1. Start ingestor API (default `http://127.0.0.1:8080`).
2. Open the app and set `API Base URL` if needed.
3. Click `Refresh` to load latest node summaries.

Optional Vite env var:

- `VITE_MESHWEATHER_API_BASE_URL=http://127.0.0.1:8080`

## Notes

- The map requires `node_latitude` and `node_longitude` values from API node records.
- If a node has telemetry but no coordinates, it appears under `Nodes Without Coordinates`.
