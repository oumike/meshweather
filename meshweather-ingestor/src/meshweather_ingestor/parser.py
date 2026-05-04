from typing import Any, Mapping, Optional

from .models import WeatherObservation


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


def parse_weather_observation(packet: Mapping[str, Any]) -> Optional[WeatherObservation]:
    decoded = packet.get("decoded")
    decoded_map: Mapping[str, Any] = decoded if isinstance(decoded, Mapping) else {}

    telemetry = decoded_map.get("telemetry")
    telemetry_map: Mapping[str, Any] = telemetry if isinstance(telemetry, Mapping) else {}

    environment = _get_first(telemetry_map, "environmentMetrics", "environment_metrics")
    environment_map: Mapping[str, Any] = (
        environment if isinstance(environment, Mapping) else {}
    )

    position = decoded_map.get("position")
    position_map: Mapping[str, Any] = position if isinstance(position, Mapping) else {}

    user = decoded_map.get("user")
    user_map: Mapping[str, Any] = user if isinstance(user, Mapping) else {}

    latitude = _coerce_float(_get_first(position_map, "latitude", "lat"))
    if latitude is None:
        # Meshtastic position packets often use scaled int coordinates (1e-7 degrees).
        latitude_i = _coerce_float(_get_first(position_map, "latitudeI", "latitude_i"))
        if latitude_i is not None:
            latitude = round(latitude_i * 1e-7, 7)

    longitude = _coerce_float(_get_first(position_map, "longitude", "lon"))
    if longitude is None:
        longitude_i = _coerce_float(
            _get_first(position_map, "longitudeI", "longitude_i")
        )
        if longitude_i is not None:
            longitude = round(longitude_i * 1e-7, 7)

    observation = WeatherObservation(
        packet_from=_coerce_int(packet.get("from")),
        packet_from_id=_coerce_str(_get_first(packet, "fromId", "from_id")),
        node_long_name=_coerce_str(
            _get_first(
                packet,
                "fromLongName",
                "from_long_name",
            )
            or _get_first(user_map, "longName", "long_name")
        ),
        node_short_name=_coerce_str(
            _get_first(
                packet,
                "fromShortName",
                "from_short_name",
            )
            or _get_first(user_map, "shortName", "short_name")
        ),
        node_latitude=latitude,
        node_longitude=longitude,
        packet_id=_coerce_int(packet.get("id")),
        packet_rx_time=_coerce_int(_get_first(packet, "rxTime", "rx_time")),
        telemetry_time=_coerce_int(telemetry_map.get("time")),
        temperature_c=_coerce_float(environment_map.get("temperature")),
        relative_humidity=_coerce_float(
            _get_first(environment_map, "relativeHumidity", "relative_humidity")
        ),
        barometric_pressure_hpa=_coerce_float(
            _get_first(environment_map, "barometricPressure", "barometric_pressure")
        ),
        wind_direction_deg=_coerce_int(
            _get_first(environment_map, "windDirection", "wind_direction")
        ),
        wind_speed_m_s=_coerce_float(
            _get_first(environment_map, "windSpeed", "wind_speed")
        ),
        wind_gust_m_s=_coerce_float(
            _get_first(environment_map, "windGust", "wind_gust")
        ),
        wind_lull_m_s=_coerce_float(
            _get_first(environment_map, "windLull", "wind_lull")
        ),
        rainfall_1h_mm=_coerce_float(
            _get_first(environment_map, "rainfall1H", "rainfall_1h")
        ),
        rainfall_24h_mm=_coerce_float(
            _get_first(environment_map, "rainfall24H", "rainfall_24h")
        ),
        lux=_coerce_float(environment_map.get("lux")),
        uv_lux=_coerce_float(_get_first(environment_map, "uvLux", "uv_lux")),
    )

    has_identity_or_location = any(
        value is not None
        for value in (
            observation.packet_from,
            observation.packet_from_id,
            observation.node_long_name,
            observation.node_short_name,
            observation.node_latitude,
            observation.node_longitude,
            observation.packet_id,
        )
    )

    has_weather = any(
        value is not None
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
    )

    if not has_identity_or_location and not has_weather:
        # Ignore packets that contain neither useful node identity/location nor weather values.
        return None

    return observation
