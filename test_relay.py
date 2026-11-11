#!/usr/bin/env python3
"""Tests für den lokalen Relay-Server (relay.py) — ohne Kamera-Hardware."""

import json
import urllib.request
from pathlib import Path

import pytest

from iwfcam4hermes import relay


def test_render_unit_contains_expected_args(tmp_path):
    unit = relay.render_unit(
        python="/usr/bin/python3", plugin_root=tmp_path, public_ip="192.168.0.4",
        signaling_port=18882, media_port=11000, stun_port=14478, http_port=18099,
    )
    assert "ExecStart=" in unit
    assert "192.168.0.4" in unit
    assert "18882" in unit and "11000" in unit and "14478" in unit and "18099" in unit
    assert str(tmp_path / "relay.py") in unit
    assert "WantedBy=default.target" in unit
    assert "Restart=on-failure" in unit


def _test_jpeg(size=(320, 240)):
    try:
        from io import BytesIO
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None
    buffer = BytesIO()
    Image.new("RGB", size, (120, 80, 60)).save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def test_relay_server_serves_status_and_snapshot():
    from iwfcam4hermes import preview

    server = relay.RelayServer(
        "127.0.0.1", signaling_port=0, media_port=0, stun_port=0,
        http_host="127.0.0.1", http_port=0, default_quality="medium", default_fps=5,
    )
    info = server.start()
    try:
        assert info["running"] is True
        assert info["signaling_port"] > 0 and info["http_port"] > 0
        assert info["quality"] == "medium" and info["fps"] == 5

        stats = relay.probe_http("127.0.0.1", info["http_port"])
        assert stats is not None and stats["ok"] is True
        assert stats["cameras"] == []
        assert stats["totals"]["cameras"] == 0

        # Ohne Kamera: kein Snapshot
        assert relay.snapshot_bytes("127.0.0.1", info["http_port"]) is None

        jpeg = _test_jpeg() or b"\xff\xd8TESTFRAME\xff\xd9"
        media = server.receiver.media_hub.acquire("196758286858")
        media._latest = jpeg

        cameras = relay.probe_http("127.0.0.1", info["http_port"])["cameras"]
        assert [camera["uid"] for camera in cameras] == ["196758286858"]

        # Original bleibt unverändert; medium/los skalieren (nur mit Pillow)
        original = relay.snapshot_bytes("127.0.0.1", info["http_port"], quality="original")
        assert original == jpeg
        if preview.pil_available() and _test_jpeg() is not None:
            medium = relay.snapshot_bytes("127.0.0.1", info["http_port"], quality="medium")
            low = relay.snapshot_bytes("127.0.0.1", info["http_port"], quality="low")
            assert medium and low and len(low) < len(medium) < len(jpeg)

        # MJPEG-Stream liefert Multipart-Header + Frame
        url = f"http://127.0.0.1:{info['http_port']}/stream.mjpg?quality=original&fps=10"
        with urllib.request.urlopen(url, timeout=5) as response:
            chunk = response.read(64)
        assert b"--frame" in chunk
    finally:
        server.stop()


def test_two_cameras_are_listed_separately():
    server = relay.RelayServer(
        "127.0.0.1", signaling_port=0, media_port=0, stun_port=0,
        http_host="127.0.0.1", http_port=0,
    )
    info = server.start()
    try:
        jpeg = _test_jpeg() or b"\xff\xd8A\xff\xd9"
        media_a = server.receiver.media_hub.acquire("111111111111")
        media_b = server.receiver.media_hub.acquire("222222222222")
        media_a._latest = jpeg
        media_b._latest = jpeg
        cameras = relay.probe_http("127.0.0.1", info["http_port"])["cameras"]
        assert sorted(c["uid"] for c in cameras) == ["111111111111", "222222222222"]
        assert cameras[0]["port"] != cameras[1]["port"]
        # per-uid Snapshot (original = unverändert)
        one = relay.snapshot_bytes("127.0.0.1", info["http_port"],
                                   uid="111111111111", quality="original")
        assert one == jpeg
    finally:
        server.stop()




def test_snapshot_store_ring_buffer(tmp_path):
    import time

    jpeg = _test_jpeg() or b"\xff\xd8SNAP\xff\xd9"
    server = relay.RelayServer(
        "127.0.0.1", signaling_port=0, media_port=0, stun_port=0,
        http_host="127.0.0.1", http_port=0,
        snapshot_dir=str(tmp_path), snapshot_interval=3600, snapshot_retain=2,
    )
    info = server.start()
    try:
        media = server.receiver.media_hub.acquire("196758286858")
        media._latest = jpeg
        saved = server.snapshot_store.save_now()
        assert len(saved) == 1 and Path(saved[0]).is_file()
        assert Path(saved[0]).read_bytes() == jpeg

        time.sleep(0.01)
        server.snapshot_store.save_now()
        stats = server.snapshot_store.stats()
        assert stats["total"] == 2 and stats["dir"] == str(tmp_path)

        # Retention: künstlich 3 alte Dateien dazu -> prune behält 2 (die neuesten)
        folder = Path(stats["dir"]) / "196758286858"
        for index in range(3):
            (folder / f"20200101-00000{index}.jpg").write_bytes(jpeg)
        server.snapshot_store._prune(folder)
        assert len(list(folder.glob("*.jpg"))) == 2

        # HTTP: /snapshots + POST /snapshots/save
        with urllib.request.urlopen(f"http://127.0.0.1:{info['http_port']}/snapshots", timeout=5) as response:
            payload = json.loads(response.read())
        assert payload["ok"] is True and payload["total"] == 2
        request = urllib.request.Request(
            f"http://127.0.0.1:{info['http_port']}/snapshots/save?uid=196758286858",
            data=b"", method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            saved_payload = json.loads(response.read())
        assert saved_payload["ok"] is True and saved_payload["saved"]
    finally:
        server.stop()


def test_snapshot_store_disabled_without_dir():
    server = relay.RelayServer(
        "127.0.0.1", signaling_port=0, media_port=0, stun_port=0,
        http_host="127.0.0.1", http_port=0,
    )
    info = server.start()
    try:
        assert server.snapshot_store is None
        with urllib.request.urlopen(f"http://127.0.0.1:{info['http_port']}/snapshots", timeout=5) as response:
            payload = json.loads(response.read())
        assert payload["ok"] is True and payload.get("enabled") is False
    finally:
        server.stop()


def test_service_status_shape():
    status = relay.service_status()
    assert status["unit"] == relay.UNIT_NAME
    assert isinstance(status["installed"], bool)
    assert "unit_path" in status


def test_install_and_uninstall_unit_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    result = relay.install(public_ip="192.168.0.4", run=False)
    assert result["ok"] is True
    unit_path = Path(result["unit_path"])
    assert unit_path.is_file()
    assert "192.168.0.4" in unit_path.read_text(encoding="utf-8")

    # Erneutes Installieren legt ein Backup an und ersetzt die IP
    relay.install(public_ip="192.168.0.5", run=False)
    assert Path(str(unit_path) + ".bak").is_file()
    assert "192.168.0.5" in unit_path.read_text(encoding="utf-8")

    removed = relay.uninstall(run=False)
    assert removed["ok"] is True and removed["removed"] is True
    assert not unit_path.exists()


def test_install_requires_public_ip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    result = relay.install({}, public_ip=None, run=False)
    assert result["ok"] is False
    assert "public_ip" in result["error"]


def test_settings_from_defaults_and_overrides():
    cfg = relay.settings_from({"relay_http_port": "9099", "public_ip": "10.0.0.5"})
    assert cfg["http_port"] == 9099
    assert cfg["public_ip"] == "10.0.0.5"
    assert cfg["signaling_port"] == relay.DEFAULT_SIGNALING_PORT
    assert cfg["http_host"] == relay.DEFAULT_HTTP_HOST
    assert cfg["quality"] == relay.DEFAULT_QUALITY
    assert cfg["fps"] == relay.DEFAULT_FPS
    assert cfg["max_cameras"] >= 1
