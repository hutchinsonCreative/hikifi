"""Verify ONVIF WS-Security UsernameToken (password digest)."""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _find_username_token(root: ET.Element) -> ET.Element | None:
    for el in root.iter():
        if _local(el.tag) == "UsernameToken":
            return el
    return None


def _child_text(token: ET.Element, local: str) -> str | None:
    for ch in token:
        if _local(ch.tag) == local:
            t = (ch.text or "").strip()
            return t if t else None
    return None


def _verify_digest_safe(
    nonce_b64: str,
    created: str,
    password: str,
    digest_b64: str,
) -> bool:
    try:
        nonce = base64.b64decode(nonce_b64, validate=True)
    except Exception:
        return False
    created_bytes = created.encode("utf-8")
    password_bytes = password.encode("utf-8")
    expected = hashlib.sha1(nonce + created_bytes + password_bytes).digest()
    expected_b64 = base64.b64encode(expected).decode("ascii")
    return digest_b64.strip() == expected_b64


@dataclass
class AuthResult:
    ok: bool
    reason: str = ""


def verify_ws_security_soap(
    body_text: str,
    expected_username: str,
    expected_password: str,
) -> AuthResult:
    """Validate UsernameToken PasswordDigest in SOAP envelope."""
    if not expected_username:
        return AuthResult(ok=True, reason="auth_disabled")
    try:
        root = ET.fromstring(body_text)
    except ET.ParseError as e:
        return AuthResult(ok=False, reason=f"invalid_xml:{e}")

    header = None
    for ch in root:
        if _local(ch.tag) == "Header":
            header = ch
            break
    if header is None:
        return AuthResult(ok=False, reason="missing_header")

    token = _find_username_token(header)
    if token is None:
        return AuthResult(ok=False, reason="missing_username_token")

    user = _child_text(token, "Username")
    nonce = _child_text(token, "Nonce")
    created = _child_text(token, "Created")
    digest = _child_text(token, "Password")
    if not user or not nonce or not created or not digest:
        return AuthResult(ok=False, reason="incomplete_token")

    digest_val = digest.strip()
    if digest_val.startswith("#"):
        digest_val = re.sub(r"^[^>]*>", "", digest_val)

    if user != expected_username:
        logger.warning("ONVIF auth failure: wrong username %r", user)
        return AuthResult(ok=False, reason="wrong_username")

    if not _verify_digest_safe(nonce, created, expected_password, digest_val):
        logger.warning("ONVIF auth failure: bad password digest for user %r", user)
        return AuthResult(ok=False, reason="bad_digest")

    return AuthResult(ok=True, reason="ok")
