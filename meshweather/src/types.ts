export type NullableNumber = number | null;

export interface WeatherRow {
  id: number;
  ingested_at_utc: string | null;
  packet_from: NullableNumber;
  packet_from_id: string | null;
  node_long_name: string | null;
  node_short_name: string | null;
  node_latitude: NullableNumber;
  node_longitude: NullableNumber;
  packet_id: NullableNumber;
  packet_rx_time: NullableNumber;
  telemetry_time: NullableNumber;
  temperature_c: NullableNumber;
  relative_humidity: NullableNumber;
  barometric_pressure_hpa: NullableNumber;
  wind_direction_deg: NullableNumber;
  wind_speed_m_s: NullableNumber;
  wind_gust_m_s: NullableNumber;
  wind_lull_m_s: NullableNumber;
  rainfall_1h_mm: NullableNumber;
  rainfall_24h_mm: NullableNumber;
  lux: NullableNumber;
  uv_lux: NullableNumber;
  node_key: string;
  node_label: string;
  sort_ts: NullableNumber;
}

export interface ApiNodesResponse {
  count: number;
  nodes: WeatherRow[];
}

export interface ApiObservationsResponse {
  count: number;
  observations: WeatherRow[];
}

export type ApiNodeObservation = WeatherRow;

export interface NodeWeatherSummary {
  node_key: string;
  label: string;
  packet_from_id: string | null;
  packet_from: NullableNumber;
  latitude: number;
  longitude: number;
  latest: ApiNodeObservation;
}

export interface NodeWithoutLocation {
  node_key: string;
  label: string;
  packet_from_id: string | null;
  packet_from: NullableNumber;
  latest: ApiNodeObservation;
}
