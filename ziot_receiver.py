"""Minimal self-hosted Z-IOT receiver (signaling + STUN + RTP media).

This lets a compatible X5 / Z-IoT-Cam stream to *this* host instead of the
vendor cloud, provided the camera has been provisioned (via BLE) with this
host's signaling address and port. It implements the camera-facing side that was
verified in tests/sources:

  * TCP signaling server: accepts login (cmd 1), replies 0x8000 with our public
    IP + RTP port + STUN endpoint, answers time (0x21 -> 0x8021), ready (2 ->
    0x8001 + 0x8002), and sends 0x9003 (media target) + 0x8005 + periodic 0x8002.
  * UDP STUN responder: answers RFC 5389 binding requests with XOR-MAPPED-ADDRESS.
  * RTP media receiver: reassembles JPEG frames (via MediaReceiver) and buffers
    PCMU audio.

It is intentionally minimal and testable without a camera: a simulated client
can connect, log in, and stream synthetic RTP to the announced port.
"""

from __future__ import annotations

import logging
import socket
import struct
import threading
import time
from typing import Callable, Optional

log = logging.getLogger("iwfcam4hermes.ziot_receiver")

try:
    from .ziota_adapter import FRAME_TERMINATOR, build_frame, parse_frame
    from .media_receiver import MediaReceiver
except ImportError:  # flat (tests)
    from ziota_adapter import FRAME_TERMINATOR, build_frame, parse_frame
    from media_receiver import MediaReceiver

CMD_LOGIN = 0x0001
CMD_TIME = 0x0021
CMD_READY = 0x0002
CMD_LOGIN_REPLY = 0x8000
CMD_ACK = 0x8001
CMD_KEEPALIVE = 0x8002
CMD_RELAY = 0x8005
CMD_MEDIA_TARGET = 0x9003
CMD_TIME_REPLY = 0x8021


def login_reply_body(cseq: int, public_ip: str, rtp_port: int,
                     stun_ip: str, stun_port: int, cloud_ip: str, cloud_port: int) -> bytes:
    """Build the verified 94-byte 0x8000 body."""
    return (
        struct.pack(">H", cseq)
        + public_ip.encode().ljust(20, b"\x00") + b"\x00\x00"
        + struct.pack(">H", rtp_port)
        + stun_ip.encode().ljust(32, b"\x00")
        + struct.pack(">H", stun_port)
        + cloud_ip.encode().ljust(32, b"\x00")
        + struct.pack(">H", cloud_port)
    )


class SignalingServer:
    """Camera-facing TCP signaling server (subset of the observed protocol)."""

    def __init__(self, host: str, port: int, public_ip: str, rtp_port: int,
                 stun_ip: str, stun_port: int,
                 on_login: Optional[Callable[[str, str], None]] = None):
        self.host = host
        self._requested_port = port
        self.public_ip = public_ip
        self.rtp_port = rtp_port
        self.stun_ip = stun_ip
        self.stun_port = stun_port
        self.on_login = on_login
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._conns: set[socket.socket] = set()
        self._lock = threading.Lock()
        self.port: Optional[int] = None

    def start(self) -> int:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self._requested_port))
        s.listen(8)
        s.settimeout(0.5)
        self._sock = s
        self.port = s.getsockname()[1]
        self._thread = threading.Thread(target=self._accept_loop, name="ziot-signaling", daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            for c in list(self._conns):
                try:
                    c.close()
                except OSError:
                    pass
            self._conns.clear()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._thread:
            self._thread.join(timeout=2)

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            sock = self._sock
            if sock is None:
                break
            try:
                conn, _addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                self._conns.add(conn)
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        seq = 0
        uid = ""
        maint_started = False
        write_lock = threading.Lock()

        def send(cmd: int, body: bytes = b"") -> None:
            nonlocal seq
            seq = (seq + 1) & 0xFFFF
            frame = build_frame(cmd, seq, uid, body)
            with write_lock:
                try:
                    conn.sendall(frame)
                except OSError:
                    pass

        def maintain() -> None:
            # Tell the camera where to stream media, then keepalive.
            log.info("media target -> uid=%s %s:%d", uid, self.public_ip, self.rtp_port)
            time.sleep(0.2)
            send(CMD_MEDIA_TARGET, self.public_ip.encode().ljust(20, b"\x00")
                 + struct.pack(">H", self.rtp_port))
            time.sleep(0.2)
            send(CMD_RELAY)
            while not self._stop.is_set():
                time.sleep(10)
                send(CMD_KEEPALIVE)

        buf = b""
        try:
            conn.settimeout(1.0)
            while not self._stop.is_set():
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                buf += data
                while len(buf) >= 10:
                    if buf[:2] != b"\x86\x86":
                        return
                    cmd, length, cseq, uidlen = struct.unpack(">HHHH", buf[2:10])
                    total = length + 12
                    if length > 2048 or total < 12:
                        return
                    if len(buf) < total:
                        break
                    frame, buf = buf[:total], buf[total:]
                    parsed = parse_frame(frame)
                    if parsed is None or parsed["uid"] != uid and uid:
                        continue
                    uid = parsed["uid"]

                    if cmd == CMD_LOGIN:
                        log.info("signaling login: uid=%s cseq=%d", uid, cseq)
                        body = login_reply_body(cseq, self.public_ip, self.rtp_port,
                                                self.stun_ip, self.stun_port,
                                                self.public_ip, 0)
                        send(CMD_LOGIN_REPLY, body)
                        if self.on_login:
                            fw = parsed["body"].rstrip(b"\x00").decode("ascii", "replace")
                            try:
                                self.on_login(uid, fw)
                            except Exception:
                                pass
                    elif cmd == CMD_TIME:
                        log.info("signaling time request: uid=%s cseq=%d", uid, cseq)
                        send(CMD_TIME_REPLY, struct.pack(">I", int(time.time())))
                    elif cmd == CMD_READY:
                        log.info("signaling ready: uid=%s cseq=%d", uid, cseq)
                        send(CMD_ACK, struct.pack(">HHB", cseq, cmd, 0))
                        send(CMD_KEEPALIVE)
                    elif cmd < 0x8000:
                        send(CMD_ACK, struct.pack(">HHB", cseq, cmd, 0))

                    if cmd in (CMD_TIME, CMD_READY) and not maint_started:
                        maint_started = True
                        threading.Thread(target=maintain, daemon=True).start()
        finally:
            with self._lock:
                self._conns.discard(conn)
            try:
                conn.close()
            except OSError:
                pass


class StunResponder:
    """Minimal RFC 5389 STUN responder (Binding Request -> XOR-MAPPED-ADDRESS)."""

    def __init__(self, host: str, port: int):
        self.host = host
        self._requested_port = port
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.port: Optional[int] = None

    def start(self) -> int:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((self.host, self._requested_port))
        s.settimeout(0.5)
        self._sock = s
        self.port = s.getsockname()[1]
        self._thread = threading.Thread(target=self._loop, name="ziot-stun", daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            sock = self._sock
            if sock is None:
                break
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            if len(data) >= 20 and data[0:2] == b"\x00\x01":
                try:
                    sock.sendto(self._binding_success(data, addr), addr)
                except OSError:
                    pass

    @staticmethod
    def _binding_success(request: bytes, addr) -> bytes:
        tid = request[8:20]
        ip = socket.inet_aton(addr[0])
        xport = addr[1] ^ 0x2112
        xip = bytes(a ^ b for a, b in zip(ip, b"\x21\x12\xa4\x42"))
        attr = struct.pack(">HH", 0x0020, 8) + b"\x00\x01" + struct.pack(">H", xport) + xip
        return struct.pack(">HH", 0x0101, len(attr)) + b"\x21\x12\xa4\x42" + tid + attr


class ZiotReceiverServer:
    """Ties signaling + STUN + media into one runnable receiver."""

    def __init__(self, host: str = "0.0.0.0", public_ip: str = "127.0.0.1",
                 signaling_port: int = 0, media_port: int = 0, stun_port: int = 0,
                 dht: bytes = b"", snapshot_dir: Optional[str] = None,
                 on_login: Optional[Callable[[str, str], None]] = None):
        self.host = host
        self.public_ip = public_ip
        self._signaling_port = signaling_port
        self._media_port = media_port
        self._stun_port = stun_port
        self.stun = StunResponder(host, stun_port)
        self.media = MediaReceiver(dht=dht, snapshot_dir=snapshot_dir)
        self.signaling: Optional[SignalingServer] = None
        self._on_login = on_login

    def start(self) -> dict:
        self._stun_port = self.stun.start()
        self._media_port = self.media.start(self.host, self._media_port)
        self.signaling = SignalingServer(
            self.host, self._signaling_port, public_ip=self.public_ip,
            rtp_port=self._media_port, stun_ip=self.public_ip, stun_port=self._stun_port,
            on_login=self._on_login,
        )
        sig_port = self.signaling.start()
        return {"signaling_port": sig_port, "media_port": self._media_port,
                "stun_port": self._stun_port}

    def stop(self) -> None:
        if self.signaling:
            self.signaling.stop()
        self.media.stop()
        self.stun.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()


if __name__ == "__main__":
    import argparse
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Self-hosted Z-IOT receiver")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--public-ip", required=True,
                    help="IP the camera can reach this host at (LAN or public IPv4)")
    ap.add_argument("--signaling-port", type=int, default=8882)
    ap.add_argument("--media-port", type=int, default=10000)
    ap.add_argument("--stun-port", type=int, default=13478)
    ap.add_argument("--snapshots", default=None, help="directory to auto-save frames")
    ap.add_argument("--dht", default=None, help="reference JPEG to extract DHT from")
    args = ap.parse_args()

    dht = b""
    if args.dht:
        try:
            from rtp_receiver import load_dht_from_jpeg
        except ImportError:
            from .rtp_receiver import load_dht_from_jpeg
        dht = load_dht_from_jpeg(args.dht)

    def _on_login(uid, fw):
        logging.info("camera login: uid=%s firmware=%s", uid, fw)

    srv = ZiotReceiverServer(
        host=args.host, public_ip=args.public_ip,
        signaling_port=args.signaling_port, media_port=args.media_port,
        stun_port=args.stun_port, dht=dht, snapshot_dir=args.snapshots,
        on_login=_on_login,
    )
    ports = srv.start()
    logging.info("receiver up: signaling=%d media=%d stun=%d public_ip=%s",
                 ports["signaling_port"], ports["media_port"], ports["stun_port"], args.public_ip)
    logging.info("provision the camera (BLE) to signaling host %s port %d, then Ctrl-C",
                 args.public_ip, ports["signaling_port"])
    try:
        while True:
            time.sleep(5)
            logging.info("stats: %s", srv.media.stats())
    except KeyboardInterrupt:
        pass
    finally:
        srv.stop()
