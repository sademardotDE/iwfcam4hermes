#!/usr/bin/env python3
"""Tests für Autoconf (Discovery + automatisches Anlegen) — ohne echte Hardware."""

import json

import pytest

from iwfcam4hermes import autoconf, config_store


def test_parse_wifi_multiline():
    text = "\n".join([
        "SSID:cccp4ever", "BSSID:08:7E:64:C7:90:00", "SIGNAL:100", "SECURITY:WPA2",
        "SSID:ZIOTA_196758286858", "BSSID:C6:26:44:28:5F:18", "SIGNAL:64", "SECURITY:",
        "SSID:ZIOTA_635572396930", "BSSID:46:E4:A5:63:4B:2C", "SIGNAL:79", "SECURITY:",
    ])
    networks = autoconf.parse_wifi_multiline(text)
    assert [n["ssid"] for n in networks] == ["cccp4ever", "ZIOTA_196758286858", "ZIOTA_635572396930"]
    assert networks[1]["bssid"] == "C6:26:44:28:5F:18"
    assert networks[1]["signal"] == "64"


def test_parse_wifi_ssid_only_unescapes_colons():
    networks = autoconf.parse_wifi_ssid_only("WLAN\\:Test\nZIOTA_123\n")
    assert networks[0]["ssid"] == "WLAN:Test"
    assert networks[1]["ssid"] == "ZIOTA_123"


@pytest.mark.parametrize("url,expected", [
    ("rtsp://192.168.1.1:7070/webcam/jpeg_dvp",
     {"host": "192.168.1.1", "port": 7070, "path": "/webcam/jpeg_dvp"}),
    ("rtsp://10.0.0.2/live", {"host": "10.0.0.2", "port": 554, "path": "/live"}),
    ("http://example/x", None),
])
def test_parse_rtsp_url(url, expected):
    assert autoconf.parse_rtsp_url(url) == expected


def test_discover_merges_wifi_and_ble(monkeypatch):
    monkeypatch.setattr(autoconf, "discover_wifi", lambda **kw: [
        {"ssid": "ZIOTA_196758286858", "bssid": "C6:26:44:28:5F:18",
         "signal": 64, "security": None},
    ])
    monkeypatch.setattr(autoconf, "discover_ble", lambda timeout=8.0: ([
        {"ble_name": "ZIOTA_196758286858", "ble_address": "18:5F:28:44:26:C6", "ble_rssi": -62},
        {"ble_name": "ZIOTA_635572396930", "ble_address": "2C:4B:63:A5:E4:46", "ble_rssi": -70},
    ], None))
    monkeypatch.setattr(autoconf, "current_ap", lambda: None)

    result = autoconf.discover(mode="both")
    cams = {c["uid"]: c for c in result["cameras"]}
    assert set(cams) == {"ZIOTA_196758286858", "ZIOTA_635572396930"}
    assert cams["ZIOTA_196758286858"]["sources"] == ["wifi", "ble"]
    assert cams["ZIOTA_635572396930"]["sources"] == ["ble"]
    assert result["ble_error"] is None


def test_suggest_device_uses_ap_mode_rtsp():
    camera = {"uid": "ZIOTA_196758286858", "ssid": "ZIOTA_196758286858",
              "sources": ["wifi"], "rtsp_url": "rtsp://192.168.1.1:7070/webcam/jpeg_dvp",
              "ap_gateway": "192.168.1.1"}
    device = autoconf.suggest_device(camera)
    assert device["id"] == "ziota-196758286858"
    assert device["uid"] == "ZIOTA_196758286858"
    assert device["type"] == "iwfcam"
    assert device["host"] == "192.168.1.1"
    assert device["port"] == 7070
    assert device["stream_path"] == "/webcam/jpeg_dvp"
    assert device["relay_mode"] is True
    assert "ZIOTA_196758286858" in device["notes"]


def test_device_id_is_unique():
    taken = {"ziota-1"}
    assert autoconf._device_id("ZIOTA_1", taken) == "ziota-1-2"


def _patch_discovery(monkeypatch):
    monkeypatch.setattr(autoconf, "discover", lambda **kw: {
        "ok": True, "mode": "both", "cameras": [
            {"uid": "ZIOTA_196758286858", "sources": ["wifi"],
             "ssid": "ZIOTA_196758286858", "rtsp_url": "rtsp://192.168.1.1:7070/webcam/jpeg_dvp",
             "ap_gateway": "192.168.1.1"},
        ], "wifi": [], "ble": [], "ble_error": None, "current_ap": None,
    })


def test_autoconf_dry_run_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("IWFCAM_CONFIG", raising=False)
    _patch_discovery(monkeypatch)

    result = autoconf.autoconf(apply=False)
    assert result["found"] == 1
    assert len(result["suggestions"]) == 1
    assert result["added"] == []
    assert not config_store.user_config_path().exists()


def test_autoconf_apply_creates_config_and_skips_duplicates(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("IWFCAM_CONFIG", raising=False)
    _patch_discovery(monkeypatch)

    first = autoconf.autoconf(apply=True)
    assert first["added"], "Kamera sollte angelegt werden"
    written = json.loads(config_store.user_config_path().read_text(encoding="utf-8"))
    assert [device["id"] for device in written["devices"]] == ["ziota-196758286858"]

    second = autoconf.autoconf(apply=True)
    assert second["added"] == []
    assert second["skipped"] and second["skipped"][0]["uid"] == "ZIOTA_196758286858"
    assert len(second["cameras"]) == 1

def test_ble_fallback_uses_subprocess(monkeypatch):
    """Fehlt bleak im Plugin-Prozess, wird der Scan über einen System-Python gemacht."""
    import sys

    import autoconf as ac

    monkeypatch.setitem(sys.modules, "bleak", None)  # import bleak -> ImportError

    def fake_subprocess(timeout):
        return [{"ble_name": "ZIOTA_TEST0001", "ble_address": "AA:BB", "ble_rssi": -40}], None

    monkeypatch.setattr(ac, "_ble_via_subprocess", fake_subprocess)
    devices, error = ac.discover_ble(timeout=1)
    assert devices == [{"ble_name": "ZIOTA_TEST0001", "ble_address": "AA:BB", "ble_rssi": -40}]
    assert error is None


def test_ble_fallback_reports_error_when_no_interpreter_has_bleak(monkeypatch):
    import sys

    import autoconf as ac

    monkeypatch.setitem(sys.modules, "bleak", None)
    monkeypatch.setattr(ac, "_ble_via_subprocess", lambda timeout: (None, "No module named 'bleak'"))
    devices, error = ac.discover_ble(timeout=1)
    assert devices == []
    assert error and "BLE-Scan nicht möglich" in error

