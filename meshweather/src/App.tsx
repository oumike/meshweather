import { useCallback, useEffect, useMemo, useState } from "react";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";

import type {
  ApiNodeObservation,
  ApiNodesResponse,
  ApiObservationsResponse,
  NodeWeatherSummary,
} from "./types";
import "./App.css";

const FALLBACK_CENTER: [number, number] = [39.8283, -98.5795];
const API_NODES_ENDPOINT = "/api/nodes?limit=1000";
const API_OBSERVATIONS_ENDPOINT = "/api/observations?limit=50";
const API_HEALTH_ENDPOINT = "/health";
const AUTO_REFRESH_MS = 30_000;
const LOG_PAGE_SIZE = 10;
type UnitSystem = "metric" | "imperial";
type NodeListSort =
  | "name-asc"
  | "name-desc"
  | "recent-desc"
  | "recent-asc";
const UNIT_SYSTEM_STORAGE_KEY = "meshweather.unitSystem";

function readStoredUnitSystem(): UnitSystem {
  try {
    const stored = window.localStorage.getItem(UNIT_SYSTEM_STORAGE_KEY);
    if (stored === "metric" || stored === "imperial") {
      return stored;
    }
  } catch {
    // Ignore storage access issues and use default.
  }
  return "metric";
}

function isFiniteCoordinate(value: number | null): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function getNodeLabel(row: ApiNodeObservation): string {
  return (
    row.node_label ??
    row.node_long_name ??
    row.node_short_name ??
    row.packet_from_id ??
    (row.packet_from !== null ? `Node ${row.packet_from}` : "Unknown node")
  );
}

function getCompactNodeHeader(row: ApiNodeObservation): string {
  const longName = row.node_long_name?.trim();
  const shortName = row.node_short_name?.trim();

  if (longName && shortName) {
    return `${longName} (${shortName})`;
  }
  if (longName) {
    return longName;
  }
  if (shortName) {
    return shortName;
  }
  return getNodeLabel(row);
}

function rowTimestampMs(row: ApiNodeObservation): number | null {
  if (typeof row.sort_ts === "number") {
    return row.sort_ts * 1000;
  }
  if (row.telemetry_time !== null) {
    return row.telemetry_time * 1000;
  }
  if (row.packet_rx_time !== null) {
    return row.packet_rx_time * 1000;
  }
  if (row.ingested_at_utc) {
    const parsed = Date.parse(row.ingested_at_utc);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return null;
}

function formatTimestamp(row: ApiNodeObservation): string {
  const ts = rowTimestampMs(row);
  if (ts === null) {
    return "n/a";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(ts));
}

function formatValue(value: number | null, unit: string, digits = 1): string {
  if (value === null) {
    return "n/a";
  }
  return `${value.toFixed(digits)} ${unit}`;
}

function celsiusToFahrenheit(value: number): number {
  return value * (9 / 5) + 32;
}

function metersPerSecondToMph(value: number): number {
  return value * 2.2369362921;
}

function hpaToInHg(value: number): number {
  return value * 0.0295299830714;
}

function mmToInches(value: number): number {
  return value / 25.4;
}

function formatTemperature(value: number | null, unitSystem: UnitSystem): string {
  if (value === null) {
    return "n/a";
  }
  if (unitSystem === "imperial") {
    return formatValue(celsiusToFahrenheit(value), "F");
  }
  return formatValue(value, "C");
}

function formatWindSpeed(value: number | null, unitSystem: UnitSystem): string {
  if (value === null) {
    return "n/a";
  }
  if (unitSystem === "imperial") {
    return formatValue(metersPerSecondToMph(value), "mph");
  }
  return formatValue(value, "m/s");
}

function formatPressure(value: number | null, unitSystem: UnitSystem): string {
  if (value === null) {
    return "n/a";
  }
  if (unitSystem === "imperial") {
    return formatValue(hpaToInHg(value), "inHg", 2);
  }
  return formatValue(value, "hPa");
}

function formatRain(value: number | null, unitSystem: UnitSystem): string {
  if (value === null) {
    return "n/a";
  }
  if (unitSystem === "imperial") {
    return formatValue(mmToInches(value), "in", 2);
  }
  return formatValue(value, "mm");
}

function hasEnvironmentTelemetry(row: ApiNodeObservation): boolean {
  return (
    row.temperature_c !== null ||
    row.relative_humidity !== null ||
    row.barometric_pressure_hpa !== null ||
    row.wind_direction_deg !== null ||
    row.wind_speed_m_s !== null ||
    row.wind_gust_m_s !== null ||
    row.wind_lull_m_s !== null ||
    row.rainfall_1h_mm !== null ||
    row.rainfall_24h_mm !== null ||
    row.lux !== null ||
    row.uv_lux !== null
  );
}

function buildTelemetryLines(
  row: ApiNodeObservation,
  unitSystem: UnitSystem,
): string[] {
  const lines: string[] = [];

  if (row.temperature_c !== null) {
    lines.push(`Temp: ${formatTemperature(row.temperature_c, unitSystem)}`);
  }
  if (row.relative_humidity !== null) {
    lines.push(`Humidity: ${formatValue(row.relative_humidity, "%", 0)}`);
  }
  if (row.barometric_pressure_hpa !== null) {
    lines.push(`Pressure: ${formatPressure(row.barometric_pressure_hpa, unitSystem)}`);
  }
  if (row.wind_speed_m_s !== null) {
    lines.push(`Wind: ${formatWindSpeed(row.wind_speed_m_s, unitSystem)}`);
  }
  if (row.rainfall_1h_mm !== null) {
    lines.push(`Rain 1h: ${formatRain(row.rainfall_1h_mm, unitSystem)}`);
  }
  if (row.rainfall_24h_mm !== null) {
    lines.push(`Rain 24h: ${formatRain(row.rainfall_24h_mm, unitSystem)}`);
  }
  if (row.lux !== null) {
    lines.push(`Lux: ${formatValue(row.lux, "lux", 0)}`);
  }
  if (row.uv_lux !== null) {
    lines.push(`UV Lux: ${formatValue(row.uv_lux, "lux", 0)}`);
  }

  return lines;
}

function getTemperatureBandClass(value: number | null): string {
  if (value === null) {
    return "temp-na";
  }
  if (value < 0) {
    return "temp-freezing";
  }
  if (value < 10) {
    return "temp-cold";
  }
  if (value < 22) {
    return "temp-mild";
  }
  if (value < 30) {
    return "temp-warm";
  }
  return "temp-hot";
}

function formatMarkerTemperature(
  value: number | null,
  unitSystem: UnitSystem,
): string {
  if (value === null) {
    return "n/a";
  }
  const display =
    unitSystem === "imperial" ? celsiusToFahrenheit(value) : value;
  return `${Math.round(display)}\u00b0`;
}

function createTemperatureMarkerIcon(
  value: number | null,
  unitSystem: UnitSystem,
): L.DivIcon {
  const tempClass = getTemperatureBandClass(value);
  const label = formatMarkerTemperature(value, unitSystem);

  return L.divIcon({
    className: "temperature-marker-wrap",
    html: `<span class="temperature-marker ${tempClass}">${label}</span>`,
    iconSize: [52, 52],
    iconAnchor: [26, 26],
    popupAnchor: [0, -24],
  });
}

type MapFocusTarget = {
  nodeKey: string;
  center: [number, number];
  requestId: number;
};

function MapFocusController({
  target,
}: {
  target: MapFocusTarget | null;
}): null {
  const map = useMap();

  useEffect(() => {
    if (!target) {
      return;
    }
    const zoomLevel = Math.max(map.getZoom(), 10);
    map.flyTo(target.center, zoomLevel, {
      animate: true,
      duration: 0.6,
    });
  }, [map, target]);

  return null;
}

function buildNodeCollections(rows: ApiNodeObservation[]): NodeWeatherSummary[] {
  const locatedNodes: NodeWeatherSummary[] = [];

  for (const latest of rows) {
    const nodeKey = latest.node_key;
    const label = getNodeLabel(latest);
    const latitude = latest.node_latitude;
    const longitude = latest.node_longitude;
    const hasLocation =
      isFiniteCoordinate(latitude) && isFiniteCoordinate(longitude);

    if (hasLocation) {
      locatedNodes.push({
        node_key: nodeKey,
        label,
        packet_from_id: latest.packet_from_id,
        packet_from: latest.packet_from,
        latitude,
        longitude,
        latest,
      });
    }
  }

  locatedNodes.sort((a, b) => a.label.localeCompare(b.label));
  return locatedNodes;
}

function compareNullableNumber(
  left: number | null,
  right: number | null,
  direction: "asc" | "desc",
): number {
  if (left === null && right === null) {
    return 0;
  }
  if (left === null) {
    return 1;
  }
  if (right === null) {
    return -1;
  }

  if (direction === "asc") {
    return left - right;
  }
  return right - left;
}

function App() {
  const [rows, setRows] = useState<ApiNodeObservation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string>("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const [apiConnected, setApiConnected] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [observationCount, setObservationCount] = useState<number | null>(null);
  const [, setLastObservationCount] = useState<number | null>(null);
  const [unitSystem, setUnitSystem] = useState<UnitSystem>(readStoredUnitSystem);
  const [selectedNodeKey, setSelectedNodeKey] = useState<string | null>(null);
  const [mapFocusTarget, setMapFocusTarget] = useState<MapFocusTarget | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [sortOrder, setSortOrder] = useState<NodeListSort>("name-asc");
  const [isLogModalOpen, setIsLogModalOpen] = useState(false);
  const [isLogLoading, setIsLogLoading] = useState(false);
  const [logError, setLogError] = useState<string>("");
  const [logRows, setLogRows] = useState<ApiNodeObservation[]>([]);
  const [logPage, setLogPage] = useState(0);

  useEffect(() => {
    try {
      window.localStorage.setItem(UNIT_SYSTEM_STORAGE_KEY, unitSystem);
    } catch {
      // Ignore storage access issues.
    }
  }, [unitSystem]);

  useEffect(() => {
    if (!isLogModalOpen) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsLogModalOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isLogModalOpen]);

  const locatedNodes = useMemo(() => buildNodeCollections(rows), [rows]);

  const listedLocatedNodes = useMemo(
    () => locatedNodes.filter((node) => hasEnvironmentTelemetry(node.latest)),
    [locatedNodes],
  );

  const visibleNodeList = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();

    const filtered = normalizedQuery
      ? listedLocatedNodes.filter((node) => {
          const longName = node.latest.node_long_name?.toLowerCase() ?? "";
          const shortName = node.latest.node_short_name?.toLowerCase() ?? "";
          return (
            longName.includes(normalizedQuery) ||
            shortName.includes(normalizedQuery)
          );
        })
      : listedLocatedNodes;

    const sorted = [...filtered];
    sorted.sort((left, right) => {
      switch (sortOrder) {
        case "name-asc":
          return getCompactNodeHeader(left.latest).localeCompare(
            getCompactNodeHeader(right.latest),
          );
        case "name-desc":
          return getCompactNodeHeader(right.latest).localeCompare(
            getCompactNodeHeader(left.latest),
          );
        case "recent-desc":
          return compareNullableNumber(
            rowTimestampMs(left.latest),
            rowTimestampMs(right.latest),
            "desc",
          );
        case "recent-asc":
          return compareNullableNumber(
            rowTimestampMs(left.latest),
            rowTimestampMs(right.latest),
            "asc",
          );
        default:
          return 0;
      }
    });

    return sorted;
  }, [listedLocatedNodes, searchQuery, sortOrder]);

  const logPageCount = useMemo(
    () => Math.max(1, Math.ceil(logRows.length / LOG_PAGE_SIZE)),
    [logRows],
  );

  const visibleLogRows = useMemo(() => {
    const start = logPage * LOG_PAGE_SIZE;
    return logRows.slice(start, start + LOG_PAGE_SIZE);
  }, [logPage, logRows]);

  const mapCenter = useMemo<[number, number]>(() => {
    if (listedLocatedNodes.length === 0) {
      return FALLBACK_CENTER;
    }

    const sum = listedLocatedNodes.reduce(
      (acc, node) => {
        acc.lat += node.latitude;
        acc.lon += node.longitude;
        return acc;
      },
      { lat: 0, lon: 0 },
    );

    return [
      sum.lat / listedLocatedNodes.length,
      sum.lon / listedLocatedNodes.length,
    ];
  }, [listedLocatedNodes]);

  const mapZoom = listedLocatedNodes.length > 0 ? 6 : 4;

  const refreshNodes = useCallback(async () => {
    setIsLoading(true);
    setLoadError("");

    const [nodesResponse, healthResponse] = await Promise.all([
      fetch(API_NODES_ENDPOINT),
      fetch(API_HEALTH_ENDPOINT),
    ]);

    if (!nodesResponse.ok) {
      throw new Error(`Request failed (${nodesResponse.status})`);
    }

    const payload = (await nodesResponse.json()) as ApiNodesResponse;
    if (!Array.isArray(payload.nodes)) {
      throw new Error("API response missing nodes array");
    }

    if (healthResponse.ok) {
      const health = (await healthResponse.json()) as {
        status?: string;
        observations?: number;
      };
      const observations =
        typeof health.observations === "number" ? health.observations : 0;

      setApiConnected(health.status === "ok");
      setObservationCount(observations);
      setLastObservationCount((previous) => {
        setIsIngesting(previous !== null ? observations > previous : observations > 0);
        return observations;
      });
    } else {
      setApiConnected(false);
      setIsIngesting(false);
    }

    setRows(payload.nodes);
    setLastUpdatedAt(Date.now());
    setLoadError("");
    setIsLoading(false);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        await refreshNodes();
      } catch (error) {
        console.error(error);
        setApiConnected(false);
        setIsIngesting(false);
        setLoadError(
          "Could not load nodes from API. Verify meshweather-ingestor is running and API URL is correct.",
        );
        setIsLoading(false);
      }
    })();
  }, [refreshNodes]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      void (async () => {
        try {
          await refreshNodes();
        } catch (error) {
          console.error(error);
          setApiConnected(false);
          setIsIngesting(false);
          setLoadError(
            "Could not refresh nodes from API. Verify meshweather-ingestor API connectivity.",
          );
          setIsLoading(false);
        }
      })();
    }, AUTO_REFRESH_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [refreshNodes]);

  async function onManualRefresh(): Promise<void> {
    try {
      await refreshNodes();
    } catch (error) {
      console.error(error);
      setApiConnected(false);
      setIsIngesting(false);
      setLoadError(
        "Could not refresh nodes from API. Verify meshweather-ingestor API connectivity.",
      );
      setIsLoading(false);
    }
  }

  async function onOpenLogModal(): Promise<void> {
    setIsLogModalOpen(true);
    setIsLogLoading(true);
    setLogError("");
    setLogPage(0);

    try {
      const response = await fetch(API_OBSERVATIONS_ENDPOINT);
      if (!response.ok) {
        throw new Error(`Request failed (${response.status})`);
      }

      const payload = (await response.json()) as ApiObservationsResponse;
      if (!Array.isArray(payload.observations)) {
        throw new Error("API response missing observations array");
      }

      setLogRows(payload.observations);
    } catch (error) {
      console.error(error);
      setLogRows([]);
      setLogError("Could not load the recent ingested messages.");
    } finally {
      setIsLogLoading(false);
    }
  }

  const lastUpdatedLabel = useMemo(() => {
    if (!lastUpdatedAt) {
      return "n/a";
    }
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(lastUpdatedAt));
  }, [lastUpdatedAt]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="title-block">
          <p className="eyebrow">Meshweather Dashboard</p>
          <h1>Node Weather Map</h1>
          <p className="subtitle">
            Live weather map powered by meshweather-ingestor API. Each node appears as a
            pin when coordinates are available.
          </p>
        </div>

        <div className="controls-card">
          <button
            type="button"
            className="refresh-button"
            onClick={() => {
              void onManualRefresh();
            }}
            disabled={isLoading}
          >
            {isLoading ? "Refreshing..." : "Refresh"}
          </button>
          <p className="status">Last update: {lastUpdatedLabel}</p>
          <p className="status">Auto-refresh: every 30 seconds</p>
          <p
            className={`status-pill ${
              !apiConnected ? "is-offline" : isIngesting ? "is-ingesting" : "is-connected"
            }`}
          >
            {!apiConnected
              ? "Ingestor API disconnected"
              : isIngesting
                ? `Connected: ingesting telemetry (${observationCount ?? 0} observations)`
                : `Connected: waiting for new telemetry (${observationCount ?? 0} observations)`}
          </p>

          <div className="unit-toggle" role="group" aria-label="Unit system">
            <button
              type="button"
              className={unitSystem === "metric" ? "is-active" : ""}
              onClick={() => setUnitSystem("metric")}
            >
              Metric
            </button>
            <button
              type="button"
              className={unitSystem === "imperial" ? "is-active" : ""}
              onClick={() => setUnitSystem("imperial")}
            >
              Imperial
            </button>
          </div>

          <div className="stats-row">
            <div>
              <strong>{listedLocatedNodes.length}</strong>
              <span>mapped nodes</span>
            </div>
            <div>
              <strong>{listedLocatedNodes.length}</strong>
              <span>nodes from API</span>
              <button
                type="button"
                className="stats-log-button"
                onClick={() => {
                  void onOpenLogModal();
                }}
              >
                Log
              </button>
            </div>
          </div>

          {isLoading ? <p className="status">Loading node data...</p> : null}
          {loadError ? <p className="error">{loadError}</p> : null}
        </div>
      </header>

      <main className="content-grid">
        <section className="map-panel">
          {listedLocatedNodes.length > 0 ? (
            <MapContainer
              center={mapCenter}
              zoom={mapZoom}
              scrollWheelZoom
              className="weather-map"
            >
              <MapFocusController target={mapFocusTarget} />
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />

              {listedLocatedNodes.map((node) => (
                <Marker
                  key={node.node_key}
                  position={[node.latitude, node.longitude]}
                  icon={createTemperatureMarkerIcon(
                    node.latest.temperature_c,
                    unitSystem,
                  )}
                  title={`${node.label} (${formatTemperature(node.latest.temperature_c, unitSystem)})`}
                >
                  <Popup minWidth={260}>
                    <div className="popup-wrap">
                      <h3>{node.label}</h3>
                      <p className="popup-id">Key: {node.node_key}</p>
                      <p className="popup-id">
                        {node.packet_from_id ??
                          (node.packet_from !== null
                            ? `Node ${node.packet_from}`
                            : "Unknown ID")}
                      </p>
                      <p className="popup-time">Latest: {formatTimestamp(node.latest)}</p>

                      <dl className="telemetry-grid">
                        <div>
                          <dt>Temperature</dt>
                          <dd>{formatTemperature(node.latest.temperature_c, unitSystem)}</dd>
                        </div>
                        <div>
                          <dt>Humidity</dt>
                          <dd>{formatValue(node.latest.relative_humidity, "%", 0)}</dd>
                        </div>
                        <div>
                          <dt>Pressure</dt>
                          <dd>
                            {formatPressure(
                              node.latest.barometric_pressure_hpa,
                              unitSystem,
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt>Wind</dt>
                          <dd>{formatWindSpeed(node.latest.wind_speed_m_s, unitSystem)}</dd>
                        </div>
                        <div>
                          <dt>Rain 1h</dt>
                          <dd>{formatRain(node.latest.rainfall_1h_mm, unitSystem)}</dd>
                        </div>
                        <div>
                          <dt>Rain 24h</dt>
                          <dd>{formatRain(node.latest.rainfall_24h_mm, unitSystem)}</dd>
                        </div>
                      </dl>
                    </div>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>
          ) : (
            <div className="empty-map">
              <h2>No mappable nodes yet</h2>
              <p>
                Waiting for API data with node_latitude and node_longitude values.
              </p>
            </div>
          )}
        </section>

        <aside className="side-panel">
          <h2>Node List</h2>

          <div className="list-controls">
            <label htmlFor="node-search-input">Search Names</label>
            <input
              id="node-search-input"
              type="text"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search long or short name"
            />

            <label htmlFor="node-sort-select">Sort</label>
            <select
              id="node-sort-select"
              value={sortOrder}
              onChange={(event) => setSortOrder(event.target.value as NodeListSort)}
            >
              <option value="name-asc">Name (A-Z)</option>
              <option value="name-desc">Name (Z-A)</option>
              <option value="recent-desc">Latest Update (Newest)</option>
              <option value="recent-asc">Latest Update (Oldest)</option>
            </select>
          </div>

          {listedLocatedNodes.length === 0 ? (
            <p className="empty-list">No telemetry loaded.</p>
          ) : null}

          {listedLocatedNodes.length > 0 && visibleNodeList.length === 0 ? (
            <p className="empty-list">No nodes match the current search.</p>
          ) : null}

          {visibleNodeList.length > 0 ? (
            <ul className="node-list">
              {visibleNodeList.map((node) => (
                <li
                  key={node.node_key}
                  className={
                    selectedNodeKey === node.node_key ? "is-selected" : undefined
                  }
                >
                  <button
                    type="button"
                    className="node-list-button"
                    onClick={() => {
                      setSelectedNodeKey(node.node_key);
                      setMapFocusTarget({
                        nodeKey: node.node_key,
                        center: [node.latitude, node.longitude],
                        requestId: Date.now(),
                      });
                    }}
                  >
                    <strong>{getCompactNodeHeader(node.latest)}</strong>
                    {buildTelemetryLines(node.latest, unitSystem).map((line) => (
                      <span key={`${node.node_key}-${line}`}>{line}</span>
                    ))}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}

        </aside>
      </main>

      {isLogModalOpen ? (
        <div
          className="log-modal-backdrop"
          role="presentation"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setIsLogModalOpen(false);
            }
          }}
        >
          <section
            className="log-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="log-modal-title"
          >
            <header className="log-modal-header">
              <h2 id="log-modal-title">Recent Ingested Messages</h2>
              <button
                type="button"
                className="log-modal-close"
                onClick={() => setIsLogModalOpen(false)}
              >
                Close
              </button>
            </header>

            <div className="log-modal-body">
              {isLogLoading ? <p className="status">Loading logs...</p> : null}
              {!isLogLoading && logError ? <p className="error">{logError}</p> : null}
              {!isLogLoading && !logError && logRows.length === 0 ? (
                <p className="status">No ingested messages found.</p>
              ) : null}

              {!isLogLoading && !logError && visibleLogRows.length > 0 ? (
                <ul className="log-message-list">
                  {visibleLogRows.map((row) => {
                    const telemetryLines = buildTelemetryLines(row, unitSystem);

                    return (
                      <li key={row.id}>
                        <p className="log-message-title">
                          <strong>{getNodeLabel(row)}</strong>
                          <span>{formatTimestamp(row)}</span>
                        </p>
                        <p className="log-message-meta">
                          packet_id={row.packet_id ?? "n/a"} | node_key={row.node_key}
                        </p>
                        <p className="log-message-lines">
                          {telemetryLines.length > 0
                            ? telemetryLines.join(" | ")
                            : "No environment telemetry values in this message."}
                        </p>
                      </li>
                    );
                  })}
                </ul>
              ) : null}
            </div>

            <footer className="log-modal-footer">
              <button
                type="button"
                onClick={() => setLogPage((page) => Math.max(0, page - 1))}
                disabled={isLogLoading || logPage === 0}
              >
                Previous
              </button>
              <p>
                Page {Math.min(logPage + 1, logPageCount)} of {logPageCount}
              </p>
              <button
                type="button"
                onClick={() =>
                  setLogPage((page) => Math.min(logPageCount - 1, page + 1))
                }
                disabled={isLogLoading || logPage >= logPageCount - 1}
              >
                Next
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </div>
  );
}

export default App;
