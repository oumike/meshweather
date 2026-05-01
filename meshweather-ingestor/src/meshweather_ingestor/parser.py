from typing import Any, Mapping, Optional

from .models import WeatherObservation

TELEMETRY_PORTNUM = 67


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _coerce_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _get_first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _is_telemetry_portnum(portnum: Any) -> bool:
    if isinstance(portnum, int):
        return portnum == TELEMETRY_PORTNUM

    if isinstance(portnum, str):
        normalized = portnum.strip().upper()
        if normalized == "TELEMETRY_APP":
            return True
        if normalized.isdigit() and int(normalized) == TELEMETRY_PORTNUM:
            return True

    return False


def parse_weather_observation(packet: Mapping[str, Any]) -> Optional[WeatherObservation]:
    decoded = packet.get("decoded")
    if not isinstance(decoded, Mapping):
        return None

    telemetry = decoded.get("telemetry")
    if not isinstance(telemetry, Mapping):
        return None

    portnum = decoded.get("portnum")
    if portnum is not None and not _is_telemetry_portnum(portnum):
        return None

    environment = _get_first(telemetry, "environmentMetrics", "environment_metrics")
    if not isinstance(environment, Mapping):
        return None

    observation = WeatherObservation(
        packet_from=_coerce_int(packet.get("from")),
        packet_from_id=_get_first(packet, "fromId", "from_id"),
        node_long_name=_coerce_str(
            _get_first(packet, "fromLongName", "from_long_name")
        ),
        node_short_name=_coerce_str(
            _get_first(packet, "fromShortName", "from_short_name")
        ),
        node_latitude=None,
        node_longitude=None,
        packet_id=_coerce_int(packet.get("id")),
        packet_rx_time=_coerce_int(_get_first(packet, "rxTime", "rx_time")),
        telemetry_time=_coerce_int(telemetry.get("time")),
        temperature_c=_coerce_float(environment.get("temperature")),
        relative_humidity=_coerce_float(
            _get_first(environment, "relativeHumidity", "relative_humidity")
        ),
        barometric_pressure_hpa=_coerce_float(
            _get_first(environment, "barometricPressure", "barometric_pressure")
        ),
        wind_direction_deg=_coerce_int(
            _get_first(environment, "windDirection", "wind_direction")
        ),
        wind_speed_m_s=_coerce_float(_get_first(environment, "windSpeed", "wind_speed")),
        wind_gust_m_s=_coerce_float(_get_first(environment, "windGust", "wind_gust")),
        wind_lull_m_s=_coerce_float(_get_first(environment, "windLull", "wind_lull")),
        rainfall_1h_mm=_coerce_float(_get_first(environment, "rainfall1H", "rainfall_1h")),
        rainfall_24h_mm=_coerce_float(
            _get_first(environment, "rainfall24H", "rainfall_24h")
        ),
        lux=_coerce_float(environment.get("lux")),
        uv_lux=_coerce_float(_get_first(environment, "uvLux", "uv_lux")),
    )

    if all(
        value is None
        for value in (
            observation.temperature_c,
            observation.relative_humidity,
            observation.barometric_pressure_hpa,
            observation.wind_direction_deg,
            observation.wind_speed_m_s,
            observation.wind_gust_m_s,
            observation.wind_lull_m_s,
            observation.rainfall_1h_mm,
            observation.rainfall_24h_mm,
            observation.lux,
            observation.uv_lux,
        )
    ):
        return None

    return observation
