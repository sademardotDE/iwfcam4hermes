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


def test_relay_server_serves_status_and_snapshot():
    server = relay.RelayServer(
        "127.0.0.1", signaling_port=0, media_port=0, stun_port=0,
        http_host="127.0.0.1", http_port=0,
    )
    info = server.start()
    try:
        assert info["running"] is True
        assert info["signaling_port"] > 0 and info["media_port"] > 0
        assert info["http_port"] > 0

        stats = relay.probe_http("127.0.0.1", info["http_port"])
        assert stats is not None and stats["ok"] is True
        assert "media" in stats

        # Ohne Frame: kein Snapshot
        assert relay.snapshot_bytes("127.0.0.1", info["http_port"]) is None

        jpeg = b"\xff\xd8TESTFRAME\xff\xd9"
        server.receiver.media._latest = jpeg  # Test-Injektion statt echter RTP-Frames
        assert relay.snapshot_bytes("127.0.0.1", info["http_port"]) == jpeg

        # MJPEG-Stream liefert Multipart-Header + Frame
        url = f"http://127.0.0.1:{info['http_port']}/stream.mjpg"
        with urllib.request.urlopen(url, timeout=5) as response:
            chunk = response.read(64)
        assert b"--frame" in chunk
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
