#!/usr/bin/env python3
"""Tests für das Dashboard-Backend (dashboard/plugin_api.py).

Läuft nur, wenn FastAPI + httpx verfügbar sind (Hermes-Venv); im System-Python
werden die Tests übersprungen. Die Handler werden über die echte
FastAPI-Router-Struktur angesprochen, aber alle Kamera-/Relay-/Provisionierungs-
Funktionen sind gefälscht — es wird nie echte Hardware oder systemctl angefasst.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parent
API_PATH = PLUGIN_ROOT / "dashboard" / "plugin_api.py"


@pytest.fixture(scope="module")
def module():
    spec = importlib.util.spec_from_file_location("iwfcam_dashboard_api_test", API_PATH)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules["iwfcam_dashboard_api_test"] = loaded
    spec.loader.exec_module(loaded)
    return loaded


@pytest.fixture
def client(module):
    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app, raise_server_exceptions=False)


def _fake_config(monkeypatch, module, tmp_path):
    path = tmp_path / "config.json"
    monkeypatch.setattr(module.config_store, "resolve_config_path", lambda *a, **k: path)
    monkeypatch.setattr(module.config_store, "user_config_path", lambda: path)
    return path


def test_config_info(client, module, monkeypatch, tmp_path):
    path = _fake_config(monkeypatch, module, tmp_path)
    response = client.get("/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True and payload["config"] == str(path)


def test_devices_list(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)

    class FakeManager:
        def __init__(self, _path):
            pass

        def list_devices(self):
            return [{"id": "cam1", "name": "Wohnzimmer"}]

    monkeypatch.setattr(module.manager, "CameraManager", FakeManager)
    payload = client.get("/devices").json()
    assert payload["devices"] == [{"id": "cam1", "name": "Wohnzimmer"}]


def test_device_add_validation_error(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)

    def boom(*_a, **_k):
        raise module.config_store.ConfigError("id fehlt")

    monkeypatch.setattr(module.config_store, "add_device", boom)
    response = client.post("/devices", json={"name": "x"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "id fehlt"


def test_device_detail_404(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)

    def missing(*_a, **_k):
        raise module.config_store.ConfigError("unknown device")

    monkeypatch.setattr(module.config_store, "get_device", missing)
    assert client.get("/devices/nope").status_code == 404


def test_device_test(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)
    monkeypatch.setattr(module.config_store, "get_device", lambda *a, **k: {"id": "cam1"})
    monkeypatch.setattr(module.plugin_tools, "test_device", lambda device: {"reachable": True, "detail": "ok"})
    payload = client.post("/devices/cam1/test").json()
    assert payload["ok"] is True and payload["reachable"] is True


def test_device_reconnect_offline(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)
    monkeypatch.setattr(module.plugin_tools, "reconnect_device",
                        lambda device_id, cfg, **kwargs: {"ok": False, "error": "Kamera-AP nicht sichtbar"})
    response = client.post("/devices/cam1/reconnect", json={})
    assert response.status_code == 409
    assert "nicht sichtbar" in response.json()["detail"]["error"]


def test_device_reconnect_ok(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)
    monkeypatch.setattr(module.plugin_tools, "reconnect_device",
                        lambda device_id, cfg, **kwargs: {"ok": True, "already_online": True, "state": "streaming"})
    payload = client.post("/devices/cam1/reconnect", json={}).json()
    assert payload["ok"] is True and payload["already_online"] is True


def test_relay_status(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)
    monkeypatch.setattr(module.relay, "status", lambda settings: {
        "ok": True, "running": True,
        "cameras": [{"uid": "196758286858", "state": "streaming", "frames": 7}],
        "snapshots": {"enabled": True, "total": 3},
    })
    payload = client.get("/relay").json()
    assert payload["running"] is True
    assert payload["cameras"][0]["state"] == "streaming"
    assert payload["snapshots"]["total"] == 3


def test_relay_snapshot(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)
    monkeypatch.setattr(module.relay, "settings_from", lambda cfg: {"http_host": "127.0.0.1", "http_port": 9})
    monkeypatch.setattr(module.relay, "snapshot_bytes",
                        lambda host, port, uid=None, quality=None: b"\xff\xd8FRAME\xff\xd9")
    payload = client.get("/relay/snapshot?uid=196758286858&quality=low").json()
    assert payload["ok"] is True and payload["image"].startswith("data:image/jpeg;base64,")


def test_relay_snapshot_no_frame(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)
    monkeypatch.setattr(module.relay, "settings_from", lambda cfg: {"http_host": "127.0.0.1", "http_port": 9})
    monkeypatch.setattr(module.relay, "snapshot_bytes", lambda *a, **k: None)
    assert client.get("/relay/snapshot").status_code == 503


def test_relay_snapshots_and_save(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)
    stats = {"enabled": True, "total": 4, "cameras": {"196758286858": {"count": 4}}}
    monkeypatch.setattr(module.relay, "settings_from", lambda cfg: {"http_host": "127.0.0.1", "http_port": 9})
    monkeypatch.setattr(module.relay, "snapshots_status", lambda *a, **k: dict(stats))
    monkeypatch.setattr(module.relay, "snapshots_save",
                        lambda host, port, uid=None: {"ok": True, "saved": ["/tmp/x.jpg"], "stats": stats})
    assert client.get("/relay/snapshots").json()["snapshots"]["total"] == 4
    saved = client.post("/relay/snapshots/save", json={}).json()
    assert saved["ok"] is True and saved["saved"] == ["/tmp/x.jpg"]


def test_relay_snapshots_unreachable(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)
    monkeypatch.setattr(module.relay, "settings_from", lambda cfg: {"http_host": "127.0.0.1", "http_port": 9})
    monkeypatch.setattr(module.relay, "snapshots_status", lambda *a, **k: None)
    assert client.get("/relay/snapshots").status_code == 503


def test_relay_unknown_action(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)
    assert client.post("/relay/warp", json={}).status_code == 400


def test_wifi_and_provision(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)
    monkeypatch.setattr(module.provision, "status", lambda: {
        "ok": True, "current": {"ssid": "cccp4ever"}, "camera_aps": [], "networks": []})
    assert client.get("/wifi").json()["current"]["ssid"] == "cccp4ever"

    saved = {}
    monkeypatch.setattr(module.provision, "provision", lambda **kwargs: {
        "ok": True, "camera_uid": "ZIOTA_196758286858", "ssid": kwargs["ssid"]})
    monkeypatch.setattr(module.config_store, "save_provision",
                        lambda credentials, path=None: saved.update(credentials))
    payload = client.post("/provision", json={
        "camera_ssid": "ZIOTA_196758286858", "ssid": "cccp4ever",
        "password": "geheim", "server_ip": "192.168.0.4", "server_port": 8882}).json()
    assert payload["ok"] is True
    assert saved["ssid"] == "cccp4ever" and saved["password"] == "geheim"




def _fake_camera(relay_mode=True, uid="ZIOTA_196758286858"):
    class FakeCamera:
        id = "cam1"
        mock = False

    camera = FakeCamera()
    camera.relay_mode = relay_mode
    camera.uid = uid
    return camera


def test_device_snapshot_uses_relay_first(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)

    class FakeManager:
        def __init__(self, _path):
            pass

        def get_device(self, device_id):
            return _fake_camera(relay_mode=True)

    monkeypatch.setattr(module.manager, "CameraManager", FakeManager)
    monkeypatch.setattr(module.relay, "settings_from", lambda cfg: {"http_host": "127.0.0.1", "http_port": 9})
    monkeypatch.setattr(module.relay, "snapshot_bytes",
                        lambda host, port, uid=None, quality=None: b"\xff\xd8RELAY\xff\xd9")
    payload = client.get("/snapshot/cam1?quality=medium").json()
    assert payload["ok"] is True and payload["source"] == "relay"
    assert payload["image"].startswith("data:image/jpeg;base64,")


def test_device_snapshot_falls_back_to_direct(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)

    class FakeManager:
        def __init__(self, _path):
            pass

        def get_device(self, device_id):
            return _fake_camera(relay_mode=True)

    monkeypatch.setattr(module.manager, "CameraManager", FakeManager)
    monkeypatch.setattr(module.relay, "settings_from", lambda cfg: {"http_host": "127.0.0.1", "http_port": 9})
    monkeypatch.setattr(module.relay, "snapshot_bytes", lambda *a, **k: None)

    def fake_fetch(camera, path):
        path.write_bytes(b"\xff\xd8DIRECT\xff\xd9")
        return True

    monkeypatch.setattr(module.plugin, "fetch_snapshot", fake_fetch)
    payload = client.get("/snapshot/cam1").json()
    assert payload["ok"] is True and payload["source"] == "direct"


def test_device_snapshot_unknown_device(client, module, monkeypatch, tmp_path):
    _fake_config(monkeypatch, module, tmp_path)

    class FakeManager:
        def __init__(self, _path):
            pass

        def get_device(self, device_id):
            return None

    monkeypatch.setattr(module.manager, "CameraManager", FakeManager)
    assert client.get("/snapshot/nope").status_code == 404


def test_services_endpoints_are_gone(client, module, monkeypatch, tmp_path):
    """Samba/MiniDLNA sind ein eigenes Plugin — hier gibt es keine /services-Routen."""
    _fake_config(monkeypatch, module, tmp_path)
    assert client.get("/services").status_code == 404
    assert client.post("/services/smb/start").status_code == 404
