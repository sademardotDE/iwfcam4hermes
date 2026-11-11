"""Hermes-Tools und CLI-Anbindung für das iwfcam4hermes-Plugin.

Der Hermes-Plugin-Loader importiert dieses Paket und ruft ``register(ctx)`` auf
(siehe :mod:`iwfcam4hermes`). Hier liegen die Tool-Schemas, die Handler und die
optionale ``hermes cameras``-CLI. Alle teuren Importe (Netzwerk, OpenCV) passieren
erst im Handler, damit ``register()`` schnell und ohne Hardware funktioniert.
"""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Any, Callable

_PLUGIN_ROOT = Path(__file__).resolve().parent

TOOLSET = "cameras"

_VALID_TYPES = ("iwfcam", "ziota", "pppp")

_DEFAULTS: dict[str, Any] = {
    "config": "",
    "snapshot_dir": "",
    "signaling_host": "sig.gps555.net",
    "signaling_port": 8882,
    "public_ip": "",
    "media_port": 10000,
    "stun_port": 13478,
}

# Laufender selbstgehosteter Empfänger (Prozess-global, wie der Port selbst).
_receiver: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #


def _json(payload: Any) -> str:
    """Tool-Ergebnisse müssen JSON-Strings sein."""
    return json.dumps(payload, ensure_ascii=False, default=str)


def _error(message: str, **extra: Any) -> str:
    return _json({"ok": False, "error": str(message), **extra})


def settings(ctx: Any) -> dict[str, Any]:
    """Plugin-Einstellungen lesen (Defaults, wenn Hermes nichts liefert)."""
    resolved: dict[str, Any] = {}
    for key, default in _DEFAULTS.items():
        getter = getattr(ctx, "get_config", None)
        value = default
        if callable(getter):
            try:
                value = getter(key, default)
            except Exception:
                value = default
        resolved[key] = default if value is None else value
    return resolved


def _resolve_config(settings_: dict[str, Any], override: str | None = None) -> Path:
    """Pfad zur Kamera-JSON (Argument > Einstellung > gemeinsamer Hermes-Speicherort)."""
    from . import config_store

    return config_store.resolve_config_path(override or settings_.get("config") or None)


def _resolve_snapshot_dir(settings_: dict[str, Any]) -> Path | None:
    """Erstes beschreibbares Snapshot-Verzeichnis (Einstellung > Hermes-Home > Plugin-Dir)."""
    raw = str(settings_.get("snapshot_dir") or "").strip()
    from . import config_store

    candidates = ([Path(raw).expanduser()] if raw else
                  [config_store.hermes_root() / "iwfcam4hermes" / "snapshots",
                   _PLUGIN_ROOT / "snapshots"])
    for directory in candidates:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            return directory
        except OSError:
            continue
    return None


def _manager(settings_: dict[str, Any], override: str | None = None):
    from .manager import CameraManager

    return CameraManager(_resolve_config(settings_, override))


def _camera_dict(cam: Any) -> dict[str, Any]:
    return {
        "id": cam.id,
        "name": cam.name,
        "type": cam.type.value,
        "uid": cam.uid,
        "host": cam.host,
        "port": cam.port,
        "channel": cam.channel,
        "relay_mode": cam.relay_mode,
        "mock": cam.mock,
        "stream_url": cam.stream_url(),
        "snapshot_url": cam.snapshot_url(),
        "notes": cam.notes,
    }


# --------------------------------------------------------------------------- #
# Kamera-Handler
# --------------------------------------------------------------------------- #


def _h_list(ctx: Any, args: dict, **_: Any) -> str:
    try:
        cfg = settings(ctx)
        manager = _manager(cfg, args.get("config"))
        return _json({
            "ok": True,
            "config": str(manager.config_path),
            "count": len(manager.devices),
            "devices": manager.list_devices(),
        })
    except Exception as exc:  # noqa: BLE001 - Tool-Vertrag: Fehler als JSON
        return _error(exc, tool="camera_list")


def _h_get(ctx: Any, args: dict, **_: Any) -> str:
    device_id = str(args.get("device_id") or "").strip()
    try:
        manager = _manager(settings(ctx), args.get("config"))
        cam = manager.get_device(device_id)
        if cam is None:
            return _error(f"Unbekannte Kamera: {device_id!r}", tool="camera_get",
                          known=[c.id for c in manager.devices])
        return _json({"ok": True, "device": _camera_dict(cam)})
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="camera_get")


def _h_stream_url(ctx: Any, args: dict, **_: Any) -> str:
    return _device_url(ctx, args, "stream")


def _h_snapshot_url(ctx: Any, args: dict, **_: Any) -> str:
    return _device_url(ctx, args, "snapshot")


def _device_url(ctx: Any, args: dict, kind: str) -> str:
    device_id = str(args.get("device_id") or "").strip()
    try:
        manager = _manager(settings(ctx), args.get("config"))
        cam = manager.get_device(device_id)
        if cam is None:
            return _error(f"Unbekannte Kamera: {device_id!r}",
                          tool=f"camera_{kind}_url",
                          known=[c.id for c in manager.devices])
        url = cam.stream_url() if kind == "stream" else cam.snapshot_url()
        return _json({"ok": True, "device_id": cam.id, "url": url})
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool=f"camera_{kind}_url")


def _h_snapshot(ctx: Any, args: dict, **_: Any) -> str:
    device_id = str(args.get("device_id") or "").strip()
    try:
        cfg = settings(ctx)
        manager = _manager(cfg, args.get("config"))
        cam = manager.get_device(device_id)
        if cam is None:
            return _error(f"Unbekannte Kamera: {device_id!r}", tool="camera_snapshot",
                          known=[c.id for c in manager.devices])
        output = str(args.get("output") or "").strip()
        if output:
            target = Path(output).expanduser()
        else:
            snapshot_dir = _resolve_snapshot_dir(cfg)
            if snapshot_dir is None:
                return _error("Kein beschreibbares Snapshot-Verzeichnis gefunden",
                              tool="camera_snapshot")
            target = snapshot_dir / f"{cam.id}-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not manager.snapshot(device_id, target):
            return _error("Snapshot fehlgeschlagen (URL nicht erreichbar oder Kamera ohne Snapshot)",
                          tool="camera_snapshot", device_id=device_id, path=str(target))
        return _json({
            "ok": True,
            "device_id": device_id,
            "path": str(target),
            "bytes": target.stat().st_size if target.exists() else 0,
            "mock": cam.mock,
        })
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="camera_snapshot")


def _h_signaling_login(ctx: Any, args: dict, **_: Any) -> str:
    uid = str(args.get("uid") or "").strip()
    if not uid:
        return _error("uid erforderlich (z. B. ZIOTA_<id>)", tool="camera_signaling_login")
    try:
        from .ziota_adapter import ZIOTAdapter

        cfg = settings(ctx)
        host = str(args.get("host") or cfg["signaling_host"])
        port = int(args.get("port") or cfg["signaling_port"])
        adapter = ZIOTAdapter(uid=uid, firmware=str(args.get("firmware") or "TXW817_A_V1.0.11.84"))
        reply = adapter.signaling_login(host=host, port=port,
                                        timeout=float(args.get("timeout") or 10))
        if not reply:
            return _error("Signalisierungs-Login fehlgeschlagen (Host/Port/Netz prüfen)",
                          tool="camera_signaling_login", uid=uid, host=host, port=port)
        return _json({"ok": True, "uid": uid, "host": host, "port": port, "reply": reply})
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="camera_signaling_login")


# --------------------------------------------------------------------------- #
# Konfiguration: Anlegen / Ändern / Löschen / Testen
# --------------------------------------------------------------------------- #


def _h_camera_add(ctx: Any, args: dict, **_: Any) -> str:
    try:
        from . import config_store

        raw = args.get("device")
        if not isinstance(raw, dict):
            return _error("'device' muss ein JSON-Objekt sein", tool="camera_add")
        device, path = config_store.add_device(raw, args.get("config"))
        return _json({"ok": True, "device": device, "config": str(path)})
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="camera_add")


def _h_camera_update(ctx: Any, args: dict, **_: Any) -> str:
    try:
        from . import config_store

        device_id = str(args.get("device_id") or "").strip()
        changes = args.get("changes")
        if not isinstance(changes, dict):
            return _error("'changes' muss ein JSON-Objekt sein", tool="camera_update")
        device, path = config_store.update_device(device_id, changes, args.get("config"))
        return _json({"ok": True, "device": device, "config": str(path)})
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="camera_update")


def _h_camera_remove(ctx: Any, args: dict, **_: Any) -> str:
    try:
        from . import config_store

        device_id = str(args.get("device_id") or "").strip()
        path = config_store.remove_device(device_id, args.get("config"))
        return _json({"ok": True, "removed": device_id, "config": str(path)})
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="camera_remove")


def test_device(device: dict[str, Any], timeout: float = 3.0) -> dict[str, Any]:
    """Erreichbarkeit eines Geräts prüfen (mock, TCP host:port, HTTP-Snapshot)."""
    import time as _time

    if device.get("mock"):
        return {"reachable": True, "detail": "Mock-Kamera (kein Netz nötig)", "elapsed_ms": 0}
    host = str(device.get("host") or "").strip()
    port = device.get("port")
    if host and port:
        started = _time.monotonic()
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                elapsed = round((_time.monotonic() - started) * 1000, 1)
                return {"reachable": True, "detail": f"TCP {host}:{port} erreichbar",
                        "elapsed_ms": elapsed}
        except OSError as exc:
            return {"reachable": False, "detail": f"TCP {host}:{port} nicht erreichbar: {exc}"}
    if host:
        return {"reachable": False, "detail": "Port fehlt (z. B. 554, 8080 oder 7070)"}
    return {"reachable": False, "detail": "host/port nicht konfiguriert"}


def _h_camera_test(ctx: Any, args: dict, **_: Any) -> str:
    try:
        from . import config_store

        device_id = str(args.get("device_id") or "").strip()
        raw = config_store.get_device(device_id, args.get("config"))
        result = test_device(raw, timeout=float(args.get("timeout") or 3))
        return _json({"ok": True, "device_id": device_id, **result})
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="camera_test")


# --------------------------------------------------------------------------- #
# Selbstgehosteter Empfänger
# --------------------------------------------------------------------------- #


def _receiver_status_payload() -> dict[str, Any]:
    if _receiver is None:
        return {"running": False}
    server = _receiver["server"]
    payload: dict[str, Any] = {
        "running": True,
        "started_at": _receiver["started_at"],
        "uptime_s": round(time.time() - _receiver["started_at"], 1),
        "public_ip": _receiver["public_ip"],
        **(_receiver.get("info") or {}),
    }
    try:
        payload["media"] = server.media.stats()
    except Exception:  # pragma: no cover - Statistik ist optional
        pass
    return payload


def _h_receiver_start(ctx: Any, args: dict, **_: Any) -> str:
    global _receiver
    if _receiver is not None:
        return _json({"ok": False, "error": "Empfänger läuft bereits",
                      "status": _receiver_status_payload()})
    try:
        from .rtp_receiver import default_dht
        from .ziot_receiver import ZiotReceiverServer

        cfg = settings(ctx)
        public_ip = str(args.get("public_ip") or cfg["public_ip"] or "127.0.0.1")
        signaling_port = int(args.get("signaling_port") or cfg["signaling_port"])
        media_port = int(args.get("media_port") or cfg["media_port"])
        stun_port = int(args.get("stun_port") or cfg["stun_port"])
        server = ZiotReceiverServer(
            host="0.0.0.0",
            public_ip=public_ip,
            signaling_port=signaling_port,
            media_port=media_port,
            stun_port=stun_port,
            dht=default_dht(),
            snapshot_dir=(lambda d: str(d) if d is not None else None)(_resolve_snapshot_dir(cfg)),
        )
        info = server.start()
        _receiver = {
            "server": server,
            "info": info,
            "public_ip": public_ip,
            "started_at": time.time(),
        }
        return _json({"ok": True, "public_ip": public_ip, **info,
                      "hint": "Kamera per BLE/App auf diese IP und signaling_port zeigen."})
    except Exception as exc:  # noqa: BLE001
        _receiver = None
        return _error(exc, tool="camera_receiver_start")


def _h_receiver_stop(ctx: Any, args: dict, **_: Any) -> str:
    global _receiver
    if _receiver is None:
        return _json({"ok": True, "status": "not_running"})
    try:
        _receiver["server"].stop()
        return _json({"ok": True, "status": "stopped"})
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="camera_receiver_stop")
    finally:
        _receiver = None


def _h_receiver_status(ctx: Any, args: dict, **_: Any) -> str:
    return _json({"ok": True, **_receiver_status_payload()})


# --------------------------------------------------------------------------- #
# Quellen / Dienste
# --------------------------------------------------------------------------- #


def _h_sources(ctx: Any, args: dict, **_: Any) -> str:
    try:
        from .camera_gui_plugin import CameraGUIPlugin

        sources = CameraGUIPlugin().list_sources()
        return _json({"ok": True, "count": len(sources), "sources": sources})
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="camera_sources")


def _h_services_status(ctx: Any, args: dict, **_: Any) -> str:
    try:
        from . import services

        return _json(services.status())
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="services_status")


def _h_services_start(ctx: Any, args: dict, **_: Any) -> str:
    try:
        from . import services

        return _json(services.start(str(args.get("service") or "all")))
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="services_start")


def _h_services_stop(ctx: Any, args: dict, **_: Any) -> str:
    try:
        from . import services

        return _json(services.stop(str(args.get("service") or "all")))
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="services_stop")


def _h_services_enable(ctx: Any, args: dict, **_: Any) -> str:
    try:
        from . import services

        return _json(services.enable(str(args.get("service") or "all")))
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="services_enable")


def _h_services_disable(ctx: Any, args: dict, **_: Any) -> str:
    try:
        from . import services

        return _json(services.disable(str(args.get("service") or "all")))
    except Exception as exc:  # noqa: BLE001
        return _error(exc, tool="services_disable")


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #

_CONFIG_PROP = {
    "type": "string",
    "description": "Optionaler Pfad zur Kamera-JSON-Konfiguration (sonst Plugin-Einstellung/Mitlieferung).",
}

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "camera_list": {
        "name": "camera_list",
        "description": "Listet alle in der Kamera-Konfiguration hinterlegten WiFi-Kameras "
                       "(iWFCam/Z-IOT) mit Typ, Host, Stream- und Snapshot-URL auf.",
        "parameters": {"type": "object", "properties": {"config": _CONFIG_PROP}},
    },
    "camera_get": {
        "name": "camera_get",
        "description": "Liefert die vollständigen Details einer Kamera aus der Konfiguration.",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "ID der Kamera, z. B. cam1."},
                "config": _CONFIG_PROP,
            },
            "required": ["device_id"],
        },
    },
    "camera_stream_url": {
        "name": "camera_stream_url",
        "description": "Gibt die Stream-URL (HTTP/RTSP/PPPP) einer konfigurierten Kamera zurück.",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "ID der Kamera, z. B. cam1."},
                "config": _CONFIG_PROP,
            },
            "required": ["device_id"],
        },
    },
    "camera_snapshot_url": {
        "name": "camera_snapshot_url",
        "description": "Gibt die Snapshot-URL einer konfigurierten Kamera zurück.",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "ID der Kamera, z. B. cam1."},
                "config": _CONFIG_PROP,
            },
            "required": ["device_id"],
        },
    },
    "camera_snapshot": {
        "name": "camera_snapshot",
        "description": "Holt einen Snapshot der Kamera und speichert ihn als JPEG. Ohne 'output' "
                       "landet die Datei im Snapshot-Verzeichnis der Plugin-Einstellungen.",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "ID der Kamera, z. B. cam1."},
                "output": {"type": "string", "description": "Zielpfad für das JPEG (optional)."},
                "config": _CONFIG_PROP,
            },
            "required": ["device_id"],
        },
    },
    "camera_signaling_login": {
        "name": "camera_signaling_login",
        "description": "Führt den verifizierten Z-IOT-Signalisierungs-Login (binäres 86-86-Framing, "
                       "TCP 8882) aus und liefert Relay-IP/-Port, Media-Port sowie STUN- und "
                       "Cloud-Endpunkte der Kamera.",
        "parameters": {
            "type": "object",
            "properties": {
                "uid": {"type": "string", "description": "Kamera-UID, z. B. ZIOTA_ABCDEFGHIJ."},
                "host": {"type": "string", "description": "Signalisierungs-Host (Default aus Einstellungen)."},
                "port": {"type": "integer", "description": "Signalisierungs-Port (Default 8882)."},
                "firmware": {"type": "string", "description": "Firmware-String für das Login-Frame."},
                "timeout": {"type": "number", "description": "TCP-Timeout in Sekunden (Default 10)."},
            },
            "required": ["uid"],
        },
    },
    "camera_receiver_start": {
        "name": "camera_receiver_start",
        "description": "Startet den selbstgehosteten Empfänger (Signalisierung + STUN-Responder + "
                       "RTP/JPEG-Media) im Hintergrund, damit eine provisonierte Kamera zu diesem "
                       "Host streamt. Liefert die belegten Ports.",
        "parameters": {
            "type": "object",
            "properties": {
                "public_ip": {"type": "string", "description": "IP, unter der die Kamera diesen Host erreicht."},
                "signaling_port": {"type": "integer", "description": "TCP-Port (Default 8882)."},
                "media_port": {"type": "integer", "description": "UDP-RTP-Port (Default 10000)."},
                "stun_port": {"type": "integer", "description": "UDP-STUN-Port (Default 13478)."},
            },
        },
    },
    "camera_receiver_stop": {
        "name": "camera_receiver_stop",
        "description": "Stoppt den laufenden selbstgehosteten Empfänger.",
        "parameters": {"type": "object", "properties": {}},
    },
    "camera_receiver_status": {
        "name": "camera_receiver_status",
        "description": "Status des selbstgehosteten Empfängers inkl. Ports, Frame-/Audio-Zähler "
                       "und Bildmaßen.",
        "parameters": {"type": "object", "properties": {}},
    },
    "camera_sources": {
        "name": "camera_sources",
        "description": "Listet lokale Videoquellen (V4L2-Geräte, OpenCV-Webcam-Indizes, "
                       "GStreamer-Pipelines) für die Kamera-GUI auf.",
        "parameters": {"type": "object", "properties": {}},
    },
    "services_status": {
        "name": "services_status",
        "description": "Status der Samba- (smb/nmb) und MiniDLNA-Dienste.",
        "parameters": {"type": "object", "properties": {}},
    },
    "services_start": {
        "name": "services_start",
        "description": "Startet Samba (smb, nmb), MiniDLNA oder beide Dienste (sudo).",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "enum": ["smb", "dlna", "all"],
                            "description": "Welcher Dienst gestartet wird (Default all)."},
            },
        },
    },
    "services_stop": {
        "name": "services_stop",
        "description": "Stoppt Samba (smb, nmb), MiniDLNA oder beide Dienste (sudo).",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "enum": ["smb", "dlna", "all"],
                            "description": "Welcher Dienst gestoppt wird (Default all)."},
            },
        },
    },
    "services_enable": {
        "name": "services_enable",
        "description": "Aktiviert den Autostart (systemctl enable) für Samba (smb/nmb), "
                       "MiniDLNA oder beide Dienste.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "enum": ["smb", "dlna", "all"],
                            "description": "Welcher Dienst beim Booten starten soll (Default all)."},
            },
        },
    },
    "services_disable": {
        "name": "services_disable",
        "description": "Deaktiviert den Autostart (systemctl disable) für Samba (smb/nmb), "
                       "MiniDLNA oder beide Dienste.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "enum": ["smb", "dlna", "all"],
                            "description": "Welcher Dienst nicht mehr automatisch starten soll (Default all)."},
            },
        },
    },
    "camera_add": {
        "name": "camera_add",
        "description": "Legt eine neue Kamera in der Konfiguration an (schreibt die JSON-Datei). "
                       "Pflichtfelder: id und name; type ist iwfcam, ziota oder pppp; "
                       "host/port/uid/… optional. Gibt die gespeicherte Kamera und den Dateipfad zurück.",
        "parameters": {
            "type": "object",
            "properties": {
                "device": {
                    "type": "object",
                    "description": "Kamera-Objekt, z. B. {\"id\":\"cam1\",\"name\":\"Wohnzimmer\","
                                   "\"type\":\"iwfcam\",\"host\":\"192.168.0.50\",\"port\":554}.",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "type": {"type": "string", "enum": list(_VALID_TYPES)},
                        "uid": {"type": "string"},
                        "host": {"type": "string"},
                        "port": {"type": "integer"},
                        "username": {"type": "string"},
                        "password": {"type": "string"},
                        "channel": {"type": "integer"},
                        "stream_path": {"type": "string"},
                        "snapshot_path": {"type": "string"},
                        "relay_mode": {"type": "boolean"},
                        "mock": {"type": "boolean"},
                        "notes": {"type": "string"},
                    },
                    "required": ["id", "name"],
                },
                "config": _CONFIG_PROP,
            },
            "required": ["device"],
        },
    },
    "camera_update": {
        "name": "camera_update",
        "description": "Ändert Felder einer bestehenden Kamera (z. B. host, port, name, mock). "
                       "Die id bleibt unverändert.",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "ID der zu ändernden Kamera."},
                "changes": {
                    "type": "object",
                    "description": "Zu ändernde Felder, z. B. {\"host\":\"192.168.0.60\","
                                   "\"port\":8080,\"mock\":false}.",
                },
                "config": _CONFIG_PROP,
            },
            "required": ["device_id", "changes"],
        },
    },
    "camera_remove": {
        "name": "camera_remove",
        "description": "Entfernt eine Kamera aus der Konfiguration.",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "ID der zu löschenden Kamera."},
                "config": _CONFIG_PROP,
            },
            "required": ["device_id"],
        },
    },
    "camera_test": {
        "name": "camera_test",
        "description": "Prüft die Erreichbarkeit einer konfigurierten Kamera (TCP host:port; "
                       "Mock-Kameras gelten als erreichbar).",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "ID der Kamera."},
                "timeout": {"type": "number", "description": "Timeout in Sekunden (Default 3)."},
                "config": _CONFIG_PROP,
            },
            "required": ["device_id"],
        },
    },
}

_HANDLERS: dict[str, Callable[..., str]] = {
    "camera_list": _h_list,
    "camera_get": _h_get,
    "camera_stream_url": _h_stream_url,
    "camera_snapshot_url": _h_snapshot_url,
    "camera_snapshot": _h_snapshot,
    "camera_signaling_login": _h_signaling_login,
    "camera_add": _h_camera_add,
    "camera_update": _h_camera_update,
    "camera_remove": _h_camera_remove,
    "camera_test": _h_camera_test,
    "camera_receiver_start": _h_receiver_start,
    "camera_receiver_stop": _h_receiver_stop,
    "camera_receiver_status": _h_receiver_status,
    "camera_sources": _h_sources,
    "services_status": _h_services_status,
    "services_start": _h_services_start,
    "services_stop": _h_services_stop,
    "services_enable": _h_services_enable,
    "services_disable": _h_services_disable,
}


def make_handlers(ctx: Any) -> dict[str, Callable[..., str]]:
    """Erzeuge die Handler für ``register()`` (jeder bekommt ``args`` plus kwargs)."""
    handlers: dict[str, Callable[..., str]] = {}
    for name, handler in _HANDLERS.items():
        def bound(args: dict | None = None, _handler=handler, **kwargs: Any) -> str:
            return _handler(ctx, dict(args or {}), **kwargs)

        handlers[name] = bound
    return handlers


# --------------------------------------------------------------------------- #
# ``hermes cameras``-CLI
# --------------------------------------------------------------------------- #


def _cli_handler(ctx: Any) -> Callable[[Any], int]:
    def handle(args: Any) -> int:
        command = getattr(args, "cameras_command", "")
        payload = dict(vars(args))
        payload.pop("cameras_command", None)
        payload.pop("func", None)
        config = payload.pop("config", "") or ""
        if command in ("list", "show", "stream-url", "snapshot-url", "snapshot"):
            tool = {
                "list": "camera_list",
                "show": "camera_get",
                "stream-url": "camera_stream_url",
                "snapshot-url": "camera_snapshot_url",
                "snapshot": "camera_snapshot",
            }[command]
            tool_args: dict[str, Any] = {"config": config}
            if command != "list":
                tool_args["device_id"] = payload.get("device", "")
            if command == "snapshot" and payload.get("output"):
                tool_args["output"] = payload["output"]
            result = _HANDLERS[tool](ctx, tool_args)
            print(result)
            try:
                return 0 if json.loads(result).get("ok") else 1
            except (ValueError, AttributeError):
                return 1
        if command in ("add", "update"):
            raw_json = str(payload.get("json") or "").strip()
            if not raw_json:
                print(_error("--json mit dem Gerät/den Änderungen angeben"))
                return 2
            try:
                parsed = json.loads(raw_json)
            except ValueError as exc:
                print(_error(f"--json ist kein gültiges JSON: {exc}"))
                return 2
            if command == "add":
                tool_args = {"device": parsed, "config": config}
                tool = "camera_add"
            else:
                tool_args = {"device_id": payload.get("device", ""), "changes": parsed,
                             "config": config}
                tool = "camera_update"
            result = _HANDLERS[tool](ctx, tool_args)
            print(result)
            try:
                return 0 if json.loads(result).get("ok") else 1
            except (ValueError, AttributeError):
                return 1

        tool_map = {
            "signaling-login": ("camera_signaling_login", ["uid", "host", "port", "firmware", "timeout"]),
            "remove": ("camera_remove", ["device"]),
            "test": ("camera_test", ["device", "timeout"]),
            "receiver-start": ("camera_receiver_start", ["public_ip", "signaling_port", "media_port", "stun_port"]),
            "receiver-stop": ("camera_receiver_stop", []),
            "receiver-status": ("camera_receiver_status", []),
            "sources": ("camera_sources", []),
            "services-status": ("services_status", []),
            "services-start": ("services_start", ["service"]),
            "services-stop": ("services_stop", ["service"]),
            "services-enable": ("services_enable", ["service"]),
            "services-disable": ("services_disable", ["service"]),
        }
        if command in tool_map:
            tool, keys = tool_map[command]
            tool_args = {key: payload[key] for key in keys if payload.get(key) is not None}
            if "device" in tool_args:
                tool_args["device_id"] = tool_args.pop("device")
            tool_args["config"] = config
            result = _HANDLERS[tool](ctx, tool_args)
            print(result)
            try:
                return 0 if json.loads(result).get("ok") else 1
            except (ValueError, AttributeError):
                return 1
        print(_error(f"Unbekannter Befehl: {command!r}"))
        return 2

    return handle


def register_cli(ctx: Any) -> None:
    """Registriert ``hermes cameras <list|show|stream-url|...>``."""
    try:
        import argparse  # noqa: F401 - nur für typing/Verfügbarkeit geprüft
    except Exception:  # pragma: no cover - argparse ist stdlib
        return

    def setup(subparser: Any) -> None:
        subs = subparser.add_subparsers(dest="cameras_command", required=True)

        p = subs.add_parser("list", help="Kameras auflisten")
        p.add_argument("--config", default="")

        p = subs.add_parser("show", help="Eine Kamera anzeigen")
        p.add_argument("device", help="Kamera-ID")
        p.add_argument("--config", default="")

        p = subs.add_parser("stream-url", help="Stream-URL ausgeben")
        p.add_argument("device", help="Kamera-ID")
        p.add_argument("--config", default="")

        p = subs.add_parser("snapshot-url", help="Snapshot-URL ausgeben")
        p.add_argument("device", help="Kamera-ID")
        p.add_argument("--config", default="")

        p = subs.add_parser("snapshot", help="Snapshot speichern")
        p.add_argument("device", help="Kamera-ID")
        p.add_argument("--output", default="")
        p.add_argument("--config", default="")

        p = subs.add_parser("add", help="Kamera anlegen (JSON)")
        p.add_argument("--json", default="", help='Gerät als JSON, z. B. {"id":"cam1","name":"Wohnzimmer"}')
        p.add_argument("--config", default="")

        p = subs.add_parser("update", help="Kamera ändern (JSON)")
        p.add_argument("device", help="Kamera-ID")
        p.add_argument("--json", default="", help='Felder als JSON, z. B. {"host":"192.168.0.60"}')
        p.add_argument("--config", default="")

        p = subs.add_parser("remove", help="Kamera löschen")
        p.add_argument("device", help="Kamera-ID")
        p.add_argument("--config", default="")

        p = subs.add_parser("test", help="Kamera-Erreichbarkeit prüfen")
        p.add_argument("device", help="Kamera-ID")
        p.add_argument("--timeout", type=float, default=3.0)
        p.add_argument("--config", default="")

        p = subs.add_parser("signaling-login", help="Z-IOT-Signalisierungs-Login (TCP 8882)")
        p.add_argument("uid", help="Kamera-UID (ZIOTA_...)")
        p.add_argument("--host", default=None)
        p.add_argument("--port", type=int, default=None)
        p.add_argument("--firmware", default="TXW817_A_V1.0.11.84")
        p.add_argument("--timeout", type=float, default=10.0)

        p = subs.add_parser("receiver-start", help="Selbstgehosteten Empfänger starten")
        p.add_argument("--public-ip", default=None)
        p.add_argument("--signaling-port", type=int, default=None)
        p.add_argument("--media-port", type=int, default=None)
        p.add_argument("--stun-port", type=int, default=None)

        subs.add_parser("receiver-stop", help="Empfänger stoppen")
        subs.add_parser("receiver-status", help="Empfänger-Status")
        subs.add_parser("sources", help="Lokale Videoquellen auflisten")
        subs.add_parser("services-status", help="Samba/MiniDLNA-Status")

        p = subs.add_parser("services-start", help="Samba/MiniDLNA starten")
        p.add_argument("service", nargs="?", default="all", choices=["smb", "dlna", "all"])

        p = subs.add_parser("services-stop", help="Samba/MiniDLNA stoppen")
        p.add_argument("service", nargs="?", default="all", choices=["smb", "dlna", "all"])

        p = subs.add_parser("services-enable", help="Autostart aktivieren")
        p.add_argument("service", nargs="?", default="all", choices=["smb", "dlna", "all"])

        p = subs.add_parser("services-disable", help="Autostart deaktivieren")
        p.add_argument("service", nargs="?", default="all", choices=["smb", "dlna", "all"])

    ctx.register_cli_command(
        name="cameras",
        help="WiFi-Kameras (iWFCam & Z-IOT) verwalten",
        setup_fn=setup,
        handler_fn=_cli_handler(ctx),
        description=("Kameras auflisten, Stream-/Snapshot-URLs ausgeben, Snapshots holen, "
                     "Z-IOT-Signalisierungs-Login ausführen, selbstgehosteten Empfänger "
                     "steuern und Samba/MiniDLNA-Dienste schalten."),
    )
