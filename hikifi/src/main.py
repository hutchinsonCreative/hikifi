"""Application entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path

from src import __version__
from src.camera_activity import CameraActivityTracker
from src.config import ConfigError, load_config
from src.discovery import DiscoveryRuntime, start_discovery
from src.onvif.soap import device_xaddr, hikifi_ws_discovery_display_name, media_xaddr
from src.onvif_server import start_servers
from src.rtsp_connectivity import (
    RtspConnectivityReport,
    check_all_cameras_tcp,
    log_connectivity_results,
)
from src.utils.app_logging import get_logger, setup_logging
from src.utils.env_file import load_dotenv_for_config
from src.utils.redact import redact_rtsp_url

logger = get_logger(__name__)


def _log_config_summary(cfg) -> None:
    logger.info("RTSP-ONVIF bridge v%s starting", __version__)
    logger.info(
        "Server bind=%s advertised=%s admin_port=%s onvif_ports=%s..%s discovery=%s log_level=%s",
        cfg.server.bind_ip,
        cfg.server.advertised_ip,
        cfg.server.admin_port,
        cfg.server.onvif_http_port_start,
        cfg.server.onvif_http_port_start + len(cfg.cameras) - 1,
        cfg.server.discovery_enabled,
        cfg.server.log_level,
    )
    logger.info(
        "Mode restream_enabled=%s mediamtx_base_url=%s",
        cfg.mode.restream_enabled,
        cfg.mode.mediamtx_base_url,
    )
    logger.info("Security onvif_username=%s", cfg.security.onvif_username)
    for cam in cfg.cameras:
        logger.info(
            "Camera %s serial=%s name=%s rtsp=%s",
            cam.id,
            cam.serial,
            cam.name,
            redact_rtsp_url(cam.rtsp_url),
        )


def _log_virtual_endpoints_ready(cfg, cameras: list, ports_by_id: dict[str, int]) -> None:
    logger.info(
        "Virtual cameras come from config only (this service does not probe your LAN for hardware). "
        "When UniFi or another ONVIF client scans or opens an endpoint, you will see SOAP / WS-Discovery lines per camera below."
    )
    logger.info("--- Advertised ONVIF URLs (use server.advertised_ip from clients) ---")
    for cam in cameras:
        port = ports_by_id[cam.id]
        dev = device_xaddr(cfg.server.advertised_ip, port)
        med = media_xaddr(cfg.server.advertised_ip, port)
        logger.info(
            "  %s (%s) TCP %s — device_service=%s media_service=%s",
            cam.id,
            cam.name,
            port,
            dev,
            med,
        )
    logger.info(
        "Admin: http://%s:%s/health  JSON: /cameras  Activity: /debug/activity  RTSP TCP checks: /debug/rtsp",
        cfg.server.advertised_ip,
        cfg.server.admin_port,
    )


async def _async_main(config_path: Path) -> None:
    cfg = load_config(config_path)
    setup_logging(cfg.server.log_level)
    _log_config_summary(cfg)

    ports_by_id = {
        cam.id: cfg.server.onvif_http_port_start + i for i, cam in enumerate(cfg.cameras)
    }
    discovery_runtime = DiscoveryRuntime(
        onvif_device_xaddr=lambda c: device_xaddr(cfg.server.advertised_ip, ports_by_id[c.id]),
        advertised_name=hikifi_ws_discovery_display_name,
    )

    rtsp_report = RtspConnectivityReport()
    if cfg.server.rtsp_connectivity_check_enabled:
        results = await check_all_cameras_tcp(
            cfg.cameras,
            cfg.server.rtsp_connectivity_check_timeout_seconds,
        )
        rtsp_report.set_results(True, results)
        log_connectivity_results(results)
    else:
        logger.info(
            "RTSP TCP connectivity checks disabled (set server.rtsp_connectivity_check_enabled: true to enable)"
        )
        rtsp_report.set_results(False, {})

    activity = CameraActivityTracker([c.id for c in cfg.cameras])
    runners, _sites = await start_servers(cfg, cfg.cameras, discovery_runtime, activity, rtsp_report)
    _log_virtual_endpoints_ready(cfg, cfg.cameras, ports_by_id)

    disc: asyncio.DatagramTransport | None = None
    if cfg.server.discovery_enabled:
        disc = await start_discovery(cfg, discovery_runtime, cfg.cameras, activity=activity)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _stop() -> None:
        stop.set()

    handlers_ok = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            handlers_ok = False
            break

    if handlers_ok:
        await stop.wait()
    else:
        logger.info("Signal handlers unavailable; use Ctrl+C to exit")
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
    logger.info("Shutting down")

    if disc is not None:
        disc.close()

    for r in runners:
        await r.cleanup()


def main() -> None:
    p = argparse.ArgumentParser(description="RTSP-to-ONVIF virtual camera bridge")
    p.add_argument(
        "--config",
        default=os.environ.get("CONFIG_PATH", "config.yml"),
        help="Path to config.yml (default: config.yml or CONFIG_PATH env)",
    )
    args = p.parse_args()
    path = Path(args.config)
    load_dotenv_for_config(path)
    try:
        asyncio.run(_async_main(path))
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        raise SystemExit(2) from e


if __name__ == "__main__":
    main()
