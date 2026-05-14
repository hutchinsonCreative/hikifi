from __future__ import annotations

from src.config import AppConfig, CameraConfig, ModeConfig, SecurityConfig, ServerConfig
from src.onvif.soap import SoapDispatch, append_rtsp_uri_suffix


def test_get_stream_uri_direct_vs_restream() -> None:
    cam = CameraConfig(
        id="cam01",
        name="n",
        manufacturer="m",
        model="mod",
        serial="sn",
        rtsp_url="rtsp://u:pw@192.168.1.5/stream",
        width=1920,
        height=1080,
        fps=25,
    )
    cfg_direct = AppConfig(
        server=ServerConfig(
            bind_ip="0.0.0.0",
            advertised_ip="10.0.0.1",
            admin_port=8090,
            onvif_http_port_start=8081,
            discovery_enabled=False,
            log_level="info",
        ),
        security=SecurityConfig(onvif_username="u", onvif_password_env="X"),
        mode=ModeConfig(restream_enabled=False, mediamtx_base_url="rtsp://10.0.0.1:8554"),
        cameras=[cam],
        onvif_password="p",
    )
    d1 = SoapDispatch(cfg_direct, cam, "10.0.0.1", 8081, "1.0.0")
    _st, _ct, body = d1.dispatch(
        "http://www.onvif.org/ver10/media/wsdl/GetStreamUri",
        "<ignored/>",
    )
    assert "192.168.1.5" in body

    cfg_re = AppConfig(
        server=cfg_direct.server,
        security=cfg_direct.security,
        mode=ModeConfig(restream_enabled=True, mediamtx_base_url="rtsp://10.0.0.1:8554"),
        cameras=[cam],
        onvif_password="p",
    )
    d2 = SoapDispatch(cfg_re, cam, "10.0.0.1", 8081, "1.0.0")
    _st2, _ct2, body2 = d2.dispatch(
        "http://www.onvif.org/ver10/media/wsdl/GetStreamUri",
        "<ignored/>",
    )
    assert "rtsp://10.0.0.1:8554/cam01" in body2


def test_append_rtsp_uri_suffix() -> None:
    assert append_rtsp_uri_suffix("rtsp://h/p", "?tcp") == "rtsp://h/p?tcp"
    assert append_rtsp_uri_suffix("rtsp://h/p?x=1", "&tcp") == "rtsp://h/p?x=1&tcp"
    assert append_rtsp_uri_suffix("rtsp://h/p", "tcp") == "rtsp://h/p?tcp"


def test_get_stream_uri_with_suffix() -> None:
    cam = CameraConfig(
        id="cam01",
        name="n",
        manufacturer="m",
        model="mod",
        serial="sn",
        rtsp_url="rtsp://u:pw@192.168.1.5/stream",
        width=1920,
        height=1080,
        fps=25,
    )
    cfg = AppConfig(
        server=ServerConfig(
            bind_ip="0.0.0.0",
            advertised_ip="10.0.0.1",
            admin_port=8090,
            onvif_http_port_start=8081,
            discovery_enabled=False,
            log_level="info",
        ),
        security=SecurityConfig(onvif_username="u", onvif_password_env="X"),
        mode=ModeConfig(
            restream_enabled=False,
            mediamtx_base_url="rtsp://10.0.0.1:8554",
            rtsp_stream_uri_suffix="?tcp",
        ),
        cameras=[cam],
        onvif_password="p",
    )
    d = SoapDispatch(cfg, cam, "10.0.0.1", 8081, "1.0.0")
    _st, _ct, body = d.dispatch(
        "http://www.onvif.org/ver10/media/wsdl/GetStreamUri",
        "<ignored/>",
    )
    assert "192.168.1.5/stream?tcp" in body
