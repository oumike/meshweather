import logging
import threading
from typing import Any, Mapping

import meshtastic.tcp_interface
from pubsub import pub

from .models import WeatherObservation
from .parser import parse_weather_observation
from .storage import SqliteWeatherRepository

logger = logging.getLogger(__name__)


def _get_first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _coerce_name(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _coerce_float(value: Any) -> float | None:
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


class MeshweatherIngestor:
    def __init__(self, host: str, port: int, repository: SqliteWeatherRepository) -> None:
        self.host = host
        self.port = port
        self.repository = repository
        self._stop_event = threading.Event()
        self._interface_lock = threading.Lock()
        self._interface: meshtastic.tcp_interface.TCPInterface | None = None

    def run_forever(self) -> None:
        logger.info("Starting ingestor for %s:%s", self.host, self.port)

        pub.subscribe(self._on_receive, "meshtastic.receive")
        pub.subscribe(self._on_connection_established, "meshtastic.connection.established")
        pub.subscribe(self._on_connection_lost, "meshtastic.connection.lost")

        try:
            interface = meshtastic.tcp_interface.TCPInterface(
                hostname=self.host,
                portNumber=self.port,
            )
            with self._interface_lock:
                self._interface = interface

            while not self._stop_event.wait(1.0):
                pass
        finally:
            self._unsubscribe_handlers()
            self._close_interface()

    def stop(self) -> None:
        self._stop_event.set()
        self._close_interface()

    def _close_interface(self) -> None:
        interface: meshtastic.tcp_interface.TCPInterface | None
        with self._interface_lock:
            interface = self._interface
            self._interface = None

        if interface is not None:
            try:
                interface.close()
            except Exception as exc:  # pragma: no cover
                logger.warning("Error while closing Meshtastic interface: %s", exc)

    def _unsubscribe_handlers(self) -> None:
        for callback, topic in (
            (self._on_receive, "meshtastic.receive"),
            (self._on_connection_established, "meshtastic.connection.established"),
            (self._on_connection_lost, "meshtastic.connection.lost"),
        ):
            try:
                pub.unsubscribe(callback, topic)
            except Exception:
                pass

    def _on_connection_established(self, interface: Any, topic: Any = pub.AUTO_TOPIC) -> None:
        logger.info("Connected to Meshtastic node at %s:%s", self.host, self.port)

    def _on_connection_lost(self, interface: Any) -> None:
        logger.warning("Lost connection to Meshtastic node")

    def _on_receive(self, packet: Mapping[str, Any], interface: Any) -> None:
        observation = parse_weather_observation(packet)
        if observation is None:
            return

        self._enrich_node_names(observation, interface)

        inserted = self.repository.insert_observation(observation, packet)
        source = observation.packet_from_id or observation.packet_from

        if inserted:
            logger.info(
                "Stored weather telemetry from=%s packet_id=%s",
                source,
                observation.packet_id,
            )
        else:
            logger.debug(
                "Skipped duplicate weather telemetry from=%s packet_id=%s",
                source,
                observation.packet_id,
            )

    def _enrich_node_names(
        self, observation: WeatherObservation, interface: Any
    ) -> None:
        if observation.packet_from is None:
            return

        nodes_by_num = getattr(interface, "nodesByNum", None)
        if not isinstance(nodes_by_num, Mapping):
            return

        node = nodes_by_num.get(observation.packet_from)
        if not isinstance(node, Mapping):
            return

        user = node.get("user")
        if not isinstance(user, Mapping):
            return

        if observation.node_long_name is None:
            observation.node_long_name = _coerce_name(
                _get_first(user, "longName", "long_name")
            )

        if observation.node_short_name is None:
            observation.node_short_name = _coerce_name(
                _get_first(user, "shortName", "short_name")
            )

        position = node.get("position")
        if isinstance(position, Mapping):
            if observation.node_latitude is None:
                latitude = _coerce_float(_get_first(position, "latitude", "lat"))
                if latitude is None:
                    latitude_i = _coerce_float(
                        _get_first(position, "latitudeI", "latitude_i")
                    )
                    if latitude_i is not None:
                        latitude = latitude_i * 1e-7
                observation.node_latitude = latitude

            if observation.node_longitude is None:
                longitude = _coerce_float(_get_first(position, "longitude", "lon"))
                if longitude is None:
                    longitude_i = _coerce_float(
                        _get_first(position, "longitudeI", "longitude_i")
                    )
                    if longitude_i is not None:
                        longitude = longitude_i * 1e-7
                observation.node_longitude = longitude
