#!/usr/bin/env python3
"""Hermes plugin entry point for iwfcam4hermes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .manager import CameraManager
from .plugin import Camera, CameraType, load_config, fetch_snapshot
from .ziota_adapter import ZIOTAdapter
from .iwfcam_adapter import IWFCamAdapter
from .iwfcam_p2p import IWFCamP2P
from .stream_proxy import StreamProxy
from .stun_client import stun_binding

__all__ = [
    "HermesPlugin",
    "CameraManager",
    "Camera",
    "CameraType",
    "load_config",
    "fetch_snapshot",
    "ZIOTAdapter",
    "IWFCamAdapter",
    "IWFCamP2P",
    "StreamProxy",
    "stun_binding",
]


class HermesPlugin:
    """Hermes-compatible plugin wrapper."""

    name = "iwfcam4hermes"
    version = "0.2.0"
    description = "WiFi camera management plugin (iWFCam & Z-IOT)"

    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self.manager = CameraManager(self.config_path)

    def get_devices(self) -> list[dict[str, Any]]:
        return self.manager.list_devices()

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        cam = self.manager.get_device(device_id)
        if not cam:
            return None
        return {
            "id": cam.id,
            "name": cam.name,
            "type": cam.type.value,
            "host": cam.host,
            "port": cam.port,
            "stream_url": cam.stream_url(),
            "snapshot_url": cam.snapshot_url(),
            "mock": cam.mock,
        }

    def snapshot(self, device_id: str, output_path: str | Path) -> bool:
        return self.manager.snapshot(device_id, output_path)

    def stream_url(self, device_id: str) -> str:
        return self.manager.stream_url(device_id)

    def snapshot_url(self, device_id: str) -> str:
        return self.manager.snapshot_url(device_id)

    def reload(self) -> None:
        self.manager.reload()

    def status(self) -> dict[str, Any]:
        return {
            "plugin": self.name,
            "version": self.version,
            "devices": len(self.manager.devices),
            "config": str(self.config_path),
        }


def create_plugin(config_path: str | Path) -> HermesPlugin:
    return HermesPlugin(config_path)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: hermes_plugin.py <config.json>")
        sys.exit(1)
    plugin = create_plugin(sys.argv[1])
    print(json.dumps(plugin.status(), indent=2))
    print(json.dumps(plugin.get_devices(), indent=2))
