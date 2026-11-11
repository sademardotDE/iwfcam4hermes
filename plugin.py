#!/usr/bin/env python3
"""Small Hermes-friendly camera plugin scaffold.

This is intentionally conservative: it does not guess the proprietary P2P wire
format. It only loads device metadata from JSON and formats known endpoints.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Any

import requests


def _http_snapshot(cam: Camera, output_path: str | Path) -> bool:
    """HTTP-Snapshot über ``cam.snapshot_url()``."""
    url = cam.snapshot_url()
    if not url or url.startswith("pppp://"):
        return False
    auth = (cam.username, cam.password) if cam.username and cam.password else None
    resp = requests.get(url, auth=auth, timeout=8)
    resp.raise_for_status()
    Path(output_path).write_bytes(resp.content)
    return Path(output_path).stat().st_size > 0


def _rtsp_frame(cam: Camera, output_path: str | Path) -> bool:
    """Frame aus dem RTSP-Stream (MJPEG) per ffmpeg ziehen."""
    stream = cam.stream_url()
    if not stream.startswith("rtsp://") or not shutil.which("ffmpeg"):
        return False
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-rtsp_transport", "udp",
        "-i", stream, "-frames:v", "1", "-q:v", "2", str(output),
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)
    return output.is_file() and output.stat().st_size > 0


def fetch_snapshot(cam: Camera, output_path: str | Path) -> bool:
    if cam.mock:
        # Generate a minimal valid JPEG placeholder
        # Minimal 1x1 JPEG
        jpeg_bytes = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
            0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
            0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x14, 0x00, 0x01,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x09, 0xFF, 0xC4, 0x00, 0x14, 0x10, 0x01, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00,
            0x7F, 0xFF, 0xD9
        ])
        Path(output_path).write_bytes(jpeg_bytes)
        return True
    # RTSP-Kameras (relay_mode) haben oft keinen HTTP-Snapshot (z. B. AP-Modus) —
    # dort zuerst einen Frame per ffmpeg ziehen, sonst HTTP zuerst.
    attempts = [_rtsp_frame, _http_snapshot] if cam.relay_mode else [_http_snapshot, _rtsp_frame]
    for attempt in attempts:
        try:
            if attempt(cam, output_path):
                return True
        except Exception as exc:  # noqa: BLE001 - nächsten Weg probieren
            print(f"Snapshot via {attempt.__name__} fehlgeschlagen: {exc}")
    return False


class CameraType(str, Enum):
    IWFCAM = "iwfcam"
    ZIOTA = "ziota"
    PPPP = "pppp"


@dataclass(frozen=True)
class Camera:
    id: str
    name: str
    type: CameraType = CameraType.IWFCAM
    uid: str | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    channel: int = 0
    stream_path: str = "/live"
    relay_mode: bool = False
    notes: str = ""
    snapshot_path: str = "/snapshot"
    mock: bool = False

    def stream_endpoint(self) -> str | None:
        if self.host and self.port:
            return f"{self.host}:{self.port}"
        if self.host:
            return self.host
        return None

    def stream_url(self) -> str:
        if self.type == CameraType.PPPP:
            host = self.host or "unknown"
            port = self.port or 32108
            return f"pppp://{host}:{port}"
        endpoint = self.stream_endpoint()
        if not endpoint:
            return ""
        scheme = "rtsp" if self.relay_mode else "http"
        auth = f"{self.username}:{self.password}@" if self.username and self.password else ""
        query = "" if scheme == "rtsp" else f"?channel={self.channel}"
        return f"{scheme}://{auth}{endpoint}{self.stream_path}{query}"

    def snapshot_url(self) -> str:
        if self.type == CameraType.PPPP:
            host = self.host or "unknown"
            port = self.port or 32108
            return f"pppp://{host}:{port}/snapshot"
        endpoint = self.stream_endpoint()
        if not endpoint:
            return ""
        scheme = "http"
        auth = f"{self.username}:{self.password}@" if self.username and self.password else ""
        return f"{scheme}://{auth}{endpoint}{self.snapshot_path}?channel={self.channel}"


def load_config(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    devices = []
    for raw in data.get("devices", []):
        raw.setdefault("type", "iwfcam")
        raw["type"] = CameraType(raw["type"])
        devices.append(Camera(**raw))
    data["devices"] = devices
    return data


def _cmd_list(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    for cam in cfg.get("devices", []):
        print(f"{cam.id}\t{cam.name}\t{cam.stream_endpoint() or '-'}\t{'relay' if cam.relay_mode else 'direct'}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    cam = next((c for c in cfg.get("devices", []) if c.id == args.device), None)
    if cam is None:
        raise SystemExit(f"unknown device: {args.device}")
    print(json.dumps(asdict(cam), ensure_ascii=False, indent=2))
    return 0


def _cmd_stream_url(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    cam = next((c for c in cfg.get("devices", []) if c.id == args.device), None)
    if cam is None:
        raise SystemExit(f"unknown device: {args.device}")
    print(cam.stream_url())
    return 0


def _cmd_snapshot_url(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    cam = next((c for c in cfg.get("devices", []) if c.id == args.device), None)
    if cam is None:
        raise SystemExit(f"unknown device: {args.device}")
    print(cam.snapshot_url())
    return 0


def _cmd_snapshot(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    cam = next((c for c in cfg.get("devices", []) if c.id == args.device), None)
    if cam is None:
        raise SystemExit(f"unknown device: {args.device}")
    ok = fetch_snapshot(cam, args.output)
    if ok:
        print(f"Snapshot saved to {args.output}")
    else:
        raise SystemExit("snapshot fetch failed")
    return 0


def _cmd_signaling_login(args: argparse.Namespace) -> int:
    try:
        from .ziota_adapter import ZIOTAdapter
    except ImportError:
        from ziota_adapter import ZIOTAdapter
    adapter = ZIOTAdapter(uid=args.uid, firmware=args.firmware)
    reply = adapter.signaling_login(host=args.host, port=args.port, timeout=args.timeout)
    if not reply:
        raise SystemExit("signaling login failed")
    print(json.dumps(reply, ensure_ascii=False, indent=2))
    return 0


def _cmd_receiver(args: argparse.Namespace) -> int:
    try:
        from .ziot_receiver import ZiotReceiverServer
        from .rtp_receiver import load_dht_from_jpeg
    except ImportError:
        from ziot_receiver import ZiotReceiverServer
        from rtp_receiver import load_dht_from_jpeg
    dht = load_dht_from_jpeg(args.dht) if args.dht else b""
    srv = ZiotReceiverServer(
        host=args.host, public_ip=args.public_ip,
        signaling_port=args.signaling_port, media_port=args.media_port,
        stun_port=args.stun_port, dht=dht, snapshot_dir=args.snapshots,
    )
    info = srv.start()
    print(json.dumps(info), flush=True)
    try:
        while True:
            time.sleep(5)
            print(json.dumps(srv.media.stats()), flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        srv.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="iwfcam4hermes")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="list cameras")
    p.add_argument("--config", required=True, help="path to JSON config")
    p = sub.add_parser("show", help="show one camera")
    p.add_argument("--config", required=True, help="path to JSON config")
    p.add_argument("--device", required=True)
    p = sub.add_parser("stream-url", help="print a derived stream URL")
    p.add_argument("--config", required=True, help="path to JSON config")
    p.add_argument("--device", required=True)
    p = sub.add_parser("snapshot-url", help="print a derived snapshot URL")
    p.add_argument("--config", required=True, help="path to JSON config")
    p.add_argument("--device", required=True)
    p = sub.add_parser("snapshot", help="fetch a snapshot to a file")
    p.add_argument("--config", required=True, help="path to JSON config")
    p.add_argument("--device", required=True)
    p.add_argument("--output", default="snapshot.jpg", help="output file path")

    p = sub.add_parser("signaling-login", help="camera signaling login (TCP 8882) -> relay/STUN")
    p.add_argument("--uid", required=True, help="camera UID (ZIOTA_...)")
    p.add_argument("--host", default="sig.gps555.net")
    p.add_argument("--port", type=int, default=8882)
    p.add_argument("--firmware", default="TXW817_A_V1.0.11.84")
    p.add_argument("--timeout", type=float, default=10.0)

    p = sub.add_parser("receiver", help="run self-hosted receiver (signaling+STUN+RTP/JPEG)")
    p.add_argument("--public-ip", required=True, help="IP the camera can reach this host at")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--signaling-port", type=int, default=8882)
    p.add_argument("--media-port", type=int, default=10000)
    p.add_argument("--stun-port", type=int, default=13478)
    p.add_argument("--snapshots", default=None, help="directory to auto-save frames")
    p.add_argument("--dht", default=None, help="reference JPEG to extract DHT from")

    args = parser.parse_args(argv)
    if args.cmd == "list":
        return _cmd_list(args)
    if args.cmd == "show":
        return _cmd_show(args)
    if args.cmd == "stream-url":
        return _cmd_stream_url(args)
    if args.cmd == "snapshot-url":
        return _cmd_snapshot_url(args)
    if args.cmd == "snapshot":
        return _cmd_snapshot(args)
    if args.cmd == "signaling-login":
        return _cmd_signaling_login(args)
    if args.cmd == "receiver":
        return _cmd_receiver(args)
    raise SystemExit(2)


if __name__ == "__main__":
    raise SystemExit(main())
