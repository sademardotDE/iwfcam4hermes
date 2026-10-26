#!/usr/bin/env python3
"""Small Hermes-friendly camera plugin scaffold.

This is intentionally conservative: it does not guess the proprietary P2P wire
format. It only loads device metadata from JSON and formats known endpoints.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Any

import requests


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
    url = cam.snapshot_url()
    if not url:
        return False
    try:
        auth = (cam.username, cam.password) if cam.username and cam.password else None
        resp = requests.get(url, auth=auth, timeout=10)
        resp.raise_for_status()
        Path(output_path).write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"Snapshot fetch failed: {e}")
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
        return f"{scheme}://{auth}{endpoint}{self.stream_path}?channel={self.channel}"

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
    raise SystemExit(2)


if __name__ == "__main__":
    raise SystemExit(main())
