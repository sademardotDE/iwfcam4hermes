#!/usr/bin/env python3
"""Z-IOT camera adapter (STUN/WebSocket based)."""

import json
import logging
import time
from typing import Any, Callable, Optional

import websocket

import threading

log = logging.getLogger("ziota_adapter")


class ZIOTAdapter:
    """Minimal adapter for Z-IOT/ZIOTA cameras via WebSocket."""

    def __init__(self, uid: str, ws_url: str = "ws://ws.gps555.net:7080/ws"):
        self.uid = uid
        self.ws_url = ws_url
        self.ws: Optional[websocket.WebSocket] = None
        self._on_message: Optional[Callable[[dict], None]] = None
        self._heartbeat_thread = None
        self._heartbeat_stop = threading.Event()

    def test_connection(self, timeout: int = 5) -> bool:
        """Attempt a quick connection test and log result."""
        try:
            ws = websocket.create_connection(self.ws_url, timeout=timeout)
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

    def connect(self, timeout: int = 10) -> bool:
        try:
            self.ws = websocket.create_connection(self.ws_url, timeout=timeout)
            log.info("Connected to %s", self.ws_url)
            # Send initial handshake / register UID
            self._send({"cmd": "register", "uid": self.uid})
            return True
        except Exception as e:
            log.error("Connection failed: %s", e)
            return False

    def _send(self, payload: dict) -> None:
        if self.ws:
            self.ws.send(json.dumps(payload))
            log.debug("Sent: %s", payload)

    def send_heart(self) -> None:
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

    def recv(self, timeout: float = 5.0) -> Optional[dict]:
        if not self.ws:
            return None
        self.ws.settimeout(timeout)
        try:
            raw = self.ws.recv()
            data = json.loads(raw)
            log.debug("Recv: %s", data)
            return data
        except Exception as e:
            log.debug("Recv error/timeout: %s", e)
            return None

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
        import threading

        while not self._heartbeat_stop.is_set():
            try:
                self.send_heart()
                log.debug("Heartbeat sent")
            except Exception as e:
                log.error("Heartbeat error: %s", e)
                break
            self._heartbeat_stop.wait(interval)

    def probe_formats(self) -> list[dict]:
        """Try sending various payloads and collect responses."""
        results = []
        payloads = [
            {"cmd": "register", "uid": self.uid},
            {"cmd": "requestSendHeart", "uid": self.uid},
            {"cmd": "requestSendCmd", "uid": self.uid, "cmdType": "snapshot"},
            b"\x00\x01\x02\x03",
            b"P2P\x00",
            self.uid.encode(),
        ]
        for p in payloads:
            try:
                if isinstance(p, bytes):
                    self.ws.send(p, websocket.ABNF.OPCODE_BINARY)
                else:
                    self.ws.send(json.dumps(p))
                log.debug("Sent probe: %s", p)
                time.sleep(1)
                try:
                    resp = self.ws.recv()
                    results.append({"payload": p, "response": resp})
                    log.info("Probe %s -> %s", p, resp)
                except Exception as e:
                    results.append({"payload": p, "response": None, "error": str(e)})
                    log.debug("No response for %s: %s", p, e)
            except Exception as e:
                results.append({"payload": p, "error": str(e)})
                log.error("Send failed for %s: %s", p, e)
        return results

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
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)
    adapter = ZIOTAdapter(uid=args.uid, ws_url=args.ws_url)
    if adapter.connect():
        print("Connected. Sending test cmd...")
        adapter.send_cmd("requestSendHeart")
        time.sleep(2)
        print("Received:", adapter.recv())
        adapter.close()
    else:
        print("Failed to connect.")
