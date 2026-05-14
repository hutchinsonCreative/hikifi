"""Track ONVIF client interaction per virtual camera (for logs and admin API)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class CameraActivityState:
    soap_requests: int = 0
    discovery_announcements: int = 0
    last_soap_peer: str | None = None
    last_soap_action: str | None = None
    last_soap_unix: float = 0.0
    last_discovery_peer: str | None = None
    last_discovery_unix: float = 0.0


class CameraActivityTracker:
    """Thread-safe counters updated from asyncio SOAP handlers and discovery."""

    def __init__(self, camera_ids: list[str]) -> None:
        self._lock = threading.Lock()
        self._by_id: dict[str, CameraActivityState] = {cid: CameraActivityState() for cid in camera_ids}

    def record_soap(self, cam_id: str, peer: str | None, action: str | None) -> tuple[bool, CameraActivityState]:
        """Record a SOAP request. Returns (first_soap_ever, copy of state after update)."""
        now = time.time()
        with self._lock:
            st = self._by_id[cam_id]
            first = st.soap_requests == 0
            st.soap_requests += 1
            st.last_soap_peer = peer
            st.last_soap_action = action
            st.last_soap_unix = now
            return first, CameraActivityState(
                soap_requests=st.soap_requests,
                discovery_announcements=st.discovery_announcements,
                last_soap_peer=st.last_soap_peer,
                last_soap_action=st.last_soap_action,
                last_soap_unix=st.last_soap_unix,
                last_discovery_peer=st.last_discovery_peer,
                last_discovery_unix=st.last_discovery_unix,
            )

    def record_discovery_announce(self, cam_id: str, peer_host: str) -> None:
        now = time.time()
        with self._lock:
            st = self._by_id[cam_id]
            st.discovery_announcements += 1
            st.last_discovery_peer = peer_host
            st.last_discovery_unix = now

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {
                cid: {
                    "soapRequests": s.soap_requests,
                    "discoveryAnnouncements": s.discovery_announcements,
                    "lastSoapClient": s.last_soap_peer,
                    "lastSoapAction": s.last_soap_action,
                    "lastSoapTime": s.last_soap_unix,
                    "lastDiscoveryClient": s.last_discovery_peer,
                    "lastDiscoveryTime": s.last_discovery_unix,
                }
                for cid, s in self._by_id.items()
            }
