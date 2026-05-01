from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .storage import SqliteWeatherRepository


def create_api_app(repository: SqliteWeatherRepository) -> FastAPI:
    app = FastAPI(
        title="meshweather-ingestor API",
        version="0.1.0",
        description="HTTP API for weather telemetry ingested from Meshtastic.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, int | str]:
        return {
            "status": "ok",
            "observations": repository.count_observations(),
        }

    @app.get("/api/nodes")
    def list_nodes(
        limit: int = Query(default=500, ge=1, le=10000)
    ) -> dict[str, object]:
        nodes = repository.fetch_latest_nodes(limit=limit)
        return {
            "count": len(nodes),
            "nodes": nodes,
        }

    @app.get("/api/observations")
    def list_observations(
        limit: int = Query(default=500, ge=1, le=10000)
    ) -> dict[str, object]:
        observations = repository.fetch_recent_observations(limit=limit)
        return {
            "count": len(observations),
            "observations": observations,
        }

    @app.get("/api/nodes/{node_key}/history")
    def node_history(
        node_key: str,
        limit: int = Query(default=200, ge=1, le=5000),
    ) -> dict[str, object]:
        history = repository.fetch_node_history(node_key=node_key, limit=limit)
        if not history:
            raise HTTPException(status_code=404, detail="Node key not found")

        return {
            "node_key": node_key,
            "count": len(history),
            "history": history,
        }

    return app
