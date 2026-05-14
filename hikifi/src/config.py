"""Load and validate config.yml with environment variable substitution."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


class ConfigError(ValueError):
    pass


@dataclass
class CameraConfig:
    id: str
    name: str
    manufacturer: str
    model: str
    serial: str
    rtsp_url: str
    width: int
    height: int
    fps: int


@dataclass
class ServerConfig:
    bind_ip: str
    advertised_ip: str
    admin_port: int
    onvif_http_port_start: int
    discovery_enabled: bool
    log_level: str
    rtsp_connectivity_check_enabled: bool = True
    rtsp_connectivity_check_timeout_seconds: float = 5.0


@dataclass
class SecurityConfig:
    onvif_username: str
    onvif_password_env: str


@dataclass
class ModeConfig:
    restream_enabled: bool
    mediamtx_base_url: str
    # Appended to direct (non-restream) RTSP URLs in GetStreamUri (e.g. "?tcp"); see README.
    rtsp_stream_uri_suffix: str = ""


@dataclass
class AppConfig:
    server: ServerConfig
    security: SecurityConfig
    mode: ModeConfig
    cameras: list[CameraConfig] = field(default_factory=list)
    onvif_password: str = ""


def _substitute_env(obj: Any) -> Any:
    if isinstance(obj, str):

        def repl(m: re.Match[str]) -> str:
            key = m.group(1)
            if key not in os.environ:
                raise ConfigError(f"Environment variable {key} is not set (required by config)")
            return os.environ[key]

        return _ENV_PATTERN.sub(repl, obj)
    if isinstance(obj, list):
        return [_substitute_env(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _substitute_env(v) for k, v in obj.items()}
    return obj


def _require_keys(d: Mapping[str, Any], keys: list[str], ctx: str) -> None:
    for k in keys:
        if k not in d or d[k] is None:
            raise ConfigError(f"Missing required key {k!r} in {ctx}")


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError("config.yml must be a mapping at the root")

    _require_keys(raw, ["server", "security", "mode", "cameras"], "root")
    s = raw["server"]
    sec = raw["security"]
    mode = raw["mode"]
    cams = raw["cameras"]

    _require_keys(
        s,
        [
            "bind_ip",
            "advertised_ip",
            "onvif_http_port_start",
            "discovery_enabled",
            "log_level",
        ],
        "server",
    )

    _require_keys(sec, ["onvif_username", "onvif_password_env"], "security")
    _require_keys(mode, ["restream_enabled", "mediamtx_base_url"], "mode")

    if not isinstance(cams, list) or not cams:
        raise ConfigError("cameras must be a non-empty list")

    substituted = _substitute_env(raw)

    s2 = substituted["server"]
    sec2 = substituted["security"]
    mode2 = substituted["mode"]
    cams2 = substituted["cameras"]

    rtsp_check = bool(s2.get("rtsp_connectivity_check_enabled", True))
    rtsp_timeout = float(s2.get("rtsp_connectivity_check_timeout_seconds", 5.0))
    if rtsp_timeout <= 0 or rtsp_timeout > 120:
        raise ConfigError("server.rtsp_connectivity_check_timeout_seconds must be in (0, 120]")

    admin_port = int(s2.get("admin_port", 8090))

    pw_env = sec2["onvif_password_env"]
    if pw_env not in os.environ:
        raise ConfigError(
            f"Required environment variable {pw_env!r} (from security.onvif_password_env) is not set"
        )
    onvif_password = os.environ[pw_env]

    cameras: list[CameraConfig] = []
    for i, c in enumerate(cams2):
        if not isinstance(c, dict):
            raise ConfigError(f"cameras[{i}] must be a mapping")
        _require_keys(
            c,
            [
                "id",
                "name",
                "manufacturer",
                "model",
                "serial",
                "rtsp_url",
                "width",
                "height",
                "fps",
            ],
            f"cameras[{i}]",
        )
        cameras.append(
            CameraConfig(
                id=str(c["id"]),
                name=str(c["name"]),
                manufacturer=str(c["manufacturer"]),
                model=str(c["model"]),
                serial=str(c["serial"]),
                rtsp_url=str(c["rtsp_url"]),
                width=int(c["width"]),
                height=int(c["height"]),
                fps=int(c["fps"]),
            )
        )

    cfg = AppConfig(
        server=ServerConfig(
            bind_ip=str(s2["bind_ip"]),
            advertised_ip=str(s2["advertised_ip"]).strip(),
            admin_port=admin_port,
            onvif_http_port_start=int(s2["onvif_http_port_start"]),
            discovery_enabled=bool(s2["discovery_enabled"]),
            log_level=str(s2["log_level"]),
            rtsp_connectivity_check_enabled=rtsp_check,
            rtsp_connectivity_check_timeout_seconds=rtsp_timeout,
        ),
        security=SecurityConfig(
            onvif_username=str(sec2["onvif_username"]),
            onvif_password_env=str(sec2["onvif_password_env"]),
        ),
        mode=ModeConfig(
            restream_enabled=bool(mode2["restream_enabled"]),
            mediamtx_base_url=str(mode2["mediamtx_base_url"]),
            rtsp_stream_uri_suffix=str(mode2.get("rtsp_stream_uri_suffix", "") or ""),
        ),
        cameras=cameras,
        onvif_password=onvif_password,
    )
    validate_config(cfg)
    return cfg


def validate_config(cfg: AppConfig) -> None:
    if not cfg.server.advertised_ip:
        raise ConfigError("server.advertised_ip must be set to a reachable IP/hostname")

    ids = [c.id for c in cfg.cameras]
    if len(set(ids)) != len(ids):
        raise ConfigError("Each camera must have a unique id")

    serials = [c.serial for c in cfg.cameras]
    if len(set(serials)) != len(serials):
        raise ConfigError("Each camera must have a unique serial")

    if len(cfg.cameras) < 1:
        raise ConfigError("At least one camera is required")

    start = cfg.server.onvif_http_port_start
    n = len(cfg.cameras)
    end = start + n - 1
    admin = cfg.server.admin_port
    if start <= admin <= end:
        raise ConfigError(
            f"admin_port {admin} conflicts with ONVIF port range [{start}, {end}]"
        )

    for cam in cfg.cameras:
        u = urlparse(cam.rtsp_url)
        if u.scheme.lower() != "rtsp" or not u.hostname:
            raise ConfigError(f"Camera {cam.id!r} must have a valid rtsp_url with host")

    if cfg.mode.restream_enabled:
        mu = urlparse(cfg.mode.mediamtx_base_url)
        if mu.scheme.lower() != "rtsp" or not mu.hostname:
            raise ConfigError("mode.mediamtx_base_url must be a valid rtsp:// URL when restream is enabled")
