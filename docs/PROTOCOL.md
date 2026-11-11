# Z-IOT / X5 Camera Protocol — Verified Notes

Independent interoperability notes for **X5 / X5Mini Z-IoT-Cam** Wi-Fi cameras
(`ZIOTA_…` BLE names, firmware `TXW817_A_V1.0.11.84`). All findings below were
verified live against the vendor infrastructure from this project — no vendor
source, no firmware was modified.

> Cross-reference: [franciszekzak/open-ziot](https://github.com/franciszekzak/open-ziot)
> documents the same camera protocol independently (MIT). This document adds
> verification against the live vendor servers and the app-side JSON channel.

---

## 1. Infrastructure map (verified via DNS + TCP probes)

| Purpose | Endpoint | Port | Status |
|---|---|---|---|
| **Camera signaling (binary)** | `sig.gps555.net` | TCP 8882 | ✅ replies `0x8000` |
| **Camera signaling (binary)** | `ipc.gps555.net`, `ipc.gps666.net`, `ws.gps555.net` | TCP 8882 | ✅ replies `0x8000` |
| **App WebSocket (JSON)** | `ws.gps555.net/ws` | 7080, 7090 | ✅ HTTP 101 upgrade |
| **App WebSocket (JSON)** | `ipc.gps666.net/ws` | 7080, 7090 | ✅ HTTP 101 upgrade |
| **REST API** | `http://ipc.gps555.net/api/v1/…` | 80 | ✅ JSON | 
| **REST API (alt)** | `http://ipc.gps666.net/api/v1/…` | 80 | ✅ JSON |
| **STUN** | `stun.gps555.net` / `stunaddr.gps555.net` | UDP 13478 | ✅ RFC 5389 |
| **Cloud media relay** | returned in login reply | TCP 554 + UDP 10000 | assigned per login |
| **Cloud signaling backup** | returned in login reply | TCP 8885 | assigned per login |

The `gps555.net` and `gps666.net` domains resolve to Alibaba Cloud (Hangzhou)
load-balanced instances. Relay IPs rotate per login.

---

## 2. Camera → server signaling — BINARY (verified, working)

This is the protocol the **camera** speaks to the signaling server. It is the
one implemented in `ziota_adapter.py` (`signaling_login()`), and verified live.

### 2.1 Frame format (cloud signaling)

```
86 86 | u16(command) | u16(UID length + body length)
u16(sequence) | u16(UID length) | UID bytes | body | u8(XOR) | 0D
```

* All multi-byte fields are **big-endian**.
* `XOR` = XOR of every preceding byte in the frame (magic .. body).
* `0D` = frame terminator.
* The same framing (without command/UID) is used for the BLE provisioning frame.

### 2.2 Login (command `0x0001`)

Body = firmware string (ASCII), e.g. `TXW817_A_V1.0.11.84`.

Verified request (UID `ZIOTA_ABCDEFGHIJ`):

```
8686 0001 0021 0001 0012 5a494f54415f4142434445464748494a 5458573831375f415f56312e302e31312e3834 <xor> 0d
```

### 2.3 Login reply (command `0x8000`) — VERIFIED 94-byte payload

```
u16(login sequence)                 = echoed request sequence
char[20] relay IPv4 ASCII, NUL-pad  e.g. "156.246.16.114"
u16(relay port)                     = 554
u16(media port)                     = 10000
char[32] STUN host ASCII, NUL-pad   e.g. "stun.gps555.net"
u16(STUN port)                      = 13478
char[32] cloud IPv4 ASCII, NUL-pad  signaling backup
u16(cloud port)                     = 8885
u8(XOR) u8(0x0D)
```

Verified live results (three independent signaling servers, same UID):

| Server | relay_ip:port | media | STUN | cloud:port |
|---|---|---|---|---|
| `sig.gps555.net:8882`   | `156.246.16.114:554` | 10000 | `stun.gps555.net:13478` | `47.110.77.193:8885`  |
| `ipc.gps555.net:8882`   | `120.26.121.165:554` | 10000 | `stun.gps555.net:13478` | `120.26.121.165:8885` |
| `ipc.gps666.net:8882`   | `47.97.191.214:554`  | 10000 | `stun.gps555.net:13478` | `47.97.191.214:8885`  |

**Key finding:** The signaling server accepts **any syntactically valid UID** and
issues a relay assignment — there is no cryptographic authentication at this
stage. Routing to a real camera still requires the camera's genuine UID (from
the BLE advertising name) to be online.

### 2.4 Post-login control flow & media (from open-ziot reference source)

The following is reconstructed from the MIT-licensed open-ziot `server/`
reference implementation and matches the verified field layout in §2.3. The
media layer (RTP/JPEG) itself is not yet live-verified here (no camera), but the
control framing is internally consistent with the verified login reply.

Control codes seen on the same TCP signaling connection (big-endian, same frame):

| Direction | Command | Meaning / body |
|---|---|---|
| camera → server | `0x0001` | Login; body = firmware string |
| server → camera | `0x8000` | Login reply (relay/STUN, see §2.3) |
| camera → server | `0x0021` | Time request |
| server → camera | `0x8021` | Time reply; body = `u32` unix seconds |
| camera → server | `0x0002` | Ready / start |
| server → camera | `0x8001` | Generic ACK; body = `u16(cseq) u16(cmd) u8(0)` |
| server → camera | `0x8002` | Keepalive (every ~10 s) |
| server → camera | `0x9003` | **Send media here**; body = `char[20] public_ip` + `u16 rtp_port` |
| server → camera | `0x8005` | Relay start / retry trigger (if no frames > 15 s) |
| camera → server | `0x0004` | Camera properties (opaque hex) |
| camera → server | `0x1301` / `0x1201` | Control responses |
| camera → server | any `< 0x8000` | ACKed with `0x8001(cseq, cmd, 0)` |

Flow: login (`0x0001`) → server replies `0x8000` → camera sends STUN binding to
`stun_port` (UDP) and `0x0021`/`0x0002` → server starts maintenance and sends
`0x9003` telling the camera the public IP + RTP port to stream to → camera sends
RTP to that UDP port → server keepalives with `0x8002`, retries `0x8005`.

### 2.5 Media — RTP/JPEG + PCMU

On the RTP UDP port (the `media_port` / `rtp_port` from the login reply):

| Stream | RTP payload type | Format |
|---|---|---|
| Video | **26** | RFC 2435 JPEG, fragmented; reassembled into a full JPEG |
| Audio | **0** | PCMU / G.711 µ-law |

Both share one SSRC. JPEG fragment header (after the 12-byte RTP header):
`u8(type-specific=0) u24(fragment offset) u8(type) u8(Q) u8(width/8) u8(height/8)`,
then 128 bytes of quantization tables on the first fragment (offset 0), then the
entropy-coded scan bytes. The RTP marker bit marks the last fragment. The JPEG
Huffman tables are **not** in the stream — the receiver supplies the standard
tables. They are bundled (`jpeg-huffman.bin` via `rtp_receiver.default_dht()`),
so frames decode out of the box (override with `load_dht_from_jpeg(ref.jpg)`).

This project ships a transport-agnostic decoder: `rtp_receiver.py`
(`parse_rtp`, `JpegRtpReceiver`) and `media_receiver.py` (`MediaReceiver`, UDP
socket → reassembly → latest JPEG + snapshots + audio buffer). Both are
unit-tested with synthetic RTP packets; full-frame decode needs the standard DHT
and a live feed.

---

## 3. App → server signaling — JSON over WebSocket

The companion app (`com.flu.flutter_wifi_camera`, Flutter/Dart AOT) uses a
separate JSON channel. Extracted from `lib/arm64-v8a/libapp.so`:

| Item | Value |
|---|---|
| WS endpoints | `ws://ws.gps555.net:7080/ws`, `:7090/ws`, `ws://ipc.gps666.net:7080/ws` |
| Envelope fields | `msgType`, `cmdType`, `deviceId`, `sequence`, `sessionId` |
| `msgType` values | `Register`, `CONNECT`, `KeepAlive`, `Stream`, `Response` (also lowercase: `register`, `connect`, `keepAlive`, `stream`, `snapshot`) |
| App controller methods | `requestSendHeart`, `requestSendRelay`, `requestSendConnectState`, `requestSendCmd`, `requestSendEvent`, `requestSendOTA`, `requestSendStop` |
| Enum | `CameraCMDType` |

**Status:** The endpoint upgrades to WebSocket (HTTP 101). The server closes or
ignores frames until a valid `Register` for an online/known `deviceId` is sent;
a synthetic test UID receives no reply. The exact `Register` body and any
per-message signing have **not** been recovered. This channel is app-only and is
**not needed** for camera control via the binary signaling in §2.

---

## 4. REST API surface (`http://ipc.gps555.net/api/v1/…`, verified)

Auth scheme: `Authorization: Bearer <token>`. `/api/v1/login` returns a generic
`{"code":400,"msg":"common error"}` for every body shape tested (empty, real
credentials, wrong credentials, extra fields) — i.e. the request is rejected on
**format/signature** before credentials are checked. Account/password fields are
`account`, `password` (+ `loginType`, `deviceType`); a request signer (MD5,
`_signPrefix`/`_signSuffix` in the AOT) is applied but its constant is not yet
recovered.

Endpoints discovered in `libapp.so` (all under `/api`):

```
/v1/login
/v1/sys-user            /v1/sys-user/get-info   /v1/sys-user/register
/v1/sys-user/bind       /v1/sys-user/bind-info  /v1/sys-user/check-email
/v1/sys-user/check-username /v1/sys-user/find-pass /v1/sys-user/reset-pwd
/v1/sys-user/set-pwd    /v1/sys-user/send-mob-code /v1/sys-user/register-guest
/v1/ipc/bind            /v1/ipc/unbind          /v1/ipc/run-info
/v1/ipc/reset-pwd       /v1/ipc/set-pwd         /v1/ipc/send-code
/v1/ipc/stun-addr       /v1/ipc/send-stun-addr
/v1/ipc/notify-live-event
/v1/ipc-function         /v1/ipc-function/get-sig-ip
/v1/ipc-function/upload-file  /v1/ipc-function/image/
/v1/ipc-function/ad-global-switch
/v1/ipc-event/single     /v1/ipc-event/event-day  /v1/ipc-event/soft-delete
/v1/ipc-event/batch-oss-signed-url
/v1/cmd/send-cmd         /v1/cmd/get-response
/v1/firmware-version     /v1/firmware-version/progress
/v1/family/add-ipc       /v1/family/unbind-ipc
/v1/cloud-service-record/account-package
/v1/cloud-service-record/current-package
/v1/share-list           /v1/share-list/by-code
/v1/dict/data            /v1/dict/type           /v1/dict-data/option-select-multi
/v1/feedback-application /v1/feedback-session
/v1/ip/get-country       /v1/lang/
```

* `GET /api/v1/ipc/stun-addr` → `{"code":401,"msg":"common error"}` (needs token).
* `GET /api/v1/ipc/send-stun-addr` → `{"requestId":…,"code":500,"msg":"Invalid input provided","status":"error","data":null}` (open, but requires specific params/body not yet recovered).

---

## 5. STUN (verified)

`stun.gps555.net:13478` / `stunaddr.gps555.net:13478`, RFC 5389.

```
Request : Binding Request  (type 0x0001, magic 0x2112A442)
Response: Binding Success  (type 0x0101)
          XOR-MAPPED-ADDRESS attribute (0x0020) → public_ip:public_port
```

Verified public address sample: `147.78.241.156:59666`. Use this to learn the
NAT mapping before contacting the relay.

---

## 6. BLE provisioning (from open-ziot docs; not exercised here — no BLE stack)

Advertising name: `ZIOTA_<device ID>`.

| GATT | UUID |
|---|---|
| Service | `36000001-0001-0002-0003-010203040506` |
| Write (with response) | `36000002-0001-0002-0003-010203040506` |
| Notify | `36000003-0001-0002-0003-010203040506` |

Provisioning frame:

```
86 86 | u16(body length + 5) | u16(sequence) | u16(body length)
body | u8(XOR) | 0D

body:
  u16(command = 1)
  u8(SSID length),   SSID bytes       (max 32)
  u8(password len),  password bytes   (max 64)
```

GATT writes are split into 20-byte chunks, each awaited, ~150 ms apart. The
device ID in the advertising name (`ZIOTA_<id>`) is the UID used in §2.

---

## 7. Reproducing the verification

```bash
cd iwfcam4hermes
python3 - <<'PY'
from ziota_adapter import ZIOTAdapter
a = ZIOTAdapter(uid="ZIOTA_ABCDEFGHIJ", firmware="TXW817_A_V1.0.11.84")
print(a.signaling_login("sig.gps555.net", 8882))
PY
```

Manual raw check:

```bash
python3 - <<'PY'
import socket
from ziota_adapter import build_login_frame
f = build_login_frame("ZIOTA_ABCDEFGHIJ", "TXW817_A_V1.0.11.84", 1)
s = socket.create_connection(("sig.gps555.net", 8882), timeout=8)
s.sendall(f); print(s.recv(4096).hex()); s.close()
PY
```

---

## 8. What is NOT verified / known limits

* Media framing (RTP/JPEG PT26 video + PCMU PT0 audio) — reconstructed from the
  open-ziot reference source and structurally consistent, but **not live-verified**
  against a real camera here (no device on the relay).
* Full JPEG decode requires the standard Huffman tables (not carried in RTP).
* App JSON `Register` body and any per-message signature — not recovered.
* REST request signer constants (`_signPrefix` / `_signSuffix` MD5) — not recovered.
* Whether a UID other than the camera's own can receive its stream (relay
  likely binds media to the logged-in UID + online camera).
* 1080p mode (open-ziot reports only 640×480 verified).
* BLE provisioning was not exercised here (container has no usable BLE stack).

These are documented as open, not assumed.
