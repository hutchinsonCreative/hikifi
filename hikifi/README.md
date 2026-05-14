# RTSP-to-ONVIF Virtual Camera Bridge

Lightweight bridge that exposes **one virtual ONVIF camera per RTSP URL** from `config.yml`, so UniFi Protect can discover and add each Hikvision (or other) NVR channel separately. Video is **not transcoded** and, in the default mode, **does not flow through this host**—only discovery and SOAP/ONVIF metadata are served here.

This implementation matches the project specification (`cctvspec.md` in the repository root).

The runnable service lives in the **`hikifi/`** directory next to that file; all commands below assume your shell is **inside** `hikifi/` (not the repo root unless they are the same).

## Why Python?

The service is **Python 3.10+** with [aiohttp](https://docs.aiohttp.org/) and [PyYAML](https://pyyaml.org/). Wheels are published for **macOS (x86_64 and arm64)** and **Linux (including Raspberry Pi / aarch64)**, so you normally avoid native compilation. The same code runs on your Mac for testing and on a Pi in production.

## Quick start (Mac or Raspberry Pi)

1. Install Python 3.10 or newer (e.g. from [python.org](https://www.python.org/downloads/) or your OS package manager).

2. Create a virtual environment and install dependencies:

```bash
cd hikifi
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3. Copy configuration and secrets:

```bash
cp config.example.yml config.yml
cp .env.example .env
# Edit config.yml: set server.advertised_ip to this machine's LAN IP (UniFi must reach it).
# Edit .env: set ONVIF_PASSWORD and any variables referenced in config.yml (${HIK_USER}, etc.).
```

Variables in a `.env` file next to `config.yml` (or in the current working directory) are loaded **automatically** before `config.yml` is read. They do **not** override variables already set in your shell (so `export HIK_USER=...` still wins).

4. Run:

```bash
export PYTHONPATH=.
python -m src.main --config config.yml
```

On startup the service **TCP-probes each camera’s `rtsp_url` host and port** (default 554) and logs **OK** or **FAILED** per camera, plus a short summary. That confirms routing/firewall from this host to the NVR; it does **not** validate RTSP credentials or the stream path. Disable with `server.rtsp_connectivity_check_enabled: false` in `config.yml` if you do not want these checks.

5. Check health (default admin port **8090**):

```bash
curl -s http://127.0.0.1:8090/health | python -m json.tool
```

ONVIF HTTP ports start at `onvif_http_port_start` (default **8081**), one port per camera.

## UniFi Protect notes

- Set `server.advertised_ip` to the **LAN IP UniFi Protect uses to reach this host** (often the Pi or Mac’s address). WS-Discovery `XAddrs` and stream metadata use this address.
- **Multiple cameras on one IP:** UniFi’s device list often **merges** every virtual ONVIF endpoint that shares the same **advertised host** into **one row**, even when ports differ. You can see a **mismatched name/model** (for example discovery text from one camera and `GetDeviceInformation` from another). To get **one adoption row per stream**, give each camera its own **LAN address** on this machine (secondary IPs / aliases), and set optional **`cameras[].advertised_ip`** per entry to those addresses. The service still **listens** on `server.bind_ip` and the usual ONVIF ports; only the URLs in discovery and SOAP change. Ensure each alias is configured on the OS before Protect scans.
- Use the ONVIF username from `security.onvif_username` and the password from your `.env` (`ONVIF_PASSWORD` by default).
- UniFi sends **WS-Security UsernameToken** requests with **PasswordDigest**; this bridge validates that digest against `ONVIF_PASSWORD`.
- If Protect refuses to use the **direct Hikvision RTSP URL** returned by `GetStreamUri`, set `mode.restream_enabled: true` and run **MediaMTX** (see below).

### Live view shows one frame then keeps loading

Video goes **Protect ↔ NVR** directly; this bridge only supplies the RTSP URL. A single decoded frame with endless buffering usually means **RTSP control on TCP port 554 works** (so you get metadata / first picture) but **RTP media** (often **UDP** from NVR toward the Protect appliance) is **blocked, NAT-unfriendly, or not what Protect expects**.

Things to try (in order):

1. **Firewall / VLANs** — Allow **UDP** (and any dynamic RTP ports your NVR documents) from **NVR → Protect** (and sometimes the reverse path), not only TCP 554.
2. **Sub stream** — Point `rtsp_url` at a **sub** channel (e.g. Hikvision `.../Channels/102` instead of `101`) for lower bitrate; some Protect builds are happier.
3. **`mode.rtsp_stream_uri_suffix`** — Set to `?tcp` (or whatever your NVR docs recommend) so `GetStreamUri` returns a URL with that query. Not all firmware honors it; harmless to try.
4. **MediaMTX restream** — Enable `mode.restream_enabled` and run MediaMTX so Protect talks to **one TCP-friendly** RTSP endpoint on the Pi while MediaMTX pulls from the NVR (often with TCP toward the NVR). This is the most reliable fix when direct RTP/UDP is the problem.

## Docker Compose (recommended on Pi)

Host networking is used so **WS-Discovery multicast (UDP 3702)** works reliably.

```bash
cp config.example.yml config.yml
cp .env.example .env
# Edit files as above, then:
docker compose up --build -d
```

Mount your real `config.yml` and `.env` as in `docker-compose.yml`.

## Optional MediaMTX restream

1. Set `mode.restream_enabled: true` and `mode.mediamtx_base_url` (e.g. `rtsp://192.168.x.x:8554` where MediaMTX listens).

2. Generate a starter MediaMTX config from the same camera list:

```bash
export PYTHONPATH=.
python scripts/generate_mediamtx_config.py --config config.yml --output mediamtx.generated.yml
```

3. Review and install paths, then run MediaMTX (see `docker-compose.yml` commented service or upstream docs).

## Development tests

```bash
export PYTHONPATH=.
pytest
```

## Ports and firewall

- **UDP 3702**: WS-Discovery (multicast `239.255.255.250`); required for automatic discovery.
- **TCP `onvif_http_port_start` … `onvif_http_port_start + N - 1`**: ONVIF SOAP per virtual camera.
- **TCP `admin_port`**: `/health`, `/cameras`, `/debug/discovery`, `/debug/activity`, **`/debug/rtsp`** (no secrets in JSON; RTSP URLs are redacted). **`/debug/activity`** shows per virtual camera whether any ONVIF client has sent SOAP yet and WS-Discovery announcement counts. **`/debug/rtsp`** shows the last **TCP reachability** result toward each camera’s `rtsp_url` host:port (startup check; not a full RTSP auth test).

## Security

- Never commit `.env` or real `config.yml` with secrets.
- Prefer a dedicated low-privilege RTSP user on the NVR and a dedicated ONVIF password for Protect.
