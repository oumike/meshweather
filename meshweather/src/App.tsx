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
type ThemePreference = "light" | "dark" | "auto";
type ResolvedTheme = "light" | "dark";
type NodeListSort =
  | "name-asc"
  | "name-desc"
  | "recent-desc"
  | "recent-asc";
const UNIT_SYSTEM_STORAGE_KEY = "meshweather.unitSystem";
const THEME_PREFERENCE_STORAGE_KEY = "meshweather.themePreference";
const MAP_TILE_LIGHT_URL =
  "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
const MAP_TILE_DARK_URL =
  "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const MAP_TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';
const MAP_TILE_SUBDOMAINS = "abcd";

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

function readStoredThemePreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_PREFERENCE_STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "auto") {
      return stored;
    }
  } catch {
    // Ignore storage access issues and use default.
  }
  return "auto";
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
  const [lastRefreshedAt, setLastRefreshedAt] = useState<number | null>(null);
  const [apiConnected, setApiConnected] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [observationCount, setObservationCount] = useState<number | null>(null);
  const [, setLastObservationCount] = useState<number | null>(null);
  const [unitSystem, setUnitSystem] = useState<UnitSystem>(readStoredUnitSystem);
  const [themePreference, setThemePreference] = useState<ThemePreference>(
    readStoredThemePreference,
  );
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => {
    if (typeof window !== "undefined") {
      return window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }
    return "light";
  });
  const [selectedNodeKey, setSelectedNodeKey] = useState<string | null>(null);
  const [mapFocusTarget, setMapFocusTarget] = useState<MapFocusTarget | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [sortOrder, setSortOrder] = useState<NodeListSort>("name-asc");
  const [showTelemetryOnly, setShowTelemetryOnly] = useState(false);
  const [isAutoRefreshEnabled, setIsAutoRefreshEnabled] = useState(true);
  const [isNodesModalOpen, setIsNodesModalOpen] = useState(false);
  const [isLogModalOpen, setIsLogModalOpen] = useState(false);
  const [isLogLoading, setIsLogLoading] = useState(false);
  const [logError, setLogError] = useState<string>("");
  const [logRows, setLogRows] = useState<ApiNodeObservation[]>([]);
  const [showLogTelemetryOnly, setShowLogTelemetryOnly] = useState(false);
  const [logPage, setLogPage] = useState(0);

  useEffect(() => {
    try {
      window.localStorage.setItem(UNIT_SYSTEM_STORAGE_KEY, unitSystem);
    } catch {
      // Ignore storage access issues.
    }
  }, [unitSystem]);

  useEffect(() => {
    const root = document.documentElement;
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");

    const applyTheme = () => {
      const nextResolvedTheme: ResolvedTheme =
        themePreference === "auto"
          ? mediaQuery.matches
            ? "dark"
            : "light"
          : themePreference;

      root.setAttribute("data-theme-preference", themePreference);
      root.setAttribute("data-theme-resolved", nextResolvedTheme);
      setResolvedTheme(nextResolvedTheme);
    };

    applyTheme();

    try {
      window.localStorage.setItem(THEME_PREFERENCE_STORAGE_KEY, themePreference);
    } catch {
      // Ignore storage access issues.
    }

    const onMediaChange = () => {
      applyTheme();
    };

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", onMediaChange);
      return () => {
        mediaQuery.removeEventListener("change", onMediaChange);
      };
    }

    mediaQuery.addListener(onMediaChange);
    return () => {
      mediaQuery.removeListener(onMediaChange);
    };
  }, [themePreference]);

  useEffect(() => {
    if (!isLogModalOpen && !isNodesModalOpen) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsLogModalOpen(false);
        setIsNodesModalOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isLogModalOpen, isNodesModalOpen]);

  const discoveredNodes = useMemo(() => {
    const sorted = [...rows];
    sorted.sort((left, right) => getNodeLabel(left).localeCompare(getNodeLabel(right)));
    return sorted;
  }, [rows]);

  const mapNodes = useMemo(
    () =>
      buildNodeCollections(
        discoveredNodes.filter((node) => hasEnvironmentTelemetry(node)),
      ),
    [discoveredNodes],
  );

  const visibleNodeList = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();

    const telemetryScoped = showTelemetryOnly
      ? discoveredNodes.filter((node) => hasEnvironmentTelemetry(node))
      : discoveredNodes;

    const filtered = normalizedQuery
      ? telemetryScoped.filter((node) => {
          const longName = node.node_long_name?.toLowerCase() ?? "";
          const shortName = node.node_short_name?.toLowerCase() ?? "";
          const label = getNodeLabel(node).toLowerCase();
          const packetFromId = node.packet_from_id?.toLowerCase() ?? "";
          return (
            label.includes(normalizedQuery) ||
            longName.includes(normalizedQuery) ||
            shortName.includes(normalizedQuery) ||
            packetFromId.includes(normalizedQuery)
          );
        })
      : telemetryScoped;

    const sorted = [...filtered];
    sorted.sort((left, right) => {
      const leftHasTelemetry = hasEnvironmentTelemetry(left);
      const rightHasTelemetry = hasEnvironmentTelemetry(right);
      if (leftHasTelemetry !== rightHasTelemetry) {
        return leftHasTelemetry ? -1 : 1;
      }

      switch (sortOrder) {
        case "name-asc":
          return getCompactNodeHeader(left).localeCompare(
            getCompactNodeHeader(right),
          );
        case "name-desc":
          return getCompactNodeHeader(right).localeCompare(
            getCompactNodeHeader(left),
          );
        case "recent-desc":
          return compareNullableNumber(
            rowTimestampMs(left),
            rowTimestampMs(right),
            "desc",
          );
        case "recent-asc":
          return compareNullableNumber(
            rowTimestampMs(left),
            rowTimestampMs(right),
            "asc",
          );
        default:
          return 0;
      }
    });

    return sorted;
  }, [discoveredNodes, searchQuery, showTelemetryOnly, sortOrder]);

  const filteredLogRows = useMemo(
    () =>
      showLogTelemetryOnly
        ? logRows.filter((row) => hasEnvironmentTelemetry(row))
        : logRows,
    [logRows, showLogTelemetryOnly],
  );

  const logPageCount = useMemo(
    () => Math.max(1, Math.ceil(filteredLogRows.length / LOG_PAGE_SIZE)),
    [filteredLogRows],
  );

  const effectiveLogPage = Math.min(logPage, Math.max(0, logPageCount - 1));

  const visibleLogRows = useMemo(() => {
    const start = effectiveLogPage * LOG_PAGE_SIZE;
    return filteredLogRows.slice(start, start + LOG_PAGE_SIZE);
  }, [effectiveLogPage, filteredLogRows]);

  const mapCenter = useMemo<[number, number]>(() => {
    if (mapNodes.length === 0) {
      return FALLBACK_CENTER;
    }

    const sum = mapNodes.reduce(
      (acc, node) => {
        acc.lat += node.latitude;
        acc.lon += node.longitude;
        return acc;
      },
      { lat: 0, lon: 0 },
    );

    return [
      sum.lat / mapNodes.length,
      sum.lon / mapNodes.length,
    ];
  }, [mapNodes]);

  const mapZoom = mapNodes.length > 0 ? 6 : 4;

  const mapTileUrl =
    resolvedTheme === "dark" ? MAP_TILE_DARK_URL : MAP_TILE_LIGHT_URL;

  const lastRefreshHint = useMemo(() => {
    if (!lastRefreshedAt) {
      return "Last refreshed: n/a";
    }

    return `Last refreshed: ${new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "medium",
    }).format(new Date(lastRefreshedAt))}`;
  }, [lastRefreshedAt]);

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
    setLastRefreshedAt(Date.now());
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
    if (!isAutoRefreshEnabled) {
      return;
    }

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
  }, [refreshNodes, isAutoRefreshEnabled]);

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
    setIsNodesModalOpen(false);
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

  function onOpenNodesModal(): void {
    setIsLogModalOpen(false);
    setIsNodesModalOpen(true);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="title-block">
          <div className="title-headline">
            <h2>Mesh Weather Dashboard</h2>
          </div>
          <p className="subtitle">
            Live weather map powered by meshweather-ingestor API. Each node appears as a
            pin when coordinates are available.
          </p>
          <div className="camellia-drawing">
            <img
              className="camellia-logo"
              src="/camellia-logo.svg"
              alt="Mesh Weather camellia logo"
            />
            <div className="title-switchers">
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

              <div className="theme-toggle" role="group" aria-label="Theme mode">
                <button
                  type="button"
                  className={themePreference === "dark" ? "is-active" : ""}
                  onClick={() => setThemePreference("dark")}
                >
                  Dark
                </button>
                <button
                  type="button"
                  className={themePreference === "light" ? "is-active" : ""}
                  onClick={() => setThemePreference("light")}
                >
                  Light
                </button>
                <button
                  type="button"
                  className={themePreference === "auto" ? "is-active" : ""}
                  onClick={() => setThemePreference("auto")}
                >
                  Auto
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="controls-card">
          <div className="stats-info-top">
            <div className="stats-info-main">
              <strong>{discoveredNodes.length}</strong>
              <span>discovered nodes</span>
            </div>
            <div className="stats-action-buttons">
              <button
                type="button"
                className="stats-log-button"
                onClick={() => {
                  void onOpenLogModal();
                }}
              >
                Log
              </button>
              <button
                type="button"
                className="stats-log-button"
                onClick={onOpenNodesModal}
              >
                Nodes
              </button>
            </div>
          </div>
          <p
            className={`status-pill ${
              !apiConnected
                ? "is-offline"
                : isIngesting
                  ? "is-ingesting"
                  : "is-connected"
            }`}
          >
            {!apiConnected
              ? "Ingestor API disconnected"
              : isIngesting
                ? `Connected: ingesting telemetry (${observationCount ?? 0} observations)`
                : `Connected: waiting for new telemetry (${observationCount ?? 0} observations)`}
          </p>

          {isLoading ? <p className="status">Loading node data...</p> : null}
          {loadError ? <p className="error">{loadError}</p> : null}

          <div className="stats-controls-row">
            <button
              type="button"
              className="refresh-button"
              title={lastRefreshHint}
              onClick={() => {
                void onManualRefresh();
              }}
              disabled={isLoading}
            >
              {isLoading ? "Refreshing..." : "Refresh"}
            </button>
            <label
              className="status auto-refresh-toggle stats-auto-refresh"
              htmlFor="auto-refresh-toggle"
            >
              <input
                id="auto-refresh-toggle"
                type="checkbox"
                checked={isAutoRefreshEnabled}
                onChange={(event) => setIsAutoRefreshEnabled(event.target.checked)}
              />
              Auto-refresh: every 30 seconds
            </label>
          </div>
        </div>
      </header>

      <main className="content-grid">
        <section className="map-panel">
          {mapNodes.length > 0 ? (
            <MapContainer
              center={mapCenter}
              zoom={mapZoom}
              scrollWheelZoom
              className="weather-map"
            >
              <MapFocusController target={mapFocusTarget} />
              <TileLayer
                key={`tiles-${resolvedTheme}`}
                attribution={MAP_TILE_ATTRIBUTION}
                subdomains={MAP_TILE_SUBDOMAINS}
                url={mapTileUrl}
              />

              {mapNodes.map((node) => (
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
      </main>

      {isNodesModalOpen ? (
        <div
          className="nodes-modal-backdrop"
          role="presentation"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setIsNodesModalOpen(false);
            }
          }}
        >
          <section
            className="nodes-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="nodes-modal-title"
          >
            <header className="nodes-modal-header">
              <h2 id="nodes-modal-title">Node List</h2>
              <button
                type="button"
                className="nodes-modal-close"
                onClick={() => setIsNodesModalOpen(false)}
              >
                Close
              </button>
            </header>

            <div className="nodes-modal-body">
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

                <label className="list-controls-checkbox" htmlFor="node-telemetry-only">
                  <input
                    id="node-telemetry-only"
                    type="checkbox"
                    checked={showTelemetryOnly}
                    onChange={(event) => setShowTelemetryOnly(event.target.checked)}
                  />
                  Show only nodes with environment telemetry
                </label>
              </div>

              {discoveredNodes.length === 0 ? (
                <p className="empty-list">No discovered nodes yet.</p>
              ) : null}

              {discoveredNodes.length > 0 && visibleNodeList.length === 0 ? (
                <p className="empty-list">
                  {showTelemetryOnly
                    ? "No telemetry nodes match the current search."
                    : "No nodes match the current search."}
                </p>
              ) : null}

              {visibleNodeList.length > 0 ? (
                <ul className="node-list">
                  {visibleNodeList.map((node) => {
                    const hasTelemetry = hasEnvironmentTelemetry(node);
                    const telemetryLines = buildTelemetryLines(node, unitSystem);
                    const itemClassName = [
                      hasTelemetry ? "has-telemetry" : "",
                      selectedNodeKey === node.node_key ? "is-selected" : "",
                    ]
                      .filter(Boolean)
                      .join(" ");

                    return (
                      <li
                        key={node.node_key}
                        className={itemClassName || undefined}
                      >
                        <button
                          type="button"
                          className="node-list-button"
                          onClick={() => {
                            setSelectedNodeKey(node.node_key);
                            if (
                              isFiniteCoordinate(node.node_latitude) &&
                              isFiniteCoordinate(node.node_longitude)
                            ) {
                              setMapFocusTarget({
                                nodeKey: node.node_key,
                                center: [node.node_latitude, node.node_longitude],
                                requestId: Date.now(),
                              });
                            }
                            setIsNodesModalOpen(false);
                          }}
                        >
                          <strong>{getCompactNodeHeader(node)}</strong>
                          {telemetryLines.map((line) => (
                            <span key={`${node.node_key}-${line}`}>{line}</span>
                          ))}
                          {telemetryLines.length === 0 ? (
                            <span>No environment telemetry yet.</span>
                          ) : null}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}

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
              <div className="log-filters">
                <label className="log-filter-checkbox" htmlFor="log-telemetry-only">
                  <input
                    id="log-telemetry-only"
                    type="checkbox"
                    checked={showLogTelemetryOnly}
                    onChange={(event) =>
                      setShowLogTelemetryOnly(event.target.checked)
                    }
                  />
                  Show only messages with environment telemetry
                </label>
              </div>

              {isLogLoading ? <p className="status">Loading logs...</p> : null}
              {!isLogLoading && logError ? <p className="error">{logError}</p> : null}
              {!isLogLoading && !logError && logRows.length === 0 ? (
                <p className="status">No ingested messages found.</p>
              ) : null}

              {!isLogLoading &&
              !logError &&
              logRows.length > 0 &&
              filteredLogRows.length === 0 ? (
                <p className="status">
                  No ingested messages with environment telemetry found.
                </p>
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
                onClick={() => setLogPage(Math.max(0, effectiveLogPage - 1))}
                disabled={isLogLoading || effectiveLogPage === 0}
              >
                Previous
              </button>
              <p>
                Page {Math.min(effectiveLogPage + 1, logPageCount)} of {logPageCount}
              </p>
              <button
                type="button"
                onClick={() =>
                  setLogPage(Math.min(logPageCount - 1, effectiveLogPage + 1))
                }
                disabled={isLogLoading || effectiveLogPage >= logPageCount - 1}
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
