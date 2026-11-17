"""USB-Smart-Dashboard-Anbindung: Erkennung + Bild-Bridge.

Das separate Hermes-Plugin ``usb-smart-dashboard`` steuert ein USB-Display
(Turing Smart Screen 3.5", VID:PID ``1a86:5722``). Es kann von zwei Prozessen
gerendert werden (Gateway-Renderthread oder ``standalone.py``); beide lesen eine
gemeinsame Bild-Inbox:

    <Hermes-Root>/usb-smart-dashboard/show-image.jpg
    <Hermes-Root>/usb-smart-dashboard/show-image.json   # created, duration, source

Dieses Modul erkennt, ob das Plugin geladen ist, und veröffentlicht dort
JPEG-Bilder (z. B. Bewegungs-Snapshots). Kein Cross-Plugin-Import, keine
Serienprotokoll-Duplizierung — nur das dokumentierte Inbox-Format.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

PLUGIN_NAME = "usb-smart-dashboard"
INBOX_IMAGE = "show-image.jpg"
INBOX_META = "show-image.json"
DEFAULT_DURATION = 8.0


def _hermes_root() -> Path:
    from . import config_store

    return config_store.hermes_root()


def _candidate_homes() -> list[Path]:
    root = _hermes_root()
    homes = [root]
    profiles = root / "profiles"
    if profiles.is_dir():
        homes.extend(sorted(path for path in profiles.iterdir() if path.is_dir()))
    return homes


def _plugin_dir(home: Path) -> Path | None:
    directory = home / "plugins" / PLUGIN_NAME
    return directory if (directory / "plugin.yaml").is_file() else None


def _plugin_version(directory: Path) -> str:
    try:
        for line in (directory / "plugin.yaml").read_text(encoding="utf-8").splitlines():
            if line.startswith("version:"):
                return line.split(":", 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return ""


def _enabled(home: Path) -> bool:
    """Prüft ``plugins.enabled``/``plugins.entries.usb-smart-dashboard``."""
    config = home / "config.yaml"
    try:
        import yaml

        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        plugins = data.get("plugins") or {}
        if PLUGIN_NAME in (plugins.get("enabled") or []):
            return True
        entry = (plugins.get("entries") or {}).get(PLUGIN_NAME) or {}
        if entry.get("enabled") is False:
            return False
        return bool(entry) and entry.get("enabled", True) is not False
    except FileNotFoundError:
        return False
    except Exception:  # noqa: BLE001 - kaputte Config -> konservativ
        try:
            text = config.read_text(encoding="utf-8")
        except OSError:
            return False
        return PLUGIN_NAME in text and "enabled: false" not in text


def _service_active() -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "usb-smart-dashboard.service"],
            capture_output=True, text=True, timeout=2.0, check=False,
        )
        return result.stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        return False


def _serial_ports() -> list[str]:
    ports = []
    for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*"):
        ports.extend(str(path) for path in sorted(Path("/").glob(pattern.lstrip("/"))))
    return ports


def dashboard_status() -> dict[str, Any]:
    """Status des USB-Smart-Dashboard-Plugins und des Displays."""
    installed_at: str | None = None
    version = ""
    loaded = False
    for home in _candidate_homes():
        directory = _plugin_dir(home)
        if directory is None:
            continue
        installed_at = str(directory)
        version = _plugin_version(directory)
        if _enabled(home):
            loaded = True
    ports = _serial_ports()
    service = _service_active()
    inbox = _hermes_root() / PLUGIN_NAME
    return {
        "plugin": PLUGIN_NAME,
        "loaded": loaded,                 # installiert + in Hermes aktiviert
        "installed": bool(installed_at),
        "installed_at": installed_at,
        "version": version,
        "display_connected": bool(ports),  # USB-Seriell (Turing/UsbMonitor)
        "serial_ports": ports,
        "service_active": service,
        "ready": bool(loaded and (ports or service)),
        "inbox": str(inbox),
    }


def publish(jpeg: bytes, duration: float = DEFAULT_DURATION,
            source: str = "motion") -> Path | None:
    """JPEG in die Display-Inbox legen (atomar); ``None`` bei Fehlern."""
    if not jpeg:
        return None
    folder = _hermes_root() / PLUGIN_NAME
    try:
        folder.mkdir(parents=True, exist_ok=True)
        image_path = folder / INBOX_IMAGE
        tmp_image = folder / (INBOX_IMAGE + ".tmp")
        tmp_image.write_bytes(jpeg)
        os.replace(tmp_image, image_path)
        meta = {
            "created": time.time(),
            "duration": max(1.0, float(duration or DEFAULT_DURATION)),
            "source": str(source or "motion"),
        }
        tmp_meta = folder / (INBOX_META + ".tmp")
        tmp_meta.write_text(json.dumps(meta), encoding="utf-8")
        os.replace(tmp_meta, folder / INBOX_META)
        return image_path
    except OSError:
        return None


def active_image() -> dict[str, Any] | None:
    """Aktuell angezeigtes Bild (für Status/Diagnose)."""
    folder = _hermes_root() / PLUGIN_NAME
    try:
        meta = json.loads((folder / INBOX_META).read_text(encoding="utf-8"))
        created = float(meta.get("created") or 0)
        duration = max(1.0, float(meta.get("duration") or DEFAULT_DURATION))
        if time.time() >= created + duration:
            return None
        return {"created": created, "duration": duration,
                "remaining": round(created + duration - time.time(), 1),
                "source": meta.get("source") or ""}
    except (OSError, ValueError, TypeError):
        return None
