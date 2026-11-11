#!/usr/bin/env python3
"""Z-IOT camera adapter (STUN/WebSocket based).

Implements the observed open-ziot protocol (https://github.com/franciszekzak/open-ziot)
for compatible X5 / X5Mini Z-IoT-Cam cameras.

Frame format (cloud signaling):
    86 86 | u16(command) | u16(UID length + body length)
    u16(sequence) | u16(UID length) | UID bytes | body | u8(XOR) | 0D

The same framing is used for BLE provisioning:
    86 86 | u16(body length + 5) | u16(sequence) | u16(body length)
    body | u8(XOR of all preceding bytes) | 0D

All multi-byte fields are big-endian.
"""

import json
import logging
import socket
import struct
import time
from typing import Any, Callable, Optional, Tuple

try:  # optional: nur der App-WebSocket-Kanal braucht websocket-client
    import websocket
except ImportError:  # pragma: no cover - abhängig von der Installation
    websocket = None  # type: ignore[assignment]

import threading

log = logging.getLogger("ziota_adapter")


def _websocket_module():
    """``websocket-client`` lazy laden; klare Fehlermeldung statt ImportError beim Plugin-Laden."""
    if websocket is None:
        raise RuntimeError(
            "websocket-client ist nicht installiert (pip install websocket-client); "
            "der App-WebSocket-Kanal ist damit nicht verfügbar. Der binäre "
            "Signalisierungs-Login (signaling_login) benötigt ihn nicht."
        )
    return websocket


# Protocol constants
FRAME_MAGIC = b"\x86\x86"
FRAME_TERMINATOR = b"\x0d"
MAX_UID_LEN = 64
MAX_BODY_LEN = 1024

# Cloud signaling commands
CMD_LOGIN = 0x0001
CMD_LOGIN_REPLY = 0x8000


def xor_bytes(data: bytes) -> int:
    """XOR every byte; returns a single byte value."""
    result = 0
    for b in data:
        result ^= b
    return result & 0xFF


def build_frame(command: int, sequence: int, uid: str, body: bytes = b"") -> bytes:
    """Build any Z-IOT signaling frame (cloud layout).

    Layout:
        86 86 | u16(command) | u16(UID length + body length)
        u16(sequence) | u16(UID length) | UID bytes | body | u8(XOR) | 0D
    """
    uid_bytes = uid.encode("utf-8")
    header = FRAME_MAGIC
    header += struct.pack(">H", command)
    header += struct.pack(">H", len(uid_bytes) + len(body))
    header += struct.pack(">H", sequence)
    header += struct.pack(">H", len(uid_bytes))
    payload = header + uid_bytes + body
    return payload + bytes([xor_bytes(payload)]) + FRAME_TERMINATOR


def build_login_frame(uid: str, firmware: str, sequence: int = 0) -> bytes:
    """Build a cloud signaling login frame (command 1)."""
    return build_frame(CMD_LOGIN, sequence, uid, firmware.encode("utf-8"))


def parse_frame(data: bytes) -> Optional[dict]:
    """Parse a Z-IOT cloud signaling frame.

    Returns a dict with keys: command, sequence, uid, body, raw
    or None if the frame is malformed.
    """
    if len(data) < 8:
        return None
    if data[0:2] != FRAME_MAGIC:
        return None
    if data[-1:] != FRAME_TERMINATOR:
        return None

    # Verify XOR checksum (byte before terminator)
    expected_checksum = data[-2]
    if xor_bytes(data[:-2]) != expected_checksum:
        log.warning("XOR checksum mismatch: got 0x%02x, expect 0x%02x",
                    xor_bytes(data[:-2]), expected_checksum)
        # We continue anyway (some devices may use different XOR scope)

    command = struct.unpack(">H", data[2:4])[0]
    body_and_uid_len = struct.unpack(">H", data[4:6])[0]
    sequence = struct.unpack(">H", data[6:8])[0]

    try:
        uid_len = struct.unpack(">H", data[8:10])[0]
    except struct.error:
        return None

    if uid_len > max(0, len(data) - 10 - 2):
        return None

    uid = data[10:10 + uid_len]
    body = data[10 + uid_len:-(2)]  # exclude checksum + terminator

    return {
        "command": command,
        "sequence": sequence,
        "uid": uid.decode("utf-8", "replace"),
        "body": body,
        "raw": data,
    }


def parse_login_reply(frame: dict) -> Optional[dict]:
    """Parse the server 0x8000 login reply — VERIFIED layout (96-byte body).

    Verified against sig.gps555.net:8882, ipc.gps555.net:8882, ipc.gps666.net:8882:

        u16(login sequence)
        char[20] relay IPv4 ASCII, NUL-padded   (relay media server)
        u16(relay port)        = 554
        u16(media port)        = 10000
        char[32] STUN host ASCII, NUL-padded    (e.g. "stun.gps555.net")
        u16(STUN port)         = 13478
        char[32] cloud IPv4 ASCII, NUL-padded   (signaling / backup)
        u16(cloud port)        = 8885
        u8(XOR) u8(0x0D)
    """
    if frame.get("command") != CMD_LOGIN_REPLY:
        return None
    body = frame["body"]
    # payload = 2+20+2+2+32+2+32+2 = 94 bytes (XOR + 0x0D already stripped by parse_frame)
    if len(body) < 94:
        log.warning("Login reply body too short: %d bytes (expected 94)", len(body))
        return None

    b = 0
    login_seq = struct.unpack(">H", body[b:b + 2])[0]; b += 2
    relay_ip = body[b:b + 20].rstrip(b"\x00").decode("ascii", "replace"); b += 20
    relay_port = struct.unpack(">H", body[b:b + 2])[0]; b += 2
    media_port = struct.unpack(">H", body[b:b + 2])[0]; b += 2
    stun_ip = body[b:b + 32].rstrip(b"\x00").decode("ascii", "replace"); b += 32
    stun_port = struct.unpack(">H", body[b:b + 2])[0]; b += 2
    cloud_ip = body[b:b + 32].rstrip(b"\x00").decode("ascii", "replace"); b += 32
    cloud_port = struct.unpack(">H", body[b:b + 2])[0]; b += 2

    return {
        "login_sequence": login_seq,
        "relay_ip": relay_ip,
        "relay_port": relay_port,
        "media_port": media_port,
        "stun_ip": stun_ip,
        "stun_port": stun_port,
        "cloud_ip": cloud_ip,
        "cloud_port": cloud_port,
    }


class ZIOTAdapter:
    """Adapter for Z-IOT/ZIOTA cameras.

    Implements the observed open-ziot cloud signaling protocol in addition to
    a WebSocket probing layer. The binary frame format is used for real device
    communication; JSON helpers are kept for diagnostics.
    """

    def __init__(self, uid: str, ws_url: str = "ws://ws.gps555.net:7080/ws",
                 firmware: str = "TXW817_A_V1.0.11.84"):
        self.uid = uid
        self.ws_url = ws_url
        self.firmware = firmware
        self.ws: Optional[Any] = None
        self._on_message: Optional[Callable[[dict], None]] = None
        self._heartbeat_thread = None
        self._heartbeat_stop = threading.Event()
        self._sequence = 0
        self.login_reply: Optional[dict] = None

    # ------------------------------------------------------------------ probes
    def test_connection(self, timeout: int = 5) -> bool:
        """Attempt a quick connection test and log result."""
        try:
            ws = _websocket_module().create_connection(self.ws_url, timeout=timeout)
            ws.close()
            log.info("Connection test to %s succeeded", self.ws_url)
            return True
        except Exception as e:
            log.warning("Connection test to %s failed: %s", self.ws_url, e)
            return False

    def discover_public_ip(self) -> tuple[str, int] | None:
        """Use STUN to discover public IP/port."""
        try:
            from .stun_client import stun_binding

            result, err = stun_binding()
            if result:
                log.info("Public address: %s:%s", result[0], result[1])
                return result
            else:
                log.warning("STUN failed: %s", err)
                return None
        except Exception as e:
            log.error("STUN error: %s", e)
            return None

    # -------------------------------------------------------------- connection
    def connect(self, timeout: int = 10) -> bool:
        """Legacy WebSocket connect (app-facing channel, JSON)."""
        try:
            ws_mod = _websocket_module()
            self.ws = ws_mod.create_connection(self.ws_url, timeout=timeout)
            log.info("Connected to %s", self.ws_url)
            frame = self.build_login()
            self.ws.send(frame, ws_mod.ABNF.OPCODE_BINARY)
            log.info("Sent login frame (%d bytes) for UID %s", len(frame), self.uid)
            return True
        except Exception as e:
            log.error("Connection failed: %s", e)
            return False

    def signaling_login(self, host: str = "sig.gps555.net", port: int = 8882,
                        timeout: int = 10) -> Optional[dict]:
        """VERIFIED camera-side signaling login over raw TCP (port 8882).

        Sends the binary 86 86 login frame (command 1, firmware string) and
        parses the 0x8000 reply carrying relay/media/STUN/cloud endpoints.

        Returns the parsed reply dict (relay_ip, relay_port, media_port,
        stun_ip, stun_port, cloud_ip, cloud_port) or None on failure.
        """
        frame = self.build_login(sequence=1)
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            try:
                s.sendall(frame)
                s.settimeout(timeout)
                raw = s.recv(4096)
            finally:
                s.close()
        except Exception as e:
            log.error("Signaling login to %s:%d failed: %s", host, port, e)
            return None

        if not raw or raw[:2] != FRAME_MAGIC:
            log.warning("Signaling reply not a Z-IOT frame: %s", raw[:32].hex() if raw else "empty")
            return None

        parsed = parse_frame(raw)
        if not parsed or parsed["command"] != CMD_LOGIN_REPLY:
            log.warning("Unexpected reply command: %s", parsed and hex(parsed["command"]))
            return None

        reply = parse_login_reply(parsed)
        if reply:
            self.login_reply = reply
            log.info("Signaling login OK: relay=%s:%d media=%d stun=%s:%d cloud=%s:%d",
                     reply["relay_ip"], reply["relay_port"], reply["media_port"],
                     reply["stun_ip"], reply["stun_port"],
                     reply["cloud_ip"], reply["cloud_port"])
        return reply

    def build_login(self, sequence: Optional[int] = None) -> bytes:
        """Build a login frame using the current sequence counter."""
        if sequence is None:
            sequence = self._next_sequence()
        return build_login_frame(self.uid, self.firmware, sequence)

    def _next_sequence(self) -> int:
        self._sequence = (self._sequence + 1) & 0xFFFF
        return self._sequence

    # --------------------------------------------------------------- messaging
    def _send(self, payload: Any) -> None:
        """Send JSON (diagnostic) payload over the WebSocket."""
        if not self.ws:
            return
        if isinstance(payload, bytes):
            self.ws.send(payload, _websocket_module().ABNF.OPCODE_BINARY)
        else:
            self.ws.send(json.dumps(payload))
        log.debug("Sent: %s", payload)

    def _send_frame(self, frame: bytes) -> None:
        if not self.ws:
            return
        self.ws.send(frame, _websocket_module().ABNF.OPCODE_BINARY)
        log.debug("Sent frame: %s", frame.hex())

    def send_login(self) -> None:
        """Send the protocol-correct login frame."""
        self._send_frame(self.build_login())

    def send_heart(self) -> None:
        """Heartbeat (JSON diagnostic path)."""
        self._send({"cmd": "requestSendHeart", "uid": self.uid})

    def send_cmd(self, cmd: str, **kwargs: Any) -> None:
        msg = {"cmd": "requestSendCmd", "uid": self.uid, "cmdType": cmd, **kwargs}
        self._send(msg)

    def request_snapshot(self) -> None:
        self.send_cmd("snapshot")

    def request_stream_start(self) -> None:
        self.send_cmd("streamStart")

    def request_stream_stop(self) -> None:
        self.send_cmd("streamStop")

    def request_relay(self) -> None:
        self.send_cmd("requestSendRelay")

    def request_ota(self) -> None:
        self.send_cmd("requestSendOTA")

    def request_connect_state(self) -> None:
        self.send_cmd("requestSendConnectState")

    def request_event(self, event: str) -> None:
        self.send_cmd("requestSendEvent", event=event)

    # --------------------------------------------------------------- receiving
    def recv(self, timeout: float = 5.0) -> Optional[dict]:
        """Receive and parse one protocol frame (binary) or JSON payload."""
        if not self.ws:
            return None
        self.ws.settimeout(timeout)
        try:
            raw = self.ws.recv()
        except Exception as e:
            log.debug("Recv error/timeout: %s", e)
            return None

        if isinstance(raw, str):
            try:
                data = json.loads(raw)
                log.debug("Recv (json): %s", data)
                return data
            except json.JSONDecodeError:
                log.debug("Recv (text, unparsed): %s", raw)
                return {"raw": raw}

        parsed = parse_frame(raw)
        if parsed:
            log.debug("Recv frame: cmd=0x%04x seq=%d uid=%s body=%d bytes",
                      parsed["command"], parsed["sequence"], parsed["uid"],
                      len(parsed["body"]))
            if parsed["command"] == CMD_LOGIN_REPLY:
                reply = parse_login_reply(parsed)
                if reply:
                    self.login_reply = reply
                    log.info("Login reply: relay=%s:%d stun=%s:%d",
                             reply["relay_ip"], reply["relay_port"],
                             reply["stun_ip"], reply["stun_port"])
            return parsed

        log.debug("Recv (binary, unparsed): %s", raw[:64].hex())
        return {"raw": raw}

    def recv_login_reply(self, timeout: float = 5.0) -> Optional[dict]:
        """Wait for the 0x8000 login reply and return relay/STUN info."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            frame = self.recv(timeout=remaining)
            if frame and isinstance(frame, dict) and frame.get("command") == CMD_LOGIN_REPLY:
                return self.login_reply
        return None

    # -------------------------------------------------------------- heartbeats
    def start_heartbeat(self, interval: float = 30.0) -> None:
        """Start a background heartbeat thread."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_worker, args=(interval,), daemon=True
        )
        self._heartbeat_thread.start()
        log.info("Heartbeat started (interval=%s)", interval)

    def stop_heartbeat(self) -> None:
        """Stop the background heartbeat thread."""
        self._heartbeat_stop.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
            self._heartbeat_thread = None
        log.info("Heartbeat stopped")

    def _heartbeat_worker(self, interval: float) -> None:
        while not self._heartbeat_stop.is_set():
            try:
                self.send_heart()
                log.debug("Heartbeat sent")
            except Exception as e:
                log.error("Heartbeat error: %s", e)
                break
            self._heartbeat_stop.wait(interval)

    # ----------------------------------------------------------------- probing
    def probe_formats(self) -> list[dict]:
        """Try sending protocol-correct frames and various payloads.

        Unlike earlier probes, this starts with the observed open-ziot login
        frame which is what a real X5 camera sends.
        """
        results = []

        # 1. Protocol-correct login frame (priority)
        try:
            login = self.build_login()
            self._send_frame(login)
            log.info("Sent protocol login frame (%d bytes)", len(login))
            time.sleep(1.0)
            try:
                resp = self.ws.recv()
                parsed = parse_frame(resp) if isinstance(resp, bytes) else resp
                results.append({"payload": "login_frame", "response": parsed})
                if isinstance(parsed, dict) and parsed.get("command") == CMD_LOGIN_REPLY:
                    self.login_reply = parse_login_reply(parsed)
                    log.info("Got login reply: %s", self.login_reply)
                    return results
            except Exception as e:
                results.append({"payload": "login_frame", "error": str(e)})
        except Exception as e:
            results.append({"payload": "login_frame", "error": str(e)})

        # 2. Legacy JSON probes (diagnostic)
        json_payloads = [
            {"cmd": "register", "uid": self.uid},
            {"cmd": "requestSendHeart", "uid": self.uid},
            {"cmd": "requestSendCmd", "uid": self.uid, "cmdType": "snapshot"},
        ]
        for p in json_payloads:
            try:
                self._send(p)
                time.sleep(0.5)
                try:
                    resp = self.ws.recv()
                    results.append({"payload": p, "response": resp})
                except Exception as e:
                    results.append({"payload": p, "error": str(e)})
            except Exception as e:
                results.append({"payload": p, "error": str(e)})

        return results

    # --------------------------------------------------------------- lifecycle
    def close(self) -> None:
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", required=True)
    parser.add_argument("--ws-url", default="ws://ws.gps555.net:7080/ws")
    parser.add_argument("--firmware", default="TXW817_A_V1.0.11.84")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)
    adapter = ZIOTAdapter(uid=args.uid, ws_url=args.ws_url, firmware=args.firmware)

    # Demonstrate frame construction
    frame = adapter.build_login()
    print("Login frame hex:", frame.hex())
    print("Frame length:", len(frame), "bytes")

    if adapter.connect():
        print("Connected. Waiting for login reply...")
        reply = adapter.recv_login_reply(timeout=5)
        if reply:
            print(f"Relay: {reply['relay_ip']}:{reply['relay_port']}")
            print(f"STUN:  {reply['stun_ip']}:{reply['stun_port']}")
        else:
            print("No login reply received.")
        adapter.close()
    else:
        print("Failed to connect.")
