"""WS-Discovery (ONVIF) responder on UDP 3702."""

from __future__ import annotations

import asyncio
import logging
import re
import socket
import struct
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from src.camera_activity import CameraActivityTracker
    from src.config import AppConfig, CameraConfig

logger = logging.getLogger(__name__)

PROBE_ACTION_MARKERS = (
    "http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe",
    "discovery/Probe",
)


@dataclass
class DiscoveryDebug:
    probes_received: int = 0
    responses_sent: int = 0
    last_peer: str | None = None
    last_message_id: str | None = None
    last_error: str | None = None


@dataclass
class DiscoveryRuntime:
    onvif_device_xaddr: Callable[[CameraConfig], str]
    advertised_name: Callable[[CameraConfig], str]
    debug: DiscoveryDebug = field(default_factory=DiscoveryDebug)


def _extract_message_id(xml: str) -> str | None:
    m = re.search(r"<\s*(?:[\w.]*:)?MessageID[^>]*>\s*([^<]+?)\s*<", xml, re.I)
    if m:
        return m.group(1).strip()
    return None


def _looks_like_probe(xml: str) -> bool:
    low = xml.lower()
    if "probe" not in low:
        return False
    if any(m.lower() in low for m in PROBE_ACTION_MARKERS):
        return True
    if "discovery:probe" in low or "d:probe" in low:
        return True
    return "<probe>" in low or ":probe>" in low


def _endpoint_uuid(cam: CameraConfig) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"hikifi:{cam.id}:{cam.serial}"))


def build_probe_match_xml(
    relates_to: str,
    endpoint_address: str,
    xaddr: str,
    scopes_name: str,
) -> str:
    msg_id = f"uuid:{uuid.uuid4()}"
    safe_name = scopes_name.replace(" ", "%20")
    scopes = (
        "onvif://www.onvif.org/type/video_encoder "
        "onvif://www.onvif.org/Profile/Streaming "
        f"onvif://www.onvif.org/name/{safe_name}"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
        'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
        'xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
        "<env:Header>"
        f"<wsa:MessageID>{msg_id}</wsa:MessageID>"
        f"<wsa:RelatesTo>{relates_to}</wsa:RelatesTo>"
        "<wsa:To>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:To>"
        "<wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</wsa:Action>"
        "</env:Header>"
        "<env:Body>"
        "<d:ProbeMatches>"
        "<d:ProbeMatch>"
        "<wsa:EndpointReference>"
        f"<wsa:Address>urn:uuid:{endpoint_address}</wsa:Address>"
        "</wsa:EndpointReference>"
        "<d:Types>dn:NetworkVideoTransmitter</d:Types>"
        f"<d:Scopes>{scopes}</d:Scopes>"
        f"<d:XAddrs>{xaddr}</d:XAddrs>"
        "<d:MetadataVersion>1</d:MetadataVersion>"
        "</d:ProbeMatch>"
        "</d:ProbeMatches>"
        "</env:Body>"
        "</env:Envelope>"
    )


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        cfg: AppConfig,
        runtime: DiscoveryRuntime,
        cameras: list[CameraConfig],
        activity: CameraActivityTracker | None,
    ) -> None:
        self._cfg = cfg
        self._runtime = runtime
        self._cameras = cameras
        self._activity = activity
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if not self._cfg.server.discovery_enabled:
            return
        text = data.decode("utf-8", errors="replace")
        if not _looks_like_probe(text):
            return
        self._runtime.debug.probes_received += 1
        self._runtime.debug.last_peer = f"{addr[0]}:{addr[1]}"
        mid = _extract_message_id(text)
        self._runtime.debug.last_message_id = mid
        if not mid:
            self._runtime.debug.last_error = "missing MessageID in probe"
            logger.warning(
                "WS-Discovery probe from %s:%s missing MessageID; ignoring",
                addr[0],
                addr[1],
            )
            return
        self._runtime.debug.last_error = None
        tr = self.transport
        if tr is None:
            return
        summary_bits: list[str] = []
        for cam in self._cameras:
            xaddr = self._runtime.onvif_device_xaddr(cam)
            ep = _endpoint_uuid(cam)
            name = self._runtime.advertised_name(cam)
            xml = build_probe_match_xml(mid, ep, xaddr, name)
            tr.sendto(xml.encode("utf-8"), addr)
            self._runtime.debug.responses_sent += 1
            if self._activity is not None:
                self._activity.record_discovery_announce(cam.id, addr[0])
            summary_bits.append(f"{cam.id} -> {xaddr}")
            logger.debug("WS-Discovery ProbeMatch xml for %s", cam.id)
        logger.info(
            "WS-Discovery probe from %s:%s — advertised %d virtual endpoint(s): %s",
            addr[0],
            addr[1],
            len(summary_bits),
            "; ".join(summary_bits),
        )


async def start_discovery(
    cfg: AppConfig,
    runtime: DiscoveryRuntime,
    cameras: list[CameraConfig],
    activity: CameraActivityTracker | None = None,
) -> asyncio.DatagramTransport:
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((cfg.server.bind_ip, 3702))
    mreq = struct.pack("4sl", socket.inet_aton("239.255.255.250"), socket.INADDR_ANY)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    except OSError as e:
        logger.warning("Multicast join failed (discovery may still work for directed probes): %s", e)

    def _proto_factory() -> _DiscoveryProtocol:
        return _DiscoveryProtocol(cfg, runtime, cameras, activity)

    transport, _ = await loop.create_datagram_endpoint(_proto_factory, sock=sock)
    logger.info("WS-Discovery listening on udp/%s:3702 (multicast 239.255.255.250)", cfg.server.bind_ip)
    return transport  # type: ignore[return-value]
