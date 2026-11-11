"""Dashboard-Backend für iwfcam4hermes, gemountet unter /api/plugins/iwfcam4hermes/.

Läuft im Hermes-Dashboard/Gateway-Prozess (hinter dessen Auth) und bedient den
Dashboard-Tab: Kameras anlegen/ändern/löschen/testen, Snapshots/Stream-URLs,
sowie Samba-/MiniDLNA-Dienste starten/stoppen und den Autostart schalten.

Das Plugin-Paket wird unter einem privaten Namen geladen (wie im Agent-Loader),
damit relative Importe im Paket sauber auflösen.
"""

from __future__ import annotations

import base64
import importlib
import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException

_ROOT = Path(__file__).resolve().parents[1]
_NAME = "_iwfcam4hermes_dashboard"

if _NAME not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _NAME, _ROOT / "__init__.py", submodule_search_locations=[str(_ROOT)]
    )
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_NAME] = _mod
    _spec.loader.exec_module(_mod)

manager = importlib.import_module(_NAME + ".manager")
plugin = importlib.import_module(_NAME + ".plugin")
config_store = importlib.import_module(_NAME + ".config_store")
plugin_tools = importlib.import_module(_NAME + ".plugin_tools")
services = importlib.import_module(_NAME + ".services")

router = APIRouter()


def _config_path() -> Path:
    return config_store.resolve_config_path()


def _cameras():
    return manager.CameraManager(_config_path())


def _error(status: int, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"ok": False, "error": message, **extra})


# --------------------------------------------------------------------------- #
# Konfiguration / Kameras
# --------------------------------------------------------------------------- #


@router.get("/config")
def config_info():
    path = _config_path()
    is_example = path.name == "config.example.json"
    target = config_store.user_config_path() if is_example else path
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        writable = True
    except OSError:
        writable = False
    return {
        "ok": True,
        "config": str(path),
        "target": str(target),
        "writable": writable,
        "is_example": is_example,
        "user_config": str(config_store.user_config_path()),
    }


@router.get("/devices")
def devices():
    mgr = _cameras()
    return {"ok": True, "devices": mgr.list_devices(), "config": str(_config_path())}


@router.get("/devices/{device_id}")
def device_detail(device_id: str):
    try:
        return {"ok": True, "device": config_store.get_device(device_id, _config_path())}
    except config_store.ConfigError as exc:
        raise _error(404, str(exc))


@router.post("/devices")
def device_add(payload: dict = Body(...)):
    try:
        device, path = config_store.add_device(payload, _config_path())
        return {"ok": True, "device": device, "config": str(path)}
    except config_store.ConfigError as exc:
        raise _error(400, str(exc))
    except OSError as exc:
        raise _error(500, f"Konfiguration nicht schreibbar: {exc}")


@router.put("/devices/{device_id}")
def device_update(device_id: str, payload: dict = Body(...)):
    try:
        device, path = config_store.update_device(device_id, payload, _config_path())
        return {"ok": True, "device": device, "config": str(path)}
    except config_store.ConfigError as exc:
        raise _error(400, str(exc))
    except OSError as exc:
        raise _error(500, f"Konfiguration nicht schreibbar: {exc}")


@router.delete("/devices/{device_id}")
def device_remove(device_id: str):
    try:
        path = config_store.remove_device(device_id, _config_path())
        return {"ok": True, "removed": device_id, "config": str(path)}
    except config_store.ConfigError as exc:
        raise _error(404, str(exc))
    except OSError as exc:
        raise _error(500, f"Konfiguration nicht schreibbar: {exc}")


@router.post("/devices/{device_id}/test")
def device_test(device_id: str):
    try:
        device = config_store.get_device(device_id, _config_path())
    except config_store.ConfigError as exc:
        raise _error(404, str(exc))
    try:
        result = plugin_tools.test_device(device)
    except Exception as exc:  # noqa: BLE001 - Test darf nie 500 werfen
        raise _error(500, f"Test fehlgeschlagen: {exc}")
    return {"ok": True, "device_id": device_id, **result}


@router.get("/stream-url/{device_id}")
def stream_url(device_id: str):
    mgr = _cameras()
    cam = mgr.get_device(device_id)
    if cam is None:
        raise _error(404, f"unknown device {device_id}")
    return {"ok": True, "stream_url": cam.stream_url()}


@router.get("/snapshot/{device_id}")
def snapshot(device_id: str):
    mgr = _cameras()
    cam = mgr.get_device(device_id)
    if cam is None:
        raise _error(404, f"unknown device {device_id}")

    # In eine Temp-Datei schreiben (fetch_snapshot-Vertrag), dann als Data-URL
    # zurückgeben: Dashboard-Auth ist ein Header, den ein <img src> nicht senden kann.
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        ok = plugin.fetch_snapshot(cam, tmp_path)
        if not ok:
            raise _error(502, "snapshot fetch failed")
        data = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)

    b64 = base64.b64encode(data).decode("ascii")
    return {"ok": True, "mime": "image/jpeg", "image": f"data:image/jpeg;base64,{b64}"}


# --------------------------------------------------------------------------- #
# Dienste (Samba / MiniDLNA)
# --------------------------------------------------------------------------- #


@router.get("/services")
def services_status():
    return services.status()


def _service_action(action: str, service: str) -> dict[str, Any]:
    allowed = {"start", "stop", "enable", "disable"}
    if action not in allowed:
        raise _error(400, f"Unbekannte Aktion: {action!r}")
    handler = {
        "start": services.start,
        "stop": services.stop,
        "enable": services.enable,
        "disable": services.disable,
    }[action]
    try:
        return handler(service)
    except ValueError as exc:
        raise _error(400, str(exc))


@router.post("/services/{service}/{action}")
def service_action(service: str, action: str):
    return _service_action(action, service)
