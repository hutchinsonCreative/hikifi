"""TCP reachability checks toward each camera RTSP host:port (no full RTSP handshake)."""

from __future__ import annotations

import asyncio
import errno
import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from src.config import CameraConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RtspTcpCheckResult:
    camera_id: str
    host: str
    port: int
    ok: bool
    detail: str
    checked_unix: float


class RtspConnectivityReport:
    """Latest startup check results (read from admin API)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._results: dict[str, RtspTcpCheckResult] = {}
        self._last_run_enabled: bool = False

    def set_results(self, enabled: bool, results: dict[str, RtspTcpCheckResult]) -> None:
        with self._lock:
            self._last_run_enabled = enabled
            self._results = dict(results)

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {
                cid: {
                    "host": r.host,
                    "port": r.port,
                    "rtspTcpReachable": r.ok,
                    "detail": r.detail,
                    "checkedUnix": r.checked_unix,
                }
                for cid, r in self._results.items()
            }

    def get(self, camera_id: str) -> RtspTcpCheckResult | None:
        with self._lock:
            return self._results.get(camera_id)

    @property
    def last_run_enabled(self) -> bool:
        with self._lock:
            return self._last_run_enabled


def rtsp_tcp_target(rtsp_url: str) -> tuple[str, int]:
    u = urlparse(rtsp_url)
    host = u.hostname or ""
    port = u.port or 554
    return host, port


def _format_os_error(exc: OSError) -> str:
    if exc.errno is not None:
        name = errno.errorcode.get(exc.errno, str(exc.errno))
        return f"{name}: {exc.strerror or exc}"
    return str(exc)


async def check_rtsp_tcp(host: str, port: int, timeout: float) -> tuple[bool, str]:
    """Try TCP connect to host:port. Does not validate RTSP protocol or credentials."""
    if not host:
        return False, "missing_host"
    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True, "tcp_connect_ok"
    except asyncio.TimeoutError:
        return False, f"timeout_after_{timeout:g}s"
    except OSError as e:
        return False, _format_os_error(e)
    except Exception as e:
        return False, f"error:{type(e).__name__}:{e}"


async def check_all_cameras_tcp(
    cameras: list[CameraConfig],
    timeout: float,
) -> dict[str, RtspTcpCheckResult]:
    """Run checks in parallel (one coroutine per camera)."""

    async def one(cam: CameraConfig) -> RtspTcpCheckResult:
        host, port = rtsp_tcp_target(cam.rtsp_url)
        ok, detail = await check_rtsp_tcp(host, port, timeout)
        return RtspTcpCheckResult(
            camera_id=cam.id,
            host=host,
            port=port,
            ok=ok,
            detail=detail,
            checked_unix=time.time(),
        )

    results_list = await asyncio.gather(*[one(c) for c in cameras])
    return {r.camera_id: r for r in results_list}


def log_connectivity_results(results: dict[str, RtspTcpCheckResult]) -> None:
    logger.info("--- RTSP endpoint TCP checks (host:port from each rtsp_url; not a full RTSP login) ---")
    for cid in sorted(results.keys()):
        r = results[cid]
        if r.ok:
            logger.info(
                "RTSP TCP %s: OK — reached %s:%s (%s)",
                cid,
                r.host,
                r.port,
                r.detail,
            )
        else:
            logger.warning(
                "RTSP TCP %s: FAILED — %s:%s (%s)",
                cid,
                r.host,
                r.port,
                r.detail,
            )
    n_ok = sum(1 for r in results.values() if r.ok)
    n = len(results)
    if n_ok == n:
        logger.info("RTSP TCP summary: all %d camera endpoint(s) reachable.", n)
    else:
        logger.warning(
            "RTSP TCP summary: %d of %d camera endpoint(s) reachable. "
            "UniFi/Protect on this host cannot pull those streams until routing/firewall allows TCP to the NVR.",
            n_ok,
            n,
        )
