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


def _safe_uid(uid: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in (uid or "unknown"))


class MediaHub:
    """Ein UDP-MediaReceiver pro Kamera (mehrere Kameras parallel).

    Jede Kamera bekommt beim Login einen eigenen, vom Betriebssystem
    zugewiesenen UDP-Port; der Port landet in der ``0x8000``-Antwort und im
    ``0x9003``-Media-Ziel. Damit können mehrere Kameras gleichzeitig an einen
    Relay streamen.
    """

    def __init__(self, host: str = "0.0.0.0", dht: bytes = b"",
                 snapshot_dir: Optional[str] = None, max_cameras: int = 16):
        self.host = host
        self.dht = dht
        self.snapshot_root = Path(snapshot_dir) if snapshot_dir else None
        self.max_cameras = max(1, int(max_cameras))
        self._lock = threading.RLock()
        self._items: dict[str, dict] = {}

    def acquire(self, uid: str) -> "MediaReceiver":
        """MediaReceiver für *uid* holen (vorhandenen wiederverwenden)."""
        with self._lock:
            entry = self._items.get(uid)
            if entry is not None:
                return entry["media"]
            if len(self._items) >= self.max_cameras:
                self._evict_locked()
            snapshot_dir = (self.snapshot_root / _safe_uid(uid)
                            if self.snapshot_root is not None else None)
            media = MediaReceiver(dht=self.dht, snapshot_dir=snapshot_dir)
            port = media.start(self.host, 0)
            self._items[uid] = {
                "uid": uid,
                "media": media,
                "port": port,
                "created_at": time.time(),
            }
            log.info("media receiver for uid=%s on udp/%d", uid, port)
            return media

    def acquire_port(self, uid: str) -> int:
        """UDP-Port für *uid* (legt den Receiver bei Bedarf an)."""
        with self._lock:
            entry = self._items.get(uid)
            if entry is not None:
                return int(entry["port"])
        self.acquire(uid)
        with self._lock:
            return int(self._items[uid]["port"])

    def _evict_locked(self) -> None:
        if not self._items:
            return
        # Zuerst Kameras ohne Frames, sonst die älteste.
        candidates = sorted(
            self._items.items(),
            key=lambda kv: (kv[1]["media"].stats().get("frames") or 0, kv[1]["created_at"]),
        )
        uid, entry = candidates[0]
        log.info("evicting media receiver uid=%s (max %d cameras)", uid, self.max_cameras)
        try:
            entry["media"].stop()
        except OSError:
            pass
        self._items.pop(uid, None)

    def get(self, uid: str) -> Optional["MediaReceiver"]:
        with self._lock:
            entry = self._items.get(uid)
            return entry["media"] if entry else None

    def first(self) -> Optional["MediaReceiver"]:
        with self._lock:
            for entry in self._items.values():
                return entry["media"]
        return None

    def list(self) -> list[dict]:
        with self._lock:
            entries = list(self._items.values())
        result = []
        now = time.time()
        for entry in entries:
            stats = entry["media"].stats()
            result.append({
                "uid": entry["uid"],
                "created_at": entry["created_at"],
                "uptime_s": round(now - entry["created_at"], 1),
                **stats,
            })
        return result

    def totals(self) -> dict:
        cameras = self.list()
        return {
            "cameras": len(cameras),
            "frames": sum(int(c.get("frames") or 0) for c in cameras),
            "audio_packets": sum(int(c.get("audio_packets") or 0) for c in cameras),
        }

    def stop_all(self) -> None:
        with self._lock:
            entries = list(self._items.values())
            self._items.clear()
        for entry in entries:
            try:
                entry["media"].stop()
            except OSError:
                pass


class SignalingServer:
    """Camera-facing TCP signaling server (subset of the observed protocol)."""

    def __init__(self, host: str, port: int, public_ip: str, rtp_port: int = 0,
                 stun_ip: str = "", stun_port: int = 0,
                 on_login: Optional[Callable[[str, str], None]] = None,
                 media_factory: Optional[Callable[[str], int]] = None):
        self.host = host
        self._requested_port = port
        self.public_ip = public_ip
        self.rtp_port = rtp_port
        self.stun_ip = stun_ip
        self.stun_port = stun_port
        self.on_login = on_login
        self.media_factory = media_factory
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
        media_port = self.rtp_port
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
            log.info("media target -> uid=%s %s:%d", uid, self.public_ip, media_port)
            time.sleep(0.2)
            send(CMD_MEDIA_TARGET, self.public_ip.encode().ljust(20, b"\x00")
                 + struct.pack(">H", media_port))
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
                        if self.media_factory is not None:
                            try:
                                media_port = int(self.media_factory(uid))
                            except Exception:  # noqa: BLE001 - Login nicht deswegen verlieren
                                log.exception("media allocation failed for uid=%s", uid)
                        log.info("signaling login: uid=%s cseq=%d media_port=%d",
                                 uid, cseq, media_port)
                        body = login_reply_body(cseq, self.public_ip, media_port,
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
        self.media_hub = MediaHub(host=host, dht=dht, snapshot_dir=snapshot_dir)
        self.signaling: Optional[SignalingServer] = None
        self._on_login = on_login

    @property
    def media(self) -> Optional[MediaReceiver]:
        """Kompatibilität: erster aktiver MediaReceiver (oder None)."""
        return self.media_hub.first()

    def media_for(self, uid: str) -> Optional[MediaReceiver]:
        return self.media_hub.get(uid)

    def cameras(self) -> list[dict]:
        return self.media_hub.list()

    def start(self) -> dict:
        self._stun_port = self.stun.start()
        self.signaling = SignalingServer(
            self.host, self._signaling_port, public_ip=self.public_ip,
            rtp_port=self._media_port, stun_ip=self.public_ip, stun_port=self._stun_port,
            on_login=self._on_login, media_factory=self.media_hub.acquire_port,
        )
        sig_port = self.signaling.start()
        return {"signaling_port": sig_port, "media_port": 0,
                "stun_port": self._stun_port, "media": "per-camera"}

    def stop(self) -> None:
        if self.signaling:
            self.signaling.stop()
        self.media_hub.stop_all()
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
            logging.info("stats: %s", json.dumps(srv.cameras(), ensure_ascii=False))
    except KeyboardInterrupt:
        pass
    finally:
        srv.stop()
