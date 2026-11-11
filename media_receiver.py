"""UDP media receiver for Z-IOT cameras.

Binds a UDP socket on the RTP port the camera streams to, feeds each datagram to
the RFC 2435 JPEG reassembler (`rtp_receiver.JpegRtpReceiver`), keeps the latest
JPEG frame, buffers recent PCMU audio, and can auto-save snapshots.

Transport-agnostic and testable on loopback without a camera (send synthetic RTP
packets to the bound port).
"""

from __future__ import annotations

import socket
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

try:  # package import (preferred)
    from .rtp_receiver import JpegRtpReceiver, PT_JPEG, PT_PCMU, parse_rtp
except ImportError:  # flat import (running tests inside the dir)
    from rtp_receiver import JpegRtpReceiver, PT_JPEG, PT_PCMU, parse_rtp


class MediaReceiver:
    """Receive, reassemble and expose camera media over UDP/RTP.

    Usage:
        rx = MediaReceiver(dht=load_dht_from_jpeg("ref.jpg"))
        port = rx.start("0.0.0.0", 0)      # 0 -> ephemeral; use the returned port
        ...
        jpeg = rx.latest_jpeg()
        rx.stop()

    `on_frame(jpeg_bytes)` is called from the receive thread for each complete
    frame. If `snapshot_dir` is set, each frame is also written there.
    """

    def __init__(self, dht: bytes = b"", on_frame: Optional[Callable[[bytes], None]] = None,
                 snapshot_dir: Optional[str | Path] = None, audio_buffer: int = 64):
        self._rx = JpegRtpReceiver(dht=dht)
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: Optional[bytes] = None
        self._frames = 0
        self._audio_packets = 0
        self._last_audio: Optional[tuple[int, bytes]] = None
        self._audio: deque = deque(maxlen=audio_buffer)
        self._ssrc: Optional[int] = None
        self._port: Optional[int] = None
        self.on_frame = on_frame
        self.snapshot_dir = Path(snapshot_dir) if snapshot_dir else None
        self._snapshot_counter = 0

    # --------------------------------------------------------------- lifecycle
    def start(self, host: str = "0.0.0.0", port: int = 0) -> int:
        """Bind the UDP socket and start the receive thread. Returns the port."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.settimeout(0.5)
        self._sock = s
        self._port = s.getsockname()[1]
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="media-receiver", daemon=True)
        self._thread.start()
        return self._port

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
            self._thread = None

    @property
    def port(self) -> Optional[int]:
        return self._port

    # ----------------------------------------------------------------- receive
    def _loop(self) -> None:
        while not self._stop.is_set():
            sock = self._sock
            if sock is None:
                break
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            self._handle(data)

    def _handle(self, data: bytes) -> None:
        pkt = parse_rtp(data)
        if pkt is None:
            return

        with self._lock:
            if self._ssrc is None:
                self._ssrc = pkt.ssrc
            elif pkt.ssrc != self._ssrc:
                return  # ignore foreign streams

        if pkt.payload_type == PT_PCMU:
            with self._lock:
                self._audio_packets += 1
                self._last_audio = (pkt.timestamp, pkt.payload)
                self._audio.append((pkt.timestamp, pkt.payload))
            return

        if pkt.payload_type == PT_JPEG:
            image = self._rx.receive(data)
            if image:
                with self._lock:
                    self._latest = image
                    self._frames += 1
                if self.on_frame:
                    try:
                        self.on_frame(image)
                    except Exception:
                        pass
                if self.snapshot_dir:
                    self._write_snapshot(image)

    def _write_snapshot(self, image: bytes) -> None:
        try:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)
            self._snapshot_counter += 1
            name = f"frame_{self._frames:06d}_{self._snapshot_counter:06d}.jpg"
            (self.snapshot_dir / name).write_bytes(image)
        except OSError:
            pass

    # ----------------------------------------------------------------- accessors
    def latest_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._latest

    def save_snapshot(self, path: str | Path) -> Optional[Path]:
        """Write the latest frame to `path`. Returns the path or None if no frame."""
        with self._lock:
            image = self._latest
        if image is None:
            return None
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(image)
        return p

    def latest_audio(self) -> Optional[tuple[int, bytes]]:
        with self._lock:
            return self._last_audio

    def stats(self) -> dict:
        with self._lock:
            return {
                "port": self._port,
                "frames": self._frames,
                "audio_packets": self._audio_packets,
                "width": self._rx.width,
                "height": self._rx.height,
                "ssrc": self._ssrc,
            }

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()
