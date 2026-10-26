#!/usr/bin/env python3
"""Hermes plugin entry point for iwfcam4hermes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .plugin import Camera, CameraType, load_config, fetch_snapshot

__all__ = ["CameraManager", "load_config"]


class CameraManager:
    """High-level manager for WiFi cameras in Hermes."""

    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self._config = load_config(self.config_path)
        self.devices: list[Camera] = self._config.get("devices", [])

    def list_devices(self) -> list[dict[str, Any]]:
        return [
            {
                "id": c.id,
                "name": c.name,
                "type": c.type.value,
                "host": c.host,
                "port": c.port,
                "stream_url": c.stream_url(),
                "snapshot_url": c.snapshot_url(),
                "mock": c.mock,
            }
            for c in self.devices
        ]

    def get_device(self, device_id: str) -> Camera | None:
        return next((c for c in self.devices if c.id == device_id), None)

    def snapshot(self, device_id: str, output_path: str | Path) -> bool:
        cam = self.get_device(device_id)
        if not cam:
            return False
        return fetch_snapshot(cam, output_path)

    def stream_url(self, device_id: str) -> str:
        cam = self.get_device(device_id)
        if not cam:
            return ""
        return cam.stream_url()

    def snapshot_url(self, device_id: str) -> str:
        cam = self.get_device(device_id)
        if not cam:
            return ""
        return cam.snapshot_url()

    def reload(self) -> None:
        self._config = load_config(self.config_path)
        self.devices = self._config.get("devices", [])


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m iwfcam4hermes.manager <config.json>")
        sys.exit(1)
    mgr = CameraManager(sys.argv[1])
    print(json.dumps(mgr.list_devices(), indent=2, ensure_ascii=False))
