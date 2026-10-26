#!/usr/bin/env python3
"""Unit tests for iwfcam4hermes plugin."""

import json
import tempfile
from pathlib import Path

import pytest

from iwfcam4hermes.plugin import Camera, CameraType, load_config, fetch_snapshot
from iwfcam4hermes.manager import CameraManager
from iwfcam4hermes.hermes_plugin import create_plugin
from iwfcam4hermes.ziota_adapter import ZIOTAdapter
from iwfcam4hermes.iwfcam_adapter import IWFCamAdapter
from iwfcam4hermes.stun_client import stun_binding
from iwfcam4hermes.stream_proxy import StreamProxy


@pytest.fixture
def config_file(tmp_path):
    cfg = {
        "devices": [
            {
                "id": "cam1",
                "name": "Test Cam",
                "type": "iwfcam",
                "host": "127.0.0.1",
                "port": 8080,
                "mock": True,
            }
        ]
    }
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg))
    return p


def test_load_config(config_file):
    cfg = load_config(config_file)
    assert len(cfg["devices"]) == 1
    cam = cfg["devices"][0]
    assert cam.id == "cam1"
    assert cam.type == CameraType.IWFCAM
    assert cam.mock is True


def test_stream_url(config_file):
    cfg = load_config(config_file)
    cam = cfg["devices"][0]
    assert cam.stream_url() == "http://127.0.0.1:8080/live?channel=0"


def test_snapshot_url(config_file):
    cfg = load_config(config_file)
    cam = cfg["devices"][0]
    assert cam.snapshot_url() == "http://127.0.0.1:8080/snapshot?channel=0"


def test_fetch_snapshot_mock(config_file, tmp_path):
    cfg = load_config(config_file)
    cam = cfg["devices"][0]
    out = tmp_path / "snap.jpg"
    assert fetch_snapshot(cam, out) is True
    assert out.exists()
    assert out.stat().st_size > 0


def test_camera_manager(config_file):
    mgr = CameraManager(config_file)
    devices = mgr.list_devices()
    assert len(devices) == 1
    assert devices[0]["id"] == "cam1"
    assert mgr.stream_url("cam1") == "http://127.0.0.1:8080/live?channel=0"


def test_hermes_plugin(config_file):
    plugin = create_plugin(config_file)
    status = plugin.status()
    assert status["devices"] == 1
    assert plugin.get_device("cam1") is not None
    assert plugin.get_device("unknown") is None


def test_ziota_adapter():
    adapter = ZIOTAdapter(uid="TEST")
    assert adapter.uid == "TEST"
    assert adapter.ws_url == "ws://ws.gps555.net:7080/ws"


def test_iwfcam_adapter():
    adapter = IWFCamAdapter()
    adapter.load()
    funcs = adapter.list_functions("P2P")
    assert len(funcs) > 0


def test_stun_binding():
    # Just check it doesn't crash; may fail without network
    result, err = stun_binding()
    # Either succeeds or fails gracefully
    assert result is None or isinstance(result, tuple)


def test_stream_proxy():
    from iwfcam4hermes.plugin import Camera

    cam = Camera(id="test", name="Test", host="127.0.0.1", port=8080)
    proxy = StreamProxy(cam, local_port=9999)
    assert proxy.local_url == "http://127.0.0.1:9999/"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
