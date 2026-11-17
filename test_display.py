#!/usr/bin/env python3
"""Tests für die USB-Smart-Dashboard-Anbindung (display.py)."""

import json
import time
from pathlib import Path

import pytest

from iwfcam4hermes import display


def _install_plugin(home: Path, enabled=True, version="0.5.0"):
    plugin = home / "plugins" / "usb-smart-dashboard"
    plugin.mkdir(parents=True, exist_ok=True)
    (plugin / "plugin.yaml").write_text(
        f"name: usb-smart-dashboard\nversion: {version}\n", encoding="utf-8")
    config = home / "config.yaml"
    config.write_text(
        "plugins:\n  enabled:\n    - usb-smart-dashboard\n" if enabled else
        "plugins:\n  enabled: []\n", encoding="utf-8")


def test_dashboard_status_detects_loaded_plugin(tmp_path, monkeypatch):
    _install_plugin(tmp_path, enabled=True, version="0.5.0")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(display, "_service_active", lambda: False)
    info = display.dashboard_status()
    assert info["installed"] is True
    assert info["loaded"] is True
    assert info["version"] == "0.5.0"
    assert info["inbox"] == str(tmp_path / "usb-smart-dashboard")


def test_dashboard_status_not_loaded(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(display, "_service_active", lambda: False)
    info = display.dashboard_status()
    assert info["installed"] is False and info["loaded"] is False


def test_publish_and_active_image(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    jpeg = b"\xff\xd8test-jpeg\xff\xd9"
    path = display.publish(jpeg, duration=30, source="unit")
    assert path is not None and path.read_bytes() == jpeg
    meta = json.loads((tmp_path / "usb-smart-dashboard" / "show-image.json").read_text())
    assert meta["duration"] == 30 and meta["source"] == "unit"
    active = display.active_image()
    assert active is not None and active["source"] == "unit" and active["remaining"] > 0


def test_active_image_expires(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    display.publish(b"\xff\xd8x\xff\xd9", duration=2)
    assert display.active_image() is not None
    real_time = time.time
    monkeypatch.setattr(display.time, "time", lambda: real_time() + 10)
    assert display.active_image() is None


def test_publish_rejects_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert display.publish(b"") is None
