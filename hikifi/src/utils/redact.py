"""Redact secrets from RTSP URLs and other strings for logs and debug APIs."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

_RTSP_USERINFO = re.compile(r"^(rtsp://)([^/@:]+)(:)([^@]*)(@)", re.IGNORECASE)


def redact_rtsp_url(url: str) -> str:
    """Return RTSP URL with password replaced by ****, user preserved."""
    if not url or not url.lower().startswith("rtsp://"):
        return url
    parsed = urlparse(url)
    if not parsed.username:
        return url
    pw = parsed.password or ""
    if pw:
        userinfo = f"{parsed.username}:****"
    else:
        userinfo = parsed.username
    netloc = f"{userinfo}@{parsed.hostname or ''}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    rebuilt = urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )
    return rebuilt


def redact_log_line(text: str) -> str:
    """Best-effort redaction for log lines that may contain rtsp://... URLs."""
    return _RTSP_USERINFO.sub(r"\1\2\3****\5", text)
