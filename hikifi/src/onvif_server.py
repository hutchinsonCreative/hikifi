"""aiohttp servers: per-camera ONVIF SOAP ports and admin REST API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from aiohttp import web

from src import __version__
from src.camera_activity import CameraActivityTracker
from src.discovery import DiscoveryRuntime
from src.rtsp_connectivity import RtspConnectivityReport
from src.onvif.soap import HIKIFI_ONVIF_MANUFACTURER, SoapDispatch, hikifi_onvif_model, parse_soap_action
from src.config import camera_advertised_host
from src.utils.redact import redact_rtsp_url

if TYPE_CHECKING:
    from src.config import AppConfig, CameraConfig

logger = logging.getLogger(__name__)


def _utc_iso(ts: float) -> str | None:
    if ts and ts > 0:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return None


def _peer(request: web.Request) -> str | None:
    return request.remote


def _local_port(request: web.Request) -> int:
    tr = request.transport
    if tr is None:
        return 0
    name = tr.get_extra_info("sockname")
    if isinstance(name, tuple) and len(name) >= 2:
        return int(name[1])
    return 0


def _camera_for_port(cfg: AppConfig, cameras: list[CameraConfig], port: int) -> CameraConfig | None:
    start = cfg.server.onvif_http_port_start
    for i, cam in enumerate(cameras):
        if start + i == port:
            return cam
    return None


async def _soap_handler(request: web.Request) -> web.StreamResponse:
    cfg: AppConfig = request.app["cfg"]
    cam: CameraConfig = request["camera"]
    activity: CameraActivityTracker = request.app["activity"]
    port = _local_port(request)
    host = camera_advertised_host(cam, cfg.server.advertised_ip)
    peer = _peer(request)
    body_text = await request.text()
    headers = {k: v for k, v in request.headers.items()}
    action = parse_soap_action(headers, body_text)

    first, _st = activity.record_soap(cam.id, peer, action)
    logger.info(
        "SOAP client=%s camera=%s (%s) port=%s action=%s",
        peer or "?",
        cam.id,
        cam.name,
        port,
        action or "?",
    )
    if first:
        logger.info(
            "First ONVIF SOAP request for virtual camera %s — a client reached this endpoint (e.g. after discovery or manual IP add)",
            cam.id,
        )

    user = cfg.security.onvif_username
    pwd = cfg.onvif_password
    if user:
        auth = verify_ws_security_soap(body_text, user, pwd)
        if not auth.ok:
            logger.warning(
                "ONVIF authentication failed client=%s camera=%s detail=%s",
                peer or "?",
                cam.id,
                auth.reason,
            )
            return web.Response(status=401, text="ONVIF authentication failed")

    if action and "GetStreamUri" in action:
        disp0 = SoapDispatch(cfg, cam, host, port, str(request.app["firmware_version"]))
        rtsp = disp0.effective_rtsp()
        logger.info("GetStreamUri for %s -> %s", cam.id, redact_rtsp_url(rtsp))

    disp = SoapDispatch(cfg, cam, host, port, str(request.app["firmware_version"]))
    status, ctype, body = disp.dispatch(action, body_text)
    return web.Response(status=status, content_type=ctype, text=body)


def build_onvif_app(cfg: AppConfig, cameras: list[CameraConfig], activity: CameraActivityTracker) -> web.Application:
    @web.middleware
    async def attach_camera(request: web.Request, handler):  # type: ignore[no-untyped-def]
        port = _local_port(request)
        cam = _camera_for_port(cfg, cameras, port)
        if cam is None:
            return web.Response(status=404, text="No virtual camera on this port")
        request["camera"] = cam
        return await handler(request)

    app = web.Application(middlewares=[attach_camera])
    app["cfg"] = cfg
    app["activity"] = activity
    app["firmware_version"] = __version__
    app.router.add_post("/onvif/device_service", _soap_handler)
    app.router.add_post("/onvif/media_service", _soap_handler)
    return app


def build_admin_app(
    cfg: AppConfig,
    cameras: list[CameraConfig],
    discovery: DiscoveryRuntime,
    activity: CameraActivityTracker,
    rtsp_report: RtspConnectivityReport,
) -> web.Application:
    app = web.Application()
    app["cfg"] = cfg
    app["cameras"] = cameras
    app["discovery"] = discovery
    app["activity"] = activity
    app["rtsp_report"] = rtsp_report

    def _connectivity_for_cam(cam_id: str) -> dict[str, object]:
        if not cfg.server.rtsp_connectivity_check_enabled:
            return {
                "rtspTcpCheckEnabled": False,
                "rtspTcpReachable": None,
                "rtspTcpCheckDetail": None,
                "rtspTarget": None,
                "rtspTcpCheckTimeIso": None,
            }
        r = rtsp_report.get(cam_id)
        if r is None:
            return {
                "rtspTcpCheckEnabled": True,
                "rtspTcpReachable": None,
                "rtspTcpCheckDetail": "no_result",
                "rtspTarget": None,
                "rtspTcpCheckTimeIso": None,
            }
        return {
            "rtspTcpCheckEnabled": True,
            "rtspTcpReachable": r.ok,
            "rtspTcpCheckDetail": r.detail,
            "rtspTarget": f"{r.host}:{r.port}",
            "rtspTcpCheckTimeIso": _utc_iso(r.checked_unix),
        }

    def _activity_for_cam(cam_id: str) -> dict[str, object]:
        snap = activity.snapshot().get(cam_id, {})
        out: dict[str, object] = dict(snap)
        ts = out.get("lastSoapTime")
        if isinstance(ts, (int, float)):
            out["lastSoapTimeIso"] = _utc_iso(float(ts))
        ts2 = out.get("lastDiscoveryTime")
        if isinstance(ts2, (int, float)):
            out["lastDiscoveryTimeIso"] = _utc_iso(float(ts2))
        soap_n = out.get("soapRequests", 0)
        disc_n = out.get("discoveryAnnouncements", 0)
        out["onvifClientSeen"] = bool(int(soap_n) > 0) if isinstance(soap_n, int) else False
        out["discoveryAnnouncedToClient"] = bool(int(disc_n) > 0) if isinstance(disc_n, int) else False
        return out

    async def health(_: web.Request) -> web.Response:
        snap = activity.snapshot()
        touched = sum(1 for v in snap.values() if int(v.get("soapRequests") or 0) > 0)
        tcp_snap = rtsp_report.snapshot()
        tcp_enabled = cfg.server.rtsp_connectivity_check_enabled
        all_reachable: bool | None = None
        unreachable = 0
        if tcp_enabled and tcp_snap:
            all_reachable = all(bool(v.get("rtspTcpReachable")) for v in tcp_snap.values())
            unreachable = sum(1 for v in tcp_snap.values() if not v.get("rtspTcpReachable"))
        return web.json_response(
            {
                "status": "ok",
                "cameraCount": len(cameras),
                "discoveryEnabled": cfg.server.discovery_enabled,
                "restreamEnabled": cfg.mode.restream_enabled,
                "virtualCamerasWithOnvifClients": touched,
                "rtspTcpCheckEnabled": tcp_enabled,
                "rtspTcpAllReachable": all_reachable,
                "rtspTcpUnreachableCount": unreachable if tcp_enabled else None,
            }
        )

    async def list_cameras(_: web.Request) -> web.Response:
        out = []
        start = cfg.server.onvif_http_port_start
        for i, cam in enumerate(cameras):
            adv_host = camera_advertised_host(cam, cfg.server.advertised_ip)
            row: dict[str, object] = {
                "id": cam.id,
                "name": cam.name,
                "serial": cam.serial,
                "manufacturer": HIKIFI_ONVIF_MANUFACTURER,
                "model": hikifi_onvif_model(cam),
                "advertisedIp": adv_host,
                "httpPort": start + i,
                "deviceService": f"http://{adv_host}:{start + i}/onvif/device_service",
                "rtspUrl": redact_rtsp_url(
                    f"{cfg.mode.mediamtx_base_url.rstrip('/')}/{cam.id}"
                    if cfg.mode.restream_enabled
                    else cam.rtsp_url
                ),
            }
            row.update(_activity_for_cam(cam.id))
            row.update(_connectivity_for_cam(cam.id))
            out.append(row)
        return web.json_response(out)

    async def get_camera(request: web.Request) -> web.Response:
        cid = request.match_info["id"]
        for cam in cameras:
            if cam.id == cid:
                start = cfg.server.onvif_http_port_start
                idx = cameras.index(cam)
                adv_host = camera_advertised_host(cam, cfg.server.advertised_ip)
                row: dict[str, object] = {
                    "id": cam.id,
                    "name": cam.name,
                    "serial": cam.serial,
                    "manufacturer": HIKIFI_ONVIF_MANUFACTURER,
                    "model": hikifi_onvif_model(cam),
                    "advertisedIp": adv_host,
                    "width": cam.width,
                    "height": cam.height,
                    "fps": cam.fps,
                    "httpPort": start + idx,
                    "deviceService": f"http://{adv_host}:{start + idx}/onvif/device_service",
                    "rtspUrl": redact_rtsp_url(
                        f"{cfg.mode.mediamtx_base_url.rstrip('/')}/{cam.id}"
                        if cfg.mode.restream_enabled
                        else cam.rtsp_url
                    ),
                }
                row.update(_activity_for_cam(cam.id))
                row.update(_connectivity_for_cam(cam.id))
                return web.json_response(row)
        return web.Response(status=404, text="Unknown camera id")

    async def debug_discovery(_: web.Request) -> web.Response:
        d = discovery.debug
        return web.json_response(
            {
                "probesReceived": d.probes_received,
                "responsesSent": d.responses_sent,
                "lastPeer": d.last_peer,
                "lastMessageId": d.last_message_id,
                "lastError": d.last_error,
            }
        )

    async def debug_activity(_: web.Request) -> web.Response:
        snap = activity.snapshot()
        enriched: dict[str, dict[str, object]] = {}
        for cid, data in snap.items():
            row = dict(data)
            ts = row.get("lastSoapTime")
            if isinstance(ts, (int, float)):
                row["lastSoapTimeIso"] = _utc_iso(float(ts))
            ts2 = row.get("lastDiscoveryTime")
            if isinstance(ts2, (int, float)):
                row["lastDiscoveryTimeIso"] = _utc_iso(float(ts2))
            enriched[cid] = row
        return web.json_response({"cameras": enriched})

    async def debug_rtsp(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "rtspTcpCheckEnabled": cfg.server.rtsp_connectivity_check_enabled,
                "timeoutSeconds": cfg.server.rtsp_connectivity_check_timeout_seconds,
                "cameras": rtsp_report.snapshot(),
            }
        )

    app.router.add_get("/health", health)
    app.router.add_get("/cameras", list_cameras)
    app.router.add_get("/cameras/{id}", get_camera)
    app.router.add_get("/debug/discovery", debug_discovery)
    app.router.add_get("/debug/activity", debug_activity)
    app.router.add_get("/debug/rtsp", debug_rtsp)
    return app


async def start_servers(
    cfg: AppConfig,
    cameras: list[CameraConfig],
    discovery: DiscoveryRuntime,
    activity: CameraActivityTracker,
    rtsp_report: RtspConnectivityReport,
) -> tuple[list[web.AppRunner], list[web.BaseSite]]:
    onvif_app = build_onvif_app(cfg, cameras, activity)
    admin_app = build_admin_app(cfg, cameras, discovery, activity, rtsp_report)

    runners: list[web.AppRunner] = []
    sites: list[web.BaseSite] = []

    onvif_runner = web.AppRunner(onvif_app)
    await onvif_runner.setup()
    runners.append(onvif_runner)
    for i, _cam in enumerate(cameras):
        port = cfg.server.onvif_http_port_start + i
        site = web.TCPSite(onvif_runner, cfg.server.bind_ip, port)
        await site.start()
        sites.append(site)
        logger.info("ONVIF HTTP for camera %s on http://%s:%s/", _cam.id, cfg.server.bind_ip, port)

    admin_runner = web.AppRunner(admin_app)
    await admin_runner.setup()
    runners.append(admin_runner)
    admin_site = web.TCPSite(admin_runner, cfg.server.bind_ip, cfg.server.admin_port)
    await admin_site.start()
    sites.append(admin_site)
    logger.info("Admin API on http://%s:%s/", cfg.server.bind_ip, cfg.server.admin_port)

    return runners, sites
