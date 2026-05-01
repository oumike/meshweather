from pathlib import Path

from meshweather_ingestor.models import WeatherObservation
from meshweather_ingestor.storage import SqliteWeatherRepository


def test_insert_and_deduplicate(tmp_path: Path) -> None:
    db_path = tmp_path / "meshweather.db"
    repo = SqliteWeatherRepository(db_path)

    observation = WeatherObservation(
        packet_from=100,
        packet_from_id="!00000064",
        node_long_name="Backyard Weather",
        node_short_name="WXBY",
        node_latitude=41.2345,
        node_longitude=-86.1234,
        packet_id=200,
        packet_rx_time=1714577000,
        telemetry_time=1714576999,
        temperature_c=20.5,
        relative_humidity=50.0,
        barometric_pressure_hpa=1009.5,
        wind_direction_deg=225,
        wind_speed_m_s=5.2,
        wind_gust_m_s=8.1,
        wind_lull_m_s=2.1,
        rainfall_1h_mm=0.4,
        rainfall_24h_mm=2.2,
        lux=380.0,
        uv_lux=0.6,
    )

    packet = {
        "from": 100,
        "id": 200,
        "decoded": {
            "portnum": "TELEMETRY_APP",
            "telemetry": {
                "environmentMetrics": {
                    "temperature": 20.5,
                }
            },
        },
    }

    assert repo.insert_observation(observation, packet) is True
    assert repo.insert_observation(observation, packet) is False
    assert repo.count_observations() == 1

    cursor = repo._conn.execute(
        "SELECT node_long_name, node_short_name, node_latitude, node_longitude FROM weather_telemetry LIMIT 1"
    )
    row = cursor.fetchone()
    assert tuple(row) == ("Backyard Weather", "WXBY", 41.2345, -86.1234)

    repo.close()


def test_fetch_latest_nodes_and_history(tmp_path: Path) -> None:
    db_path = tmp_path / "meshweather.db"
    repo = SqliteWeatherRepository(db_path)

    packet = {
        "decoded": {
            "portnum": "TELEMETRY_APP",
            "telemetry": {"environmentMetrics": {"temperature": 20.5}},
        },
    }

    node_a_old = WeatherObservation(
        packet_from=100,
        packet_from_id="!00000064",
        node_long_name="Backyard Weather",
        node_short_name="WXBY",
        node_latitude=41.2345,
        node_longitude=-86.1234,
        packet_id=201,
        packet_rx_time=1714577000,
        telemetry_time=1714576999,
        temperature_c=19.8,
        relative_humidity=49.0,
        barometric_pressure_hpa=1009.0,
        wind_direction_deg=220,
        wind_speed_m_s=4.9,
        wind_gust_m_s=7.5,
        wind_lull_m_s=2.0,
        rainfall_1h_mm=0.2,
        rainfall_24h_mm=1.9,
        lux=300.0,
        uv_lux=0.4,
    )

    node_a_new = WeatherObservation(
        packet_from=100,
        packet_from_id="!00000064",
        node_long_name="Backyard Weather",
        node_short_name="WXBY",
        node_latitude=41.2345,
        node_longitude=-86.1234,
        packet_id=202,
        packet_rx_time=1714578000,
        telemetry_time=1714577999,
        temperature_c=21.1,
        relative_humidity=52.0,
        barometric_pressure_hpa=1010.0,
        wind_direction_deg=230,
        wind_speed_m_s=5.4,
        wind_gust_m_s=8.2,
        wind_lull_m_s=2.4,
        rainfall_1h_mm=0.5,
        rainfall_24h_mm=2.4,
        lux=410.0,
        uv_lux=0.8,
    )

    node_b = WeatherObservation(
        packet_from=222,
        packet_from_id="!000000de",
        node_long_name="Rooftop Station",
        node_short_name="WXRT",
        node_latitude=40.1000,
        node_longitude=-85.8000,
        packet_id=303,
        packet_rx_time=1714578500,
        telemetry_time=1714578499,
        temperature_c=18.3,
        relative_humidity=61.0,
        barometric_pressure_hpa=1006.0,
        wind_direction_deg=180,
        wind_speed_m_s=3.3,
        wind_gust_m_s=5.7,
        wind_lull_m_s=1.2,
        rainfall_1h_mm=1.2,
        rainfall_24h_mm=8.2,
        lux=120.0,
        uv_lux=0.2,
    )

    assert repo.insert_observation(node_a_old, packet)
    assert repo.insert_observation(node_a_new, packet)
    assert repo.insert_observation(node_b, packet)

    latest_nodes = repo.fetch_latest_nodes(limit=10)
    assert len(latest_nodes) == 2

    node_a_summary = next(n for n in latest_nodes if n["node_key"] == "id:!00000064")
    assert node_a_summary["packet_id"] == 202
    assert node_a_summary["temperature_c"] == 21.1

    node_a_history = repo.fetch_node_history("id:!00000064", limit=10)
    assert len(node_a_history) == 2
    assert node_a_history[0]["packet_id"] == 202
    assert node_a_history[1]["packet_id"] == 201

    recent = repo.fetch_recent_observations(limit=2)
    assert len(recent) == 2
    assert recent[0]["packet_id"] == 303

    repo.close()
