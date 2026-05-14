from __future__ import annotations

from pathlib import Path

import pytest

from src.config import ConfigError, camera_advertised_host, load_config


def test_redacted_rtsp_in_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONVIF_PASSWORD", "pw")
    monkeypatch.setenv("HIK_USER", "u")
    monkeypatch.setenv("HIK_PASS", "secret")
    cfg_yml = tmp_path / "config.yml"
    cfg_yml.write_text(
        """
server:
  bind_ip: "127.0.0.1"
  advertised_ip: "127.0.0.1"
  admin_port: 8090
  onvif_http_port_start: 18081
  discovery_enabled: false
  log_level: "info"
security:
  onvif_username: "unifi"
  onvif_password_env: "ONVIF_PASSWORD"
mode:
  restream_enabled: false
  mediamtx_base_url: "rtsp://127.0.0.1:8554"
cameras:
  - id: "cam01"
    name: "Test"
    manufacturer: "M"
    model: "RTSP-ONVIF-Bridge"
    serial: "S1"
    rtsp_url: "rtsp://${HIK_USER}:${HIK_PASS}@192.168.1.10:554/Streaming/Channels/101"
    width: 1920
    height: 1080
    fps: 25
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_yml)
    assert cfg.cameras[0].rtsp_url.startswith("rtsp://u:secret@")


def test_missing_env_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ONVIF_PASSWORD", raising=False)
    cfg_yml = tmp_path / "config.yml"
    cfg_yml.write_text(
        """
server:
  bind_ip: "127.0.0.1"
  advertised_ip: "127.0.0.1"
  admin_port: 8090
  onvif_http_port_start: 18081
  discovery_enabled: false
  log_level: "info"
security:
  onvif_username: "unifi"
  onvif_password_env: "ONVIF_PASSWORD"
mode:
  restream_enabled: false
  mediamtx_base_url: "rtsp://127.0.0.1:8554"
cameras:
  - id: "cam01"
    name: "Test"
    manufacturer: "M"
    model: "RTSP-ONVIF-Bridge"
    serial: "S1"
    rtsp_url: "rtsp://u:p@192.168.1.10:554/x"
    width: 1920
    height: 1080
    fps: 25
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(cfg_yml)


def test_duplicate_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONVIF_PASSWORD", "pw")
    cfg_yml = tmp_path / "config.yml"
    cfg_yml.write_text(
        """
server:
  bind_ip: "127.0.0.1"
  advertised_ip: "127.0.0.1"
  admin_port: 8090
  onvif_http_port_start: 18081
  discovery_enabled: false
  log_level: "info"
security:
  onvif_username: "unifi"
  onvif_password_env: "ONVIF_PASSWORD"
mode:
  restream_enabled: false
  mediamtx_base_url: "rtsp://127.0.0.1:8554"
cameras:
  - id: "cam01"
    name: "A"
    manufacturer: "M"
    model: "X"
    serial: "S1"
    rtsp_url: "rtsp://u:p@h/x"
    width: 1
    height: 1
    fps: 1
  - id: "cam01"
    name: "B"
    manufacturer: "M"
    model: "X"
    serial: "S2"
    rtsp_url: "rtsp://u:p@h/y"
    width: 1
    height: 1
    fps: 1
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(cfg_yml)


def test_camera_advertised_ip_optional(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONVIF_PASSWORD", "pw")
    cfg_yml = tmp_path / "config.yml"
    cfg_yml.write_text(
        """
server:
  bind_ip: "127.0.0.1"
  advertised_ip: "127.0.0.1"
  admin_port: 8090
  onvif_http_port_start: 18081
  discovery_enabled: false
  log_level: "info"
security:
  onvif_username: "unifi"
  onvif_password_env: "ONVIF_PASSWORD"
mode:
  restream_enabled: false
  mediamtx_base_url: "rtsp://127.0.0.1:8554"
cameras:
  - id: "cam01"
    name: "A"
    manufacturer: "M"
    model: "X"
    serial: "S1"
    rtsp_url: "rtsp://u:p@h/x"
    width: 1
    height: 1
    fps: 1
  - id: "cam02"
    name: "B"
    manufacturer: "M"
    model: "X"
    serial: "S2"
    advertised_ip: "10.0.0.50"
    rtsp_url: "rtsp://u:p@h/y"
    width: 1
    height: 1
    fps: 1
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_yml)
    assert cfg.cameras[0].advertised_ip is None
    assert camera_advertised_host(cfg.cameras[0], cfg.server.advertised_ip) == "127.0.0.1"
    assert cfg.cameras[1].advertised_ip == "10.0.0.50"
    assert camera_advertised_host(cfg.cameras[1], cfg.server.advertised_ip) == "10.0.0.50"


def test_onvif_encoding_hevc_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONVIF_PASSWORD", "pw")
    cfg_yml = tmp_path / "config.yml"
    cfg_yml.write_text(
        """
server:
  bind_ip: "127.0.0.1"
  advertised_ip: "127.0.0.1"
  admin_port: 8090
  onvif_http_port_start: 18081
  discovery_enabled: false
  log_level: "info"
security:
  onvif_username: "unifi"
  onvif_password_env: "ONVIF_PASSWORD"
mode:
  restream_enabled: false
  mediamtx_base_url: "rtsp://127.0.0.1:8554"
cameras:
  - id: "cam01"
    name: "A"
    manufacturer: "M"
    model: "X"
    serial: "S1"
    onvif_encoding: "hevc"
    rtsp_url: "rtsp://u:p@h/x"
    width: 1
    height: 1
    fps: 1
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_yml)
    assert cfg.cameras[0].onvif_encoding == "H265"


def test_onvif_encoding_invalid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONVIF_PASSWORD", "pw")
    cfg_yml = tmp_path / "config.yml"
    cfg_yml.write_text(
        """
server:
  bind_ip: "127.0.0.1"
  advertised_ip: "127.0.0.1"
  admin_port: 8090
  onvif_http_port_start: 18081
  discovery_enabled: false
  log_level: "info"
security:
  onvif_username: "unifi"
  onvif_password_env: "ONVIF_PASSWORD"
mode:
  restream_enabled: false
  mediamtx_base_url: "rtsp://127.0.0.1:8554"
cameras:
  - id: "cam01"
    name: "A"
    manufacturer: "M"
    model: "X"
    serial: "S1"
    onvif_encoding: "VP9"
    rtsp_url: "rtsp://u:p@h/x"
    width: 1
    height: 1
    fps: 1
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(cfg_yml)
