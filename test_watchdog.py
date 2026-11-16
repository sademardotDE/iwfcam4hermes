#!/usr/bin/env python3
"""Tests für den Opt-in-Watchdog (watchdog.py) — ohne Hardware/NM."""

from iwfcam4hermes.watchdog import CameraWatchdog, canonical_uid


def _watchdog(*, cameras, devices, wifi=None, credentials=None, provision=None,
              public_ip="192.168.0.4", interval=300, cooldown=1800):
    calls = []

    def fake_provision(**kwargs):
        calls.append(kwargs)
        return provision or {"ok": True, "camera_uid": "635572396930"}

    watchdog = CameraWatchdog(
        cameras_fn=lambda: cameras,
        devices_fn=lambda: devices,
        wifi_fn=lambda: wifi or {"camera_aps": []},
        provision_fn=fake_provision,
        credentials_fn=lambda: credentials or {},
        public_ip=public_ip,
        signaling_port=8882,
        interval=interval,
        cooldown=cooldown,
    )
    return watchdog, calls


def test_canonical_uid():
    assert canonical_uid("ZIOTA_635572396930") == "635572396930"
    assert canonical_uid("635572396930") == "635572396930"
    assert canonical_uid(None) == ""


def test_skips_camera_that_is_streaming_or_paused():
    devices = [{"id": "cam2", "uid": "ZIOTA_635572396930"}]
    for state in ("streaming", "paused"):
        watchdog, calls = _watchdog(
            cameras=[{"uid": "635572396930", "state": state}], devices=devices,
            wifi={"camera_aps": [{"ssid": "ZIOTA_635572396930"}]},
            credentials={"ssid": "cccp4ever", "password": "geheim"},
        )
        assert watchdog.tick() == []
        assert calls == []


def test_provisions_offline_camera_with_visible_ap():
    watchdog, calls = _watchdog(
        cameras=[{"uid": "196758286858", "state": "streaming"}],
        devices=[
            {"id": "cam1", "uid": "ZIOTA_196758286858"},
            {"id": "cam2", "uid": "ZIOTA_635572396930"},
        ],
        wifi={"camera_aps": [{"ssid": "ZIOTA_635572396930"}]},
        credentials={"ssid": "cccp4ever", "password": "geheim"},
    )
    actions = watchdog.tick()
    assert [action["outcome"] for action in actions] == ["provisioned"]
    assert calls and calls[0]["camera_ssid"] == "ZIOTA_635572396930"
    assert calls[0]["ssid"] == "cccp4ever"
    assert calls[0]["server_ip"] == "192.168.0.4"
    assert calls[0]["auto_connect"] is True


def test_skips_without_credentials():
    watchdog, calls = _watchdog(
        cameras=[],
        devices=[{"id": "cam2", "uid": "ZIOTA_635572396930"}],
        wifi={"camera_aps": [{"ssid": "ZIOTA_635572396930"}]},
        credentials={},
    )
    actions = watchdog.tick()
    assert actions and actions[0]["outcome"] == "skipped"
    assert "Zugangsdaten" in actions[0]["reason"]
    assert calls == []


def test_skips_when_ap_not_visible():
    watchdog, calls = _watchdog(
        cameras=[], devices=[{"id": "cam2", "uid": "ZIOTA_635572396930"}],
        wifi={"camera_aps": []},
        credentials={"ssid": "cccp4ever", "password": "geheim"},
    )
    assert watchdog.tick() == []
    assert calls == []


def test_cooldown_prevents_repeated_provisioning():
    watchdog, calls = _watchdog(
        cameras=[], devices=[{"id": "cam2", "uid": "ZIOTA_635572396930"}],
        wifi={"camera_aps": [{"ssid": "ZIOTA_635572396930"}]},
        credentials={"ssid": "cccp4ever", "password": "geheim"},
        cooldown=1800,
    )
    assert len(watchdog.tick()) == 1
    assert len(calls) == 1
    assert watchdog.tick() == []          # Cooldown aktiv
    assert len(calls) == 1
    assert len(watchdog.tick(force=True)) == 1  # erzwungen
    assert len(calls) == 2


def test_failure_is_recorded():
    watchdog, calls = _watchdog(
        cameras=[], devices=[{"id": "cam2", "uid": "ZIOTA_635572396930"}],
        wifi={"camera_aps": [{"ssid": "ZIOTA_635572396930"}]},
        credentials={"ssid": "cccp4ever", "password": "geheim"},
        provision={"ok": False, "error": "kein ACK"},
    )
    actions = watchdog.tick()
    assert actions[0]["outcome"] == "failed"
    assert actions[0]["error"] == "kein ACK"
    assert len(calls) == 1


def test_status_reports_actions_and_cooldown():
    watchdog, _calls = _watchdog(
        cameras=[], devices=[{"id": "cam2", "uid": "ZIOTA_635572396930"}],
        wifi={"camera_aps": [{"ssid": "ZIOTA_635572396930"}]},
        credentials={"ssid": "cccp4ever", "password": "geheim"},
    )
    watchdog.tick()
    status = watchdog.status()
    assert status["enabled"] is True
    assert status["running"] is False
    assert status["actions"][-1]["outcome"] == "provisioned"
    assert status["last_run_age_s"] is not None
    assert status["cooldown_remaining_s"]
