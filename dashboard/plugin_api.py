"""Dashboard backend for iwfcam4hermes, mounted at /api/plugins/iwfcam4hermes/.

Runs inside the Hermes dashboard/gateway process (behind its auth) and serves
the camera list, snapshots and stream URLs to both the dashboard tab and the
Desktop page. The plugin package is loaded under a private name, mirroring the
agent loader, so relative imports inside the package resolve cleanly.
"""

from __future__ import annotations

import base64
import importlib
import importlib.util
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException

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

router = APIRouter()


def _config_path() -> Path:
    """Prefer a user config next to the plugin, else the bundled example.

    The example ships three devices (one mock) so the tab renders out of the box.
    """
    cfg = _ROOT / "config.json"
    return cfg if cfg.exists() else (_ROOT / "config.example.json")


def _cameras():
    return manager.CameraManager(_config_path())


@router.get("/devices")
def devices():
    mgr = _cameras()
    return {"ok": True, "devices": mgr.list_devices(), "config": str(_config_path())}


@router.get("/stream-url/{device_id}")
def stream_url(device_id: str):
    mgr = _cameras()
    cam = mgr.get_device(device_id)
    if cam is None:
        raise HTTPException(404, f"unknown device {device_id}")
    return {"ok": True, "stream_url": cam.stream_url()}


@router.get("/snapshot/{device_id}")
def snapshot(device_id: str):
    mgr = _cameras()
    cam = mgr.get_device(device_id)
    if cam is None:
        raise HTTPException(404, f"unknown device {device_id}")

    # Write to a temp file (fetch_snapshot's contract), then read it back and
    # inline it as a data URL. Dashboard auth is a header an <img src> cannot
    # send, so the image travels as JSON, not as a URL.
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        ok = plugin.fetch_snapshot(cam, tmp_path)
        if not ok:
            raise HTTPException(502, "snapshot fetch failed")
        data = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)

    b64 = base64.b64encode(data).decode("ascii")
    return {"ok": True, "mime": "image/jpeg", "image": f"data:image/jpeg;base64,{b64}"}
