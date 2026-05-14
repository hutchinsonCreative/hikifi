"""Build ONVIF SOAP 1.2 responses (minimal subset for UniFi Protect)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import AppConfig, CameraConfig


def esc(s: str) -> str:
    return html.escape(s, quote=True)


# ONVIF / WS-Discovery: clients typically show Manufacturer + Model as the device title.
HIKIFI_ONVIF_MANUFACTURER = "HikiFi"


def hikifi_onvif_model(cam: CameraConfig) -> str:
    return cam.name


def hikifi_ws_discovery_display_name(cam: CameraConfig) -> str:
    return f"{HIKIFI_ONVIF_MANUFACTURER} {cam.name}"


def hikifi_media_configuration_name(cam: CameraConfig) -> str:
    return hikifi_ws_discovery_display_name(cam)


SOAP_ENVELOPE_START = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
    'xmlns:tt="http://www.onvif.org/ver10/schema" '
    'xmlns:trt="http://www.onvif.org/ver10/media/wsdl" '
    'xmlns:ter="http://www.onvif.org/ver10/error" >'
    "<s:Body>"
)

SOAP_ENVELOPE_END = "</s:Body></s:Envelope>"


def fault(sender: str, subcode: str, reason: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:ter="http://www.onvif.org/ver10/error">'
        "<s:Body>"
        "<s:Fault>"
        "<s:Code>"
        f"<s:Value>s:{sender}</s:Value>"
        f"<s:Subcode><s:Value>ter:{esc(subcode)}</s:Value></s:Subcode>"
        "</s:Code>"
        "<s:Reason>"
        f'<s:Text xml:lang="en">{esc(reason)}</s:Text>'
        "</s:Reason>"
        "</s:Fault>"
        "</s:Body></s:Envelope>"
    )


def profile_token(cam_id: str) -> str:
    return f"profile_{cam_id}_main"


def device_xaddr(host: str, port: int) -> str:
    return f"http://{host}:{port}/onvif/device_service"


def media_xaddr(host: str, port: int) -> str:
    return f"http://{host}:{port}/onvif/media_service"


def get_device_information(cam: CameraConfig, firmware_version: str) -> str:
    inner = (
        "<tds:GetDeviceInformationResponse>"
        f"<tds:Manufacturer>{esc(HIKIFI_ONVIF_MANUFACTURER)}</tds:Manufacturer>"
        f"<tds:Model>{esc(hikifi_onvif_model(cam))}</tds:Model>"
        f"<tds:FirmwareVersion>{esc(firmware_version)}</tds:FirmwareVersion>"
        f"<tds:SerialNumber>{esc(cam.serial)}</tds:SerialNumber>"
        "<tds:HardwareId>virtual-camera</tds:HardwareId>"
        "</tds:GetDeviceInformationResponse>"
    )
    return SOAP_ENVELOPE_START + inner + SOAP_ENVELOPE_END


def get_system_date_and_time() -> str:
    now = datetime.now(timezone.utc)
    inner = (
        "<tds:GetSystemDateAndTimeResponse>"
        "<tds:SystemDateAndTime>"
        "<tt:DateTimeType>UTC</tt:DateTimeType>"
        "<tt:DaylightSavings>false</tt:DaylightSavings>"
        "<tt:TimeZone><tt:TZ>UTC</tt:TZ></tt:TimeZone>"
        "<tt:UTCDateTime>"
        "<tt:Time>"
        f"<tt:Hour>{now.hour}</tt:Hour>"
        f"<tt:Minute>{now.minute}</tt:Minute>"
        f"<tt:Second>{now.second}</tt:Second>"
        "</tt:Time>"
        "<tt:Date>"
        f"<tt:Year>{now.year}</tt:Year>"
        f"<tt:Month>{now.month}</tt:Month>"
        f"<tt:Day>{now.day}</tt:Day>"
        "</tt:Date>"
        "</tt:UTCDateTime>"
        "</tds:SystemDateAndTime>"
        "</tds:GetSystemDateAndTimeResponse>"
    )
    return SOAP_ENVELOPE_START + inner + SOAP_ENVELOPE_END


def get_capabilities(host: str, port: int) -> str:
    dx = esc(device_xaddr(host, port))
    mx = esc(media_xaddr(host, port))
    inner = (
        "<tds:GetCapabilitiesResponse>"
        "<tds:Capabilities>"
        "<tt:Media>"
        f"<tt:XAddr>{mx}</tt:XAddr>"
        "<tt:StreamingCapabilities>"
        "<tt:RTPMulticast>false</tt:RTPMulticast>"
        "<tt:RTP_TCP>true</tt:RTP_TCP>"
        "<tt:RTP_RTSP_TCP>true</tt:RTP_RTSP_TCP>"
        "</tt:StreamingCapabilities>"
        "</tt:Media>"
        "<tt:Device>"
        f"<tt:XAddr>{dx}</tt:XAddr>"
        "</tt:Device>"
        "</tds:Capabilities>"
        "</tds:GetCapabilitiesResponse>"
    )
    return SOAP_ENVELOPE_START + inner + SOAP_ENVELOPE_END


def get_services(host: str, port: int) -> str:
    dx = esc(device_xaddr(host, port))
    mx = esc(media_xaddr(host, port))
    inner = (
        "<tds:GetServicesResponse>"
        "<tds:Service>"
        "<tds:Namespace>http://www.onvif.org/ver10/device/wsdl</tds:Namespace>"
        f"<tds:XAddr>{dx}</tds:XAddr>"
        "<tds:Version><tt:Major>2</tt:Major><tt:Minor>0</tt:Minor></tds:Version>"
        "</tds:Service>"
        "<tds:Service>"
        "<tds:Namespace>http://www.onvif.org/ver10/media/wsdl</tds:Namespace>"
        f"<tds:XAddr>{mx}</tds:XAddr>"
        "<tds:Version><tt:Major>2</tt:Major><tt:Minor>0</tt:Minor></tds:Version>"
        "</tds:Service>"
        "</tds:GetServicesResponse>"
    )
    return SOAP_ENVELOPE_START + inner + SOAP_ENVELOPE_END


def get_video_sources(cam: CameraConfig) -> str:
    vs_token = f"video_{cam.id}"
    inner = (
        "<trt:GetVideoSourcesResponse>"
        "<trt:VideoSources>"
        "<tt:Framerate>"
        f"{cam.fps}.0"
        "</tt:Framerate>"
        f'<tt:Resolution><tt:Width>{cam.width}</tt:Width><tt:Height>{cam.height}</tt:Height></tt:Resolution>'
        f"<tt:Imaging><tt:Brightness>128.0</tt:Brightness></tt:Imaging>"
        f'<tt:token>{esc(vs_token)}</tt:token>'
        "</trt:VideoSources>"
        "</trt:GetVideoSourcesResponse>"
    )
    return SOAP_ENVELOPE_START + inner + SOAP_ENVELOPE_END


def get_video_source_configurations(cam: CameraConfig) -> str:
    vs_token = f"video_{cam.id}"
    vsc_token = f"vsc_{cam.id}_main"
    inner = (
        "<trt:GetVideoSourceConfigurationsResponse>"
        "<trt:Configurations>"
        f'<tt:Name>{esc(hikifi_media_configuration_name(cam))}</tt:Name>'
        f"<tt:UseCount>1</tt:UseCount>"
        f'<tt:token>{esc(vsc_token)}</tt:token>'
        "<tt:SourceToken>"
        f"{esc(vs_token)}"
        "</tt:SourceToken>"
        "<tt:Bounds height=\"100\" width=\"100\" y=\"0\" x=\"0\"/>"
        "</trt:Configurations>"
        "</trt:GetVideoSourceConfigurationsResponse>"
    )
    return SOAP_ENVELOPE_START + inner + SOAP_ENVELOPE_END


def get_video_encoder_configurations(cam: CameraConfig) -> str:
    vs_token = f"video_{cam.id}"
    vec_token = f"vec_{cam.id}_main"
    inner = (
        "<trt:GetVideoEncoderConfigurationsResponse>"
        "<trt:Configurations>"
        f'<tt:Name>{esc(hikifi_media_configuration_name(cam))}</tt:Name>'
        f"<tt:UseCount>1</tt:UseCount>"
        f'<tt:token>{esc(vec_token)}</tt:token>'
        f"<tt:Encoding>H264</tt:Encoding>"
        f'<tt:Resolution><tt:Width>{cam.width}</tt:Width><tt:Height>{cam.height}</tt:Height></tt:Resolution>'
        "<tt:Quality>5.0</tt:Quality>"
        "<tt:RateControl>"
        "<tt:FrameRateLimit>"
        f"{cam.fps}"
        "</tt:FrameRateLimit>"
        "<tt:EncodingInterval>1</tt:EncodingInterval>"
        "<tt:BitrateLimit>4096</tt:BitrateLimit>"
        "</tt:RateControl>"
        f"<tt:Multicast><tt:Address><tt:Type>IPv4</tt:Type><tt:IPv4Address>0.0.0.0</tt:IPv4Address></tt:Address><tt:Port>0</tt:Port><tt:TTL>1</tt:TTL><tt:AutoStart>false</tt:AutoStart></tt:Multicast>"
        f"<tt:SessionTimeout>PT60S</tt:SessionTimeout>"
        f"<tt:SourceToken>{esc(vs_token)}</tt:SourceToken>"
        "</trt:Configurations>"
        "</trt:GetVideoEncoderConfigurationsResponse>"
    )
    return SOAP_ENVELOPE_START + inner + SOAP_ENVELOPE_END


def get_profiles(cam: CameraConfig) -> str:
    vs_token = f"video_{cam.id}"
    vsc_token = f"vsc_{cam.id}_main"
    vec_token = f"vec_{cam.id}_main"
    ptok = profile_token(cam.id)
    inner = (
        "<trt:GetProfilesResponse>"
        "<trt:Profiles fixed=\"true\" token="
        f'"{esc(ptok)}"'
        ">"
        f"<tt:Name>{esc(hikifi_media_configuration_name(cam))}</tt:Name>"
        "<tt:VideoSourceConfiguration>"
        f'<tt:Name>{esc(hikifi_media_configuration_name(cam))}</tt:Name>'
        f"<tt:UseCount>1</tt:UseCount>"
        f'<tt:token>{esc(vsc_token)}</tt:token>'
        f"<tt:SourceToken>{esc(vs_token)}</tt:SourceToken>"
        "<tt:Bounds height=\"100\" width=\"100\" y=\"0\" x=\"0\"/>"
        "</tt:VideoSourceConfiguration>"
        "<tt:VideoEncoderConfiguration>"
        f'<tt:Name>{esc(hikifi_media_configuration_name(cam))}</tt:Name>'
        f"<tt:UseCount>1</tt:UseCount>"
        f'<tt:token>{esc(vec_token)}</tt:token>'
        "<tt:Encoding>H264</tt:Encoding>"
        f'<tt:Resolution><tt:Width>{cam.width}</tt:Width><tt:Height>{cam.height}</tt:Height></tt:Resolution>'
        "<tt:Quality>5.0</tt:Quality>"
        "<tt:RateControl>"
        f"<tt:FrameRateLimit>{cam.fps}</tt:FrameRateLimit>"
        "<tt:EncodingInterval>1</tt:EncodingInterval>"
        "<tt:BitrateLimit>4096</tt:BitrateLimit>"
        "</tt:RateControl>"
        f"<tt:Multicast><tt:Address><tt:Type>IPv4</tt:Type><tt:IPv4Address>0.0.0.0</tt:IPv4Address></tt:Address><tt:Port>0</tt:Port><tt:TTL>1</tt:TTL><tt:AutoStart>false</tt:AutoStart></tt:Multicast>"
        "<tt:SessionTimeout>PT60S</tt:SessionTimeout>"
        f"<tt:SourceToken>{esc(vs_token)}</tt:SourceToken>"
        "</tt:VideoEncoderConfiguration>"
        "</trt:Profiles>"
        "</trt:GetProfilesResponse>"
    )
    return SOAP_ENVELOPE_START + inner + SOAP_ENVELOPE_END


def append_rtsp_uri_suffix(url: str, suffix: str) -> str:
    """Append a query string to an RTSP URL for client-specific transport hints."""
    s = (suffix or "").strip()
    if not s:
        return url
    if s.startswith("?") or s.startswith("&"):
        return url + s
    return url + ("&" if "?" in url else "?") + s


def get_stream_uri(rtsp_uri: str) -> str:
    u = esc(rtsp_uri)
    inner = (
        "<trt:GetStreamUriResponse>"
        "<trt:MediaUri>"
        f"<tt:Uri>{u}</tt:Uri>"
        "<tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>"
        "<tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>"
        "<tt:Timeout>PT60S</tt:Timeout>"
        "</trt:MediaUri>"
        "</trt:GetStreamUriResponse>"
    )
    return SOAP_ENVELOPE_START + inner + SOAP_ENVELOPE_END


def get_snapshot_uri_not_supported() -> str:
    return fault("Sender", "ActionNotSupported", "Snapshot URI is not supported by this bridge")


@dataclass
class SoapDispatch:
    cfg: AppConfig
    cam: CameraConfig
    host: str
    port: int
    firmware_version: str

    def effective_rtsp(self) -> str:
        if self.cfg.mode.restream_enabled:
            base = self.cfg.mode.mediamtx_base_url.rstrip("/")
            return f"{base}/{self.cam.id}"
        return append_rtsp_uri_suffix(self.cam.rtsp_url, self.cfg.mode.rtsp_stream_uri_suffix)

    def dispatch(self, action: str | None, body_text: str) -> tuple[int, str, str]:
        if action is None:
            return 400, "text/plain", "Missing SOAPAction"

        a = action.strip().strip('"')
        local = a.rsplit("/", 1)[-1]

        def ok(xml: str) -> tuple[int, str, str]:
            return 200, "application/soap+xml", xml

        if local == "GetDeviceInformation" or a.endswith("/GetDeviceInformation"):
            return ok(get_device_information(self.cam, self.firmware_version))
        if local == "GetSystemDateAndTime" or a.endswith("/GetSystemDateAndTime"):
            return ok(get_system_date_and_time())
        if local == "GetCapabilities" or a.endswith("/GetCapabilities"):
            return ok(get_capabilities(self.host, self.port))
        if local == "GetServices" or a.endswith("/GetServices"):
            return ok(get_services(self.host, self.port))
        if local == "GetVideoSources" or a.endswith("/GetVideoSources"):
            return ok(get_video_sources(self.cam))
        if local == "GetVideoSourceConfigurations" or a.endswith("/GetVideoSourceConfigurations"):
            return ok(get_video_source_configurations(self.cam))
        if local == "GetVideoEncoderConfigurations" or a.endswith("/GetVideoEncoderConfigurations"):
            return ok(get_video_encoder_configurations(self.cam))
        if local == "GetProfiles" or a.endswith("/GetProfiles"):
            return ok(get_profiles(self.cam))
        if local == "GetStreamUri" or a.endswith("/GetStreamUri"):
            return ok(get_stream_uri(self.effective_rtsp()))
        if local == "GetSnapshotUri" or a.endswith("/GetSnapshotUri"):
            xml = get_snapshot_uri_not_supported()
            return 200, "application/soap+xml", xml

        return ok(
            fault("Receiver", "ActionNotSupported", f"Action not implemented: {esc(a)}")
        )


_BODY_LOCAL_TO_ACTION: dict[str, str] = {
    "GetDeviceInformation": "http://www.onvif.org/ver10/device/wsdl/GetDeviceInformation",
    "GetSystemDateAndTime": "http://www.onvif.org/ver10/device/wsdl/GetSystemDateAndTime",
    "GetCapabilities": "http://www.onvif.org/ver10/device/wsdl/GetCapabilities",
    "GetServices": "http://www.onvif.org/ver10/device/wsdl/GetServices",
    "GetVideoSources": "http://www.onvif.org/ver10/media/wsdl/GetVideoSources",
    "GetVideoSourceConfigurations": "http://www.onvif.org/ver10/media/wsdl/GetVideoSourceConfigurations",
    "GetVideoEncoderConfigurations": "http://www.onvif.org/ver10/media/wsdl/GetVideoEncoderConfigurations",
    "GetProfiles": "http://www.onvif.org/ver10/media/wsdl/GetProfiles",
    "GetStreamUri": "http://www.onvif.org/ver10/media/wsdl/GetStreamUri",
    "GetSnapshotUri": "http://www.onvif.org/ver10/media/wsdl/GetSnapshotUri",
}


def parse_soap_action(headers: dict[str, str], body_text: str) -> str | None:
    for key, val in headers.items():
        if key.lower() == "soapaction":
            v = val.strip()
            if v in ("", '""'):
                break
            return v.strip('"')
    ct = headers.get("Content-Type") or headers.get("content-type") or ""
    if "action=" in ct.lower():
        m = re.search(r'action\s*=\s*"([^"]+)"', ct, re.I)
        if m:
            return m.group(1)
    try:
        from xml.etree import ElementTree as ET

        root = ET.fromstring(body_text)
    except ET.ParseError:
        return None

    def local(t: str) -> str:
        return t.rsplit("}", 1)[-1] if "}" in t else t

    for el in root.iter():
        if local(el.tag) == "Body":
            for ch in el:
                tag = local(ch.tag)
                if tag == "Header":
                    continue
                return _BODY_LOCAL_TO_ACTION.get(tag)
    return None
