# meshweather

Multi-project workspace for mesh-based weather data systems.

## Structure

- `meshweather-ingestor` - Meshtastic weather telemetry ingestor over TCP/IP into SQLite with a FastAPI HTTP layer.
- `meshweather` - React map dashboard that loads node telemetry from the ingestor API.

Additional projects can be added as top-level sibling folders as the solution grows.
