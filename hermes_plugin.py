#!/usr/bin/env python3
"""Hermes-Plugin-Einstiegspunkt für iwfcam4hermes.

Zwei Nutzungswege:

* **Als Verzeichnis-Plugin** lädt Hermes ``iwfcam4hermes/__init__.py`` und ruft
  dort ``register(ctx)`` auf. ``hermes_plugin.py`` ist dann nur die
  objektorientierte Fassade (z. B. für Skripte und die Dashboard-API).
* **Direkt** per ``python3 -m iwfcam4hermes.hermes_plugin <config.json>`` oder
  ``python3 -m iwfcam4hermes.plugin <befehl>``.

Die Samba-/MiniDLNA-Funktionen sind in :mod:`iwfcam4hermes.services` implementiert
(kein externer Pfad, keine Fremdabhängigkeit).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .manager import CameraManager
from .plugin import Camera, CameraType, fetch_snapshot, load_config

__all__ = [
    "HermesPlugin",
    "create_plugin",
    "register",
    "CameraManager",
    "Camera",
    "CameraType",
    "load_config",
    "fetch_snapshot",
]

_PLUGIN_ROOT = Path(__file__).resolve().parent


def _default_config_path() -> Path:
    """Kamera-Konfiguration finden (gemeinsame Auflösung aus :mod:`config_store`)."""
    from .config_store import resolve_config_path

    return resolve_config_path()


class HermesPlugin:
    """Hermes-kompatible Plugin-Fassade (Kameras + Dienste)."""

    name = "iwfcam4hermes"
    version = "0.11.0"
    description = "WiFi-Kamera-Verwaltung (iWFCam & Z-IOT) + Samba/MiniDLNA-Dienste"

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path).expanduser() if config_path else _default_config_path()
        self.manager = CameraManager(self.config_path)

    # --- Kamera-Methoden ---------------------------------------------------

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

    # --- Status ------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "plugin": self.name,
            "version": self.version,
            "devices": len(self.manager.devices),
            "config": str(self.config_path),
        }


def create_plugin(config_path: str | Path | None = None) -> HermesPlugin:
    """Fassade erzeugen; ohne Argument wird die Standard-Konfiguration benutzt."""
    return HermesPlugin(config_path)


def register(ctx: Any) -> None:
    """Entry-Point-Fallback: identisch zum Paket-Register (``iwfcam4hermes``)."""
    from . import register as _register

    _register(ctx)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0].startswith("-"):
        # Unbekannte Optionen klar melden statt sie als Config-Pfad zu deuten.
        if args[0] in ("-h", "--help"):
            print(__doc__)
            return 0
        print(f"Unbekannte Option: {args[0]}", file=sys.stderr)
        return 2
    plugin = create_plugin(args[0] if args else None)
    print(json.dumps(plugin.status(), indent=2, ensure_ascii=False))
    print(json.dumps(plugin.get_devices(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
