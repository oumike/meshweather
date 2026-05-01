from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class WeatherObservation:
    packet_from: Optional[int]
    packet_from_id: Optional[str]
    node_long_name: Optional[str]
    node_short_name: Optional[str]
    node_latitude: Optional[float]
    node_longitude: Optional[float]
    packet_id: Optional[int]
    packet_rx_time: Optional[int]
    telemetry_time: Optional[int]
    temperature_c: Optional[float]
    relative_humidity: Optional[float]
    barometric_pressure_hpa: Optional[float]
    wind_direction_deg: Optional[int]
    wind_speed_m_s: Optional[float]
    wind_gust_m_s: Optional[float]
    wind_lull_m_s: Optional[float]
    rainfall_1h_mm: Optional[float]
    rainfall_24h_mm: Optional[float]
    lux: Optional[float]
    uv_lux: Optional[float]
