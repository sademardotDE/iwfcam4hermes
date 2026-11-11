"""Schreibbarer Kamera-Konfigurations-Store für iwfcam4hermes.

Zentrale Stelle für Auflösung, Validierung und Schreiben der JSON-Kamera-
Konfiguration. Genutzt von den Agent-Tools (`plugin_tools.py`) **und** vom
Dashboard-Backend (`dashboard/plugin_api.py`), damit beide dieselbe Datei
bearbeiten.

Ablage (Reihenfolge):

1. explizites Argument / ``IWFCAM_CONFIG``-Env
2. ``<Hermes-Root>/iwfcam4hermes/config.json`` (bei Profilen immer das
   gemeinsame Basis-Home, also ``~/.hermes`` statt ``profiles/<name>``)
3. ``~/.hermes/iwfcam4hermes/config.json``
4. ``config.json`` im Plugin-Verzeichnis
5. mitgeliefertes ``config.example.json`` (nur lesen; beim ersten Speichern
   wird automatisch eine beschreibbare Datei unter 2. angelegt)

Schreiben ist atomar (Temp-Datei + ``os.replace``) und legt ein ``.bak`` der
vorherigen Datei ab.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

_PLUGIN_ROOT = Path(__file__).resolve().parent
EXAMPLE_FILE = _PLUGIN_ROOT / "config.example.json"
CONFIG_FILE = "config.json"

VALID_TYPES = ("iwfcam", "ziota", "pppp")

_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

# Felder des Camera-Dataclasses (plugin.py) + Defaults für neue Geräte.
KNOWN_FIELDS = (
    "id", "name", "type", "uid", "host", "port", "username", "password",
    "channel", "stream_path", "relay_mode", "notes", "snapshot_path", "mock",
)
DEFAULTS: dict[str, Any] = {
    "type": "iwfcam",
    "uid": None,
    "host": None,
    "port": None,
    "username": None,
    "password": None,
    "channel": 0,
    "stream_path": "/live",
    "relay_mode": False,
    "notes": "",
    "snapshot_path": "/snapshot",
    "mock": False,
}
REQUIRED_FIELDS = ("id", "name")


class ConfigError(ValueError):
    """Ungültige Konfiguration / ungültiges Gerät."""


# --------------------------------------------------------------------------- #
# Pfad-Auflösung
# --------------------------------------------------------------------------- #


def hermes_root() -> Path:
    """Gemeinsames Hermes-Basis-Home (Profil-Verzeichnisse werden hochgemappt)."""
    env = os.environ.get("HERMES_HOME", "").strip()
    home = Path(env).expanduser() if env else Path.home() / ".hermes"
    if home.parent.name == "profiles":
        home = home.parent.parent
    return home


def user_config_path() -> Path:
    """Beschreibbarer Standardpfad der Kamera-Konfiguration."""
    return hermes_root() / "iwfcam4hermes" / CONFIG_FILE


def candidate_paths() -> list[Path]:
    ordered = [
        user_config_path(),
        Path.home() / ".hermes" / "iwfcam4hermes" / CONFIG_FILE,
        _PLUGIN_ROOT / CONFIG_FILE,
        EXAMPLE_FILE,
    ]
    seen: list[Path] = []
    for path in ordered:
        if path not in seen:
            seen.append(path)
    return seen


def resolve_config_path(override: str | Path | None = None) -> Path:
    """Pfad zur Kamera-Konfiguration; nicht existierende Ziele sind erlaubt (werden angelegt)."""
    env = os.environ.get("IWFCAM_CONFIG", "").strip()
    raw = str(override or env or "").strip()
    if raw:
        path = Path(raw).expanduser()
        return path / CONFIG_FILE if path.is_dir() else path
    for candidate in candidate_paths():
        if candidate.is_file():
            return candidate
    return user_config_path()


# --------------------------------------------------------------------------- #
# Laden / Speichern
# --------------------------------------------------------------------------- #


def load(path: str | Path | None = None) -> dict[str, Any]:
    """Konfiguration laden; fehlt eine Nutzerdatei, wird das Beispiel geladen."""
    resolved = resolve_config_path(path)
    source = resolved if resolved.is_file() else EXAMPLE_FILE
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Konfiguration nicht lesbar ({source}): {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Konfiguration muss ein JSON-Objekt sein ({source})")
    devices = data.get("devices")
    if devices is None:
        data["devices"] = []
    elif not isinstance(devices, list):
        raise ConfigError("Feld 'devices' muss eine Liste sein")
    return data


def save(data: Mapping[str, Any], path: str | Path | None = None) -> Path:
    """Konfiguration atomar schreiben; liefert den geschriebenen Pfad."""
    resolved = resolve_config_path(path)
    if resolved == EXAMPLE_FILE or resolved.name == "config.example.json":
        resolved = user_config_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(dict(data), indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=str(resolved.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if resolved.is_file():
            try:
                shutil.copy2(resolved, resolved.with_suffix(resolved.suffix + ".bak"))
            except OSError:
                pass
        os.replace(tmp_path, resolved)
    finally:
        tmp_path.unlink(missing_ok=True)
    return resolved


def ensure_user_config(path: str | Path | None = None) -> Path:
    """Beschreibbare Nutzerdatei sicherstellen (Beispiel kopieren, falls nötig)."""
    resolved = resolve_config_path(path)
    if resolved == EXAMPLE_FILE or resolved.name == "config.example.json" or not resolved.is_file():
        target = user_config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            try:
                data = json.loads(EXAMPLE_FILE.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {"devices": []}
            save(data, target)
        return target
    return resolved


# --------------------------------------------------------------------------- #
# Validierung
# --------------------------------------------------------------------------- #


def _as_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("1", "true", "yes", "on"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("0", "false", "no", "off", ""):
        return False
    raise ConfigError(f"Feld '{field}' muss ein Wahrheitswert sein")


def _optional_int(value: Any, field: str, minimum: int, maximum: int) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ConfigError(f"Feld '{field}' muss eine Zahl sein")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"Feld '{field}' muss eine Zahl sein")
    if not (minimum <= number <= maximum):
        raise ConfigError(f"Feld '{field}' muss zwischen {minimum} und {maximum} liegen")
    return number


def _optional_str(value: Any, field: str, maximum: int = 255) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"Feld '{field}' muss Text sein")
    text = value.strip()
    if len(text) > maximum:
        raise ConfigError(f"Feld '{field}' ist zu lang (max. {maximum})")
    return text or None


def normalize_device(raw: Mapping[str, Any], *, existing_id: str | None = None) -> dict[str, Any]:
    """Ein Gerät validieren und auf bekannte Felder normalisieren."""
    if not isinstance(raw, Mapping):
        raise ConfigError("Gerät muss ein JSON-Objekt sein")
    unknown = sorted(set(raw) - set(KNOWN_FIELDS))
    if unknown:
        raise ConfigError(f"Unbekannte Felder: {', '.join(unknown)}")

    device = dict(DEFAULTS)
    device.update({key: value for key, value in raw.items() if key in KNOWN_FIELDS})

    device_id = _optional_str(device.get("id"), "id", 64)
    if not device_id or not _ID_RE.match(device_id):
        raise ConfigError("Feld 'id' ist erforderlich (Buchstaben, Ziffern, _ . -, max. 64)")
    if existing_id is not None and device_id != existing_id:
        raise ConfigError("Feld 'id' kann nicht geändert werden")
    device["id"] = device_id

    name = _optional_str(device.get("name"), "name", 120)
    if not name:
        raise ConfigError("Feld 'name' ist erforderlich")
    device["name"] = name

    device_type = str(device.get("type") or "").strip().lower()
    if device_type not in VALID_TYPES:
        raise ConfigError(f"Feld 'type' muss einer von {', '.join(VALID_TYPES)} sein")
    device["type"] = device_type

    device["uid"] = _optional_str(device.get("uid"), "uid", 64)
    device["host"] = _optional_str(device.get("host"), "host", 255)
    device["port"] = _optional_int(device.get("port"), "port", 1, 65535)
    device["username"] = _optional_str(device.get("username"), "username", 128)
    device["password"] = _optional_str(device.get("password"), "password", 256)
    channel = _optional_int(device.get("channel"), "channel", 0, 255)
    device["channel"] = 0 if channel is None else channel
    device["stream_path"] = _optional_str(device.get("stream_path"), "stream_path", 255) or "/live"
    device["snapshot_path"] = (_optional_str(device.get("snapshot_path"), "snapshot_path", 255)
                               or "/snapshot")
    device["notes"] = _optional_str(device.get("notes"), "notes", 512) or ""
    device["relay_mode"] = _as_bool(device.get("relay_mode"), "relay_mode")
    device["mock"] = _as_bool(device.get("mock"), "mock")
    return device


def _stored_device(device: Mapping[str, Any]) -> dict[str, Any]:
    """Nur die Felder speichern, die vom Default abweichen (kompakte Datei)."""
    stored: dict[str, Any] = {}
    for field in KNOWN_FIELDS:
        value = device.get(field, DEFAULTS.get(field))
        if value != DEFAULTS.get(field) or field in REQUIRED_FIELDS:
            stored[field] = value
    for field in ("uid", "host", "username", "password"):
        if stored.get(field) is None:
            stored.pop(field, None)
    return stored


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #


def _index_by_id(devices: list[dict[str, Any]], device_id: str) -> int:
    for index, device in enumerate(devices):
        if device.get("id") == device_id:
            return index
    raise ConfigError(f"Unbekannte Kamera: {device_id!r}")


def add_device(raw: Mapping[str, Any], path: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    device = normalize_device(raw)
    data = load(path)
    devices = list(data.get("devices") or [])
    if any(entry.get("id") == device["id"] for entry in devices):
        raise ConfigError(f"Kamera {device['id']!r} existiert bereits")
    devices.append(_stored_device(device))
    data["devices"] = devices
    written = save(data, path)
    return device, written


def update_device(device_id: str, changes: Mapping[str, Any],
                  path: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    data = load(path)
    devices = [dict(entry) for entry in (data.get("devices") or [])]
    index = _index_by_id(devices, device_id)
    merged = dict(devices[index])
    merged.update({key: value for key, value in changes.items() if key in KNOWN_FIELDS})
    device = normalize_device(merged, existing_id=device_id)
    devices[index] = _stored_device(device)
    data["devices"] = devices
    written = save(data, path)
    return device, written


def remove_device(device_id: str, path: str | Path | None = None) -> Path:
    data = load(path)
    devices = [dict(entry) for entry in (data.get("devices") or [])]
    index = _index_by_id(devices, device_id)
    devices.pop(index)
    data["devices"] = devices
    return save(data, path)


def get_device(device_id: str, path: str | Path | None = None) -> dict[str, Any]:
    for entry in load(path).get("devices") or []:
        if entry.get("id") == device_id:
            return dict(entry)
    raise ConfigError(f"Unbekannte Kamera: {device_id!r}")


def list_devices(path: str | Path | None = None) -> list[dict[str, Any]]:
    return [dict(entry) for entry in (load(path).get("devices") or []) if isinstance(entry, dict)]
