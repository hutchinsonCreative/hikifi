# RTSP-to-ONVIF Virtual Camera Bridge Specification

## Goal

Build a lightweight self-hosted application that allows UniFi Protect to discover and add multiple Hikvision NVR/DVR RTSP channel streams as separate ONVIF cameras.

The application should run on a Raspberry Pi 4 or similar Linux host. It should avoid video transcoding. The preferred design is to expose virtual ONVIF devices that return existing RTSP stream URLs when UniFi Protect asks for the stream URI.

## Problem

Two Hikvision NVR/DVR devices expose multiple camera channels over RTSP. Example URLs:

```text
rtsp://USERNAME:PASSWORD@192.168.60.32:554/Streaming/Channels/101
rtsp://USERNAME:PASSWORD@192.168.60.32:554/Streaming/Channels/201
rtsp://USERNAME:PASSWORD@192.168.60.32:554/Streaming/Channels/301
```

UniFi Protect currently detects only one camera from the Hikvision device instead of exposing each channel as a separate camera.

## Desired Outcome

UniFi Protect should see each configured RTSP channel as a separate ONVIF-compatible camera.

Example:

```text
Virtual ONVIF Camera 01 -> Hikvision NVR 1 Channel 101
Virtual ONVIF Camera 02 -> Hikvision NVR 1 Channel 201
Virtual ONVIF Camera 03 -> Hikvision NVR 1 Channel 301
...
Virtual ONVIF Camera 16 -> Hikvision NVR 2 Channel 801
```

## Hard Requirements

1. Must run on Raspberry Pi 4, Ubuntu Server, Raspberry Pi OS, or Debian.
2. Must not transcode video by default.
3. Must support at least 16 camera streams.
4. Must expose each configured stream as a separate ONVIF discoverable camera.
5. Must support UniFi Protect ONVIF discovery where possible.
6. Must provide a simple YAML config file for defining virtual cameras.
7. Must support Docker Compose deployment.
8. Must include clear logging.
9. Must include health checks.
10. Must never store passwords in source code.

## Recommended Architecture

### Preferred Mode: ONVIF Wrapper Only

The service should:

1. Read a list of virtual cameras from `config.yml`.
2. For each virtual camera, expose ONVIF device/media services.
3. Respond to WS-Discovery probe requests.
4. Return the configured RTSP URL when `GetStreamUri` is requested.
5. Avoid proxying the actual video stream.

In this mode, video traffic flows directly:

```text
UniFi Protect -> Hikvision NVR RTSP stream
```

The Raspberry Pi only handles ONVIF discovery and SOAP/XML responses.

### Optional Mode: MediaMTX Restream

If UniFi Protect does not accept the remote Hikvision RTSP URL directly, add an optional MediaMTX-based restream mode.

In this mode:

```text
Hikvision RTSP -> MediaMTX on Pi -> UniFi Protect
```

The app should still avoid transcoding. MediaMTX should use RTSP pass-through/restreaming only.

ONVIF `GetStreamUri` should return:

```text
rtsp://PI_IP:8554/cam01
```

instead of the Hikvision URL.

## Technology Preference

Use one of the following:

### Option A: Node.js

Recommended packages:

- Express or Fastify for HTTP endpoints
- UDP socket support for WS-Discovery
- XML/SOAP response handling
- YAML config parser
- Docker Compose

### Option B: Python

Recommended packages:

- FastAPI or Flask
- `socket` / `asyncio` for WS-Discovery
- `lxml` or XML templates for SOAP responses
- PyYAML
- Docker Compose

Choose the option with the fastest path to a working ONVIF implementation.

## Config File

Create `config.yml`:

```yaml
server:
  bind_ip: "0.0.0.0"
  advertised_ip: "192.168.60.50"
  onvif_http_port_start: 8081
  discovery_enabled: true
  log_level: "info"

security:
  onvif_username: "unifi"
  onvif_password_env: "ONVIF_PASSWORD"

mode:
  restream_enabled: false
  mediamtx_base_url: "rtsp://192.168.60.50:8554"

cameras:
  - id: "cam01"
    name: "Right Camera 1"
    manufacturer: "Virtual Hikvision Bridge"
    model: "RTSP-ONVIF-Bridge"
    serial: "VHIK-CAM-001"
    rtsp_url: "rtsp://USERNAME:PASSWORD@192.168.60.32:554/Streaming/Channels/101"
    width: 1920
    height: 1080
    fps: 25

  - id: "cam02"
    name: "Right Camera 2"
    manufacturer: "Virtual Hikvision Bridge"
    model: "RTSP-ONVIF-Bridge"
    serial: "VHIK-CAM-002"
    rtsp_url: "rtsp://USERNAME:PASSWORD@192.168.60.32:554/Streaming/Channels/201"
    width: 1920
    height: 1080
    fps: 25

  - id: "cam03"
    name: "Left Camera 1"
    manufacturer: "Virtual Hikvision Bridge"
    model: "RTSP-ONVIF-Bridge"
    serial: "VHIK-CAM-003"
    rtsp_url: "rtsp://USERNAME:PASSWORD@192.168.60.33:554/Streaming/Channels/101"
    width: 1920
    height: 1080
    fps: 25
```

The app should also support environment variable substitution in RTSP URLs, for example:

```yaml
rtsp_url: "rtsp://${HIK_USER}:${HIK_PASS}@192.168.60.32:554/Streaming/Channels/101"
```

## ONVIF Features To Implement

Implement the minimum ONVIF features required for UniFi Protect to discover and add the cameras.

### WS-Discovery

Listen on UDP multicast:

```text
239.255.255.250:3702
```

Respond to ONVIF `Probe` messages with one response per configured virtual camera.

Each virtual camera should have a unique:

- UUID
- XAddr
- friendly name
- serial number

Example XAddr:

```text
http://192.168.60.50:8081/onvif/device_service
http://192.168.60.50:8082/onvif/device_service
http://192.168.60.50:8083/onvif/device_service
```

### Device Service Endpoints

Each virtual camera should expose:

```text
/onvif/device_service
/onvif/media_service
```

The service can run either:

1. One HTTP port per virtual camera, or
2. One HTTP service with unique paths per camera.

Prefer one port per camera if it improves UniFi compatibility.

### Required ONVIF SOAP Actions

Implement at least:

- `GetDeviceInformation`
- `GetCapabilities`
- `GetServices`
- `GetProfiles`
- `GetStreamUri`
- `GetVideoSources`
- `GetVideoSourceConfigurations`
- `GetVideoEncoderConfigurations`
- `GetSnapshotUri` if easy, otherwise return a sensible fault
- `GetSystemDateAndTime`

### GetDeviceInformation

Return configured values:

```text
Manufacturer: Virtual Hikvision Bridge
Model: RTSP-ONVIF-Bridge
FirmwareVersion: 1.0.0
SerialNumber: per camera serial from config
HardwareId: virtual-camera
```

### GetProfiles

Return one profile per virtual camera.

Example token:

```text
profile_cam01_main
```

### GetStreamUri

Return the configured RTSP URL for that virtual camera.

If `restream_enabled` is false:

```text
rtsp://USERNAME:PASSWORD@HIKVISION_NVR_IP:554/Streaming/Channels/201
```

If `restream_enabled` is true:

```text
rtsp://PI_IP:8554/cam01
```

## Authentication

Support ONVIF username/password authentication.

Minimum acceptable for first version:

- Basic auth or simple digest-compatible handling if UniFi requires it.

Preferred:

- ONVIF WS-Security UsernameToken digest support.

Credentials should come from environment variables, not hardcoded source files.

Example `.env`:

```env
ONVIF_PASSWORD=change_me
HIK_USER=unifi
HIK_PASS=change_me
```

## Docker Compose

Provide `docker-compose.yml`.

For ONVIF discovery to work, host networking may be required:

```yaml
services:
  onvif-bridge:
    build: .
    network_mode: host
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./config.yml:/app/config.yml:ro
```

If MediaMTX mode is included:

```yaml
services:
  mediamtx:
    image: bluenviron/mediamtx:latest
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./mediamtx.yml:/mediamtx.yml:ro
```

## MediaMTX Optional Config Generation

If restream mode is enabled, the app should either:

1. Generate a `mediamtx.yml` from `config.yml`, or
2. Provide a documented script to generate it.

Example MediaMTX path:

```yaml
paths:
  cam01:
    source: rtsp://USERNAME:PASSWORD@192.168.60.32:554/Streaming/Channels/101
  cam02:
    source: rtsp://USERNAME:PASSWORD@192.168.60.32:554/Streaming/Channels/201
```

## Admin / Debug Endpoints

Expose local debug endpoints:

```text
GET /health
GET /cameras
GET /cameras/:id
GET /debug/discovery
```

`/health` should return:

```json
{
  "status": "ok",
  "cameraCount": 16,
  "discoveryEnabled": true,
  "restreamEnabled": false
}
```

Do not expose passwords in debug responses.

RTSP URLs should be redacted:

```text
rtsp://USERNAME:****@192.168.60.32:554/Streaming/Channels/101
```

## Logging

Log:

- Startup config summary
- Virtual camera list
- WS-Discovery probes received
- Probe responses sent
- SOAP action received
- `GetStreamUri` requests
- Authentication failures
- Config validation errors

Do not log full passwords.

## Validation

At startup validate:

- Each camera has unique `id`
- Each camera has unique `serial`
- Each camera has a valid RTSP URL
- Advertised IP is set
- Required environment variables exist
- Port allocation does not conflict

## Test Plan

### 1. RTSP Validation

Before ONVIF testing, verify all Hikvision RTSP streams in VLC:

```text
rtsp://USERNAME:PASSWORD@192.168.60.32:554/Streaming/Channels/101
rtsp://USERNAME:PASSWORD@192.168.60.32:554/Streaming/Channels/201
rtsp://USERNAME:PASSWORD@192.168.60.32:554/Streaming/Channels/301
```

### 2. ONVIF Discovery Test

Use ONVIF Device Manager or another ONVIF discovery tool on the same VLAN.

Expected:

- Each virtual camera appears separately.
- Each camera has a unique name and serial.
- Each camera returns a stream URI.

### 3. UniFi Protect Test

In UniFi Protect:

1. Add third-party ONVIF camera.
2. Confirm virtual cameras appear separately.
3. Add each camera.
4. Confirm Protect records and displays each stream independently.

### 4. Raspberry Pi Load Test

With 16 cameras added:

- CPU should remain low in wrapper-only mode.
- RAM should remain stable.
- No ffmpeg/transcoding processes should run unless explicitly enabled.
- Network load should primarily be Hikvision NVR to UniFi Protect, not through the Pi, unless restream mode is enabled.

## Performance Notes

A Raspberry Pi 4 should be sufficient in ONVIF-wrapper-only mode because it is not processing video.

A Raspberry Pi 4 may also work in MediaMTX restream mode if all streams are copied/pass-through only.

The Raspberry Pi 4 is not suitable for transcoding 16 camera streams.

## Security Notes

1. Rotate any camera/NVR password that has been pasted into chat, logs, commits, or screenshots.
2. Use a dedicated low-privilege Hikvision user for RTSP access.
3. Use a dedicated ONVIF user for UniFi Protect.
4. Keep `.env` out of Git.
5. Add `.env` to `.gitignore`.
6. Do not expose the bridge outside the local camera VLAN.
7. Prefer firewall rules allowing only UniFi Protect, the Pi, and the Hikvision NVRs to communicate.

## Suggested Repository Structure

```text
rtsp-onvif-bridge/
  README.md
  spec.md
  docker-compose.yml
  Dockerfile
  .env.example
  .gitignore
  config.example.yml
  src/
    main.*
    config.*
    discovery.*
    onvif/
      device-service.*
      media-service.*
      soap-templates.*
    utils/
      redact.*
      logger.*
  scripts/
    generate-mediamtx-config.*
  tests/
    config.test.*
    soap.test.*
    discovery.test.*
```

## Initial MVP Scope

Build the smallest version that can:

1. Load `config.yml`.
2. Create virtual ONVIF cameras.
3. Respond to WS-Discovery.
4. Implement `GetDeviceInformation`.
5. Implement `GetProfiles`.
6. Implement `GetStreamUri`.
7. Be discovered by ONVIF Device Manager.
8. Be added to UniFi Protect.

After that, add optional MediaMTX restream support.

## Example Camera Channel Mapping

For Hikvision-style RTSP channel URLs:

```text
Camera 1 main stream: rtsp://USER:PASS@NVR_IP:554/Streaming/Channels/101
Camera 1 sub stream:  rtsp://USER:PASS@NVR_IP:554/Streaming/Channels/102
Camera 2 main stream: rtsp://USER:PASS@NVR_IP:554/Streaming/Channels/201
Camera 2 sub stream:  rtsp://USER:PASS@NVR_IP:554/Streaming/Channels/202
Camera 3 main stream: rtsp://USER:PASS@NVR_IP:554/Streaming/Channels/301
Camera 3 sub stream:  rtsp://USER:PASS@NVR_IP:554/Streaming/Channels/302
```

## Cursor Build Prompt

Use this prompt in Cursor:

```text
Build this project from spec.md. Start with the MVP. Use Docker Compose with host networking. Avoid transcoding. Implement a configurable ONVIF wrapper that exposes one virtual ONVIF camera per RTSP URL from config.yml. Use environment variables for secrets. Include clear README setup instructions for Raspberry Pi 4 and UniFi Protect. Prioritize practical compatibility with UniFi Protect over full ONVIF completeness.
```
