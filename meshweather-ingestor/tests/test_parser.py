from meshweather_ingestor.parser import parse_weather_observation


def test_parse_weather_observation_camel_case() -> None:
    packet = {
        "from": 123456,
        "fromId": "!001e240",
        "fromLongName": "Rooftop WX Node",
        "fromShortName": "WX01",
        "id": 789,
        "rxTime": 1714575000,
        "decoded": {
            "portnum": "TELEMETRY_APP",
            "telemetry": {
                "time": 1714574999,
                "environmentMetrics": {
                    "temperature": 21.4,
                    "relativeHumidity": 54.0,
                    "barometricPressure": 1008.2,
                    "windSpeed": 4.7,
                    "windDirection": 190,
                    "rainfall1H": 0.8,
                    "rainfall24H": 3.2,
                },
            },
        },
    }

    observation = parse_weather_observation(packet)

    assert observation is not None
    assert observation.packet_from == 123456
    assert observation.packet_id == 789
    assert observation.node_long_name == "Rooftop WX Node"
    assert observation.node_short_name == "WX01"
    assert observation.node_latitude is None
    assert observation.node_longitude is None
    assert observation.temperature_c == 21.4
    assert observation.relative_humidity == 54.0
    assert observation.barometric_pressure_hpa == 1008.2
    assert observation.wind_speed_m_s == 4.7
    assert observation.wind_direction_deg == 190
    assert observation.rainfall_1h_mm == 0.8
    assert observation.rainfall_24h_mm == 3.2


def test_parse_weather_observation_snake_case() -> None:
    packet = {
        "from": 42,
        "id": 99,
        "rx_time": 1714576000,
        "decoded": {
            "portnum": 67,
            "telemetry": {
                "time": 1714575999,
                "environment_metrics": {
                    "temperature": 19.0,
                    "relative_humidity": 61.2,
                    "barometric_pressure": 1012.6,
                    "wind_speed": 2.0,
                    "wind_gust": 3.4,
                    "wind_lull": 0.9,
                    "uv_lux": 0.4,
                },
            },
        },
    }

    observation = parse_weather_observation(packet)

    assert observation is not None
    assert observation.packet_from == 42
    assert observation.packet_id == 99
    assert observation.node_long_name is None
    assert observation.node_short_name is None
    assert observation.node_latitude is None
    assert observation.node_longitude is None
    assert observation.temperature_c == 19.0
    assert observation.relative_humidity == 61.2
    assert observation.wind_gust_m_s == 3.4
    assert observation.wind_lull_m_s == 0.9
    assert observation.uv_lux == 0.4


def test_parse_weather_observation_non_telemetry_is_ignored() -> None:
    packet = {
        "from": 1,
        "id": 2,
        "decoded": {
            "portnum": "TEXT_MESSAGE_APP",
            "telemetry": {
                "environmentMetrics": {
                    "temperature": 25.0,
                }
            },
        },
    }

    observation = parse_weather_observation(packet)

    assert observation is None
