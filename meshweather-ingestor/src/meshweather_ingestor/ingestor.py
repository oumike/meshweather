import logging
import threading
from typing import Any, Mapping

import meshtastic.tcp_interface
from pubsub import pub

from .models import WeatherObservation
from .parser import parse_weather_observation
from .storage import SqliteWeatherRepository

logger = logging.getLogger(__name__)

_DEFAULT_MONITORED_CHANNEL_NAME = "MetalOnes"
_TEXT_MESSAGE_PORTNUMS = {1, 7, "TEXT_MESSAGE_APP", "TEXT_MESSAGE_COMPRESSED_APP"}


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


def _coerce_int(value: Any) -> int | None:
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


class MeshweatherIngestor:
    def __init__(
        self,
        host: str,
        port: int,
        repository: SqliteWeatherRepository,
        monitored_channel_name: str = _DEFAULT_MONITORED_CHANNEL_NAME,
    ) -> None:
        self.host = host
        self.port = port
        self.repository = repository
        self.monitored_channel_name = monitored_channel_name
        self._stop_event = threading.Event()
        self._reconnect_event = threading.Event()
        self._interface_lock = threading.Lock()
        self._interface: meshtastic.tcp_interface.TCPInterface | None = None

    def run_forever(self) -> None:
        logger.info("Starting ingestor for %s:%s", self.host, self.port)

        pub.subscribe(self._on_receive, "meshtastic.receive")
        pub.subscribe(self._on_connection_established, "meshtastic.connection.established")
        pub.subscribe(self._on_connection_lost, "meshtastic.connection.lost")

        try:
            while not self._stop_event.is_set():
                self._reconnect_event.clear()

                try:
                    logger.info("Attempting Meshtastic connection to %s:%s", self.host, self.port)
                    interface = meshtastic.tcp_interface.TCPInterface(
                        hostname=self.host,
                        portNumber=self.port,
                    )
                    logger.info(
                        "Meshtastic TCP connection established to %s:%s",
                        self.host,
                        self.port,
                    )
                except Exception as exc:
                    logger.warning(
                        "Meshtastic connect failed (%s). Retrying in 5 seconds.",
                        exc,
                    )
                    if self._stop_event.wait(5.0):
                        break
                    continue

                with self._interface_lock:
                    self._interface = interface

                # Wait until stop is requested or the connection is reported lost.
                while not self._stop_event.is_set() and not self._reconnect_event.wait(1.0):
                    pass

                self._close_interface()

                if self._stop_event.is_set():
                    break

                logger.info("Meshtastic connection lost; reconnecting in 2 seconds.")
                if self._stop_event.wait(2.0):
                    break
        finally:
            self._unsubscribe_handlers()
            self._close_interface()

    def stop(self) -> None:
        self._stop_event.set()
        self._reconnect_event.set()
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
        self._reconnect_event.set()

    def _on_receive(self, packet: Mapping[str, Any], interface: Any) -> None:
        self._report_monitored_channel_message(packet, interface)

        observation = parse_weather_observation(packet)
        if observation is None:
            return

        self._enrich_node_names(observation, interface)

        inserted = self.repository.insert_observation(observation, packet)
        source = observation.packet_from_id or observation.packet_from

        if inserted:
            logger.info(
                "Stored packet from=%s packet_id=%s",
                source,
                observation.packet_id,
            )
        else:
            logger.debug(
                "Skipped duplicate packet from=%s packet_id=%s",
                source,
                observation.packet_id,
            )

    def _report_monitored_channel_message(
        self, packet: Mapping[str, Any], interface: Any
    ) -> None:
        channel_name = self._resolve_channel_name(packet, interface)
        if channel_name != self.monitored_channel_name:
            return

        text = _extract_text_message(packet)
        if text is None:
            return

        logger.info(
            "Channel %s message from %s: %s",
            channel_name,
            self._describe_packet_source(packet, interface),
            text,
        )

    def _resolve_channel_name(self, packet: Mapping[str, Any], interface: Any) -> str | None:
        channel_index = _coerce_int(packet.get("channel"))
        if channel_index is None:
            return None

        local_node = getattr(interface, "localNode", None)
        get_channel = getattr(local_node, "getChannelByChannelIndex", None)
        if not callable(get_channel):
            return None

        try:
            channel = get_channel(channel_index)
        except Exception:
            return None

        if channel is None:
            return None

        settings = getattr(channel, "settings", None)
        if isinstance(settings, Mapping):
            return _coerce_name(settings.get("name"))

        return _coerce_name(getattr(settings, "name", None))

    def _describe_packet_source(self, packet: Mapping[str, Any], interface: Any) -> str:
        source_name = _coerce_name(
            _get_first(
                packet,
                "fromLongName",
                "from_long_name",
                "fromShortName",
                "from_short_name",
                "fromId",
                "from_id",
            )
        )
        if source_name is not None:
            return source_name

        packet_from = _coerce_int(packet.get("from"))
        if packet_from is None:
            return "unknown"

        nodes_by_num = getattr(interface, "nodesByNum", None)
        if isinstance(nodes_by_num, Mapping):
            node = nodes_by_num.get(packet_from)
            if isinstance(node, Mapping):
                user = node.get("user")
                if isinstance(user, Mapping):
                    name = _coerce_name(
                        _get_first(user, "longName", "long_name", "shortName", "short_name")
                    )
                    if name is not None:
                        return name

        return str(packet_from)

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
                        latitude = round(latitude_i * 1e-7, 7)
                observation.node_latitude = latitude

            if observation.node_longitude is None:
                longitude = _coerce_float(_get_first(position, "longitude", "lon"))
                if longitude is None:
                    longitude_i = _coerce_float(
                        _get_first(position, "longitudeI", "longitude_i")
                    )
                    if longitude_i is not None:
                        longitude = round(longitude_i * 1e-7, 7)
                observation.node_longitude = longitude


def _extract_text_message(packet: Mapping[str, Any]) -> str | None:
    decoded = packet.get("decoded")
    if not isinstance(decoded, Mapping):
        return None

    if not _is_text_message_portnum(decoded.get("portnum")):
        return None

    text = _coerce_name(decoded.get("text"))
    if text is not None:
        return text

    payload = decoded.get("payload")
    if isinstance(payload, str):
        return _coerce_name(payload)

    if isinstance(payload, (bytes, bytearray)):
        try:
            return _coerce_name(bytes(payload).decode("utf-8"))
        except UnicodeDecodeError:
            return None

    return None


def _is_text_message_portnum(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().upper() in _TEXT_MESSAGE_PORTNUMS

    portnum = _coerce_int(value)
    return portnum in _TEXT_MESSAGE_PORTNUMS
