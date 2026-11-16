#!/usr/bin/env python3
"""Tests für den Bewegungsmelder (motion.py) — mit synthetischen JPEGs."""

import json
import time
from io import BytesIO

import pytest

pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402

from iwfcam4hermes import motion  # noqa: E402


def _jpeg(image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def _black(width=320, height=240) -> bytes:
    return _jpeg(Image.new("RGB", (width, height), (0, 0, 0)))


def _square(width=320, height=240) -> bytes:
    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle([80, 60, 240, 180], fill=(255, 255, 255))
    return _jpeg(image)


def test_sensitivity_threshold_mapping():
    assert motion.sensitivity_threshold(1) > motion.sensitivity_threshold(50)
    assert motion.sensitivity_threshold(50) > motion.sensitivity_threshold(100)
    assert motion.sensitivity_threshold(100) > 0
    assert motion.sensitivity_threshold("quatsch") == motion.sensitivity_threshold(50)


def test_frame_score_same_and_different():
    gray_a = bytes([10] * 100)
    gray_b = bytes([10] * 100)
    gray_c = bytes([255] * 100)
    assert motion.frame_score(gray_a, gray_b) == 0.0
    assert motion.frame_score(gray_a, gray_c) == 1.0
    assert motion.frame_score(b"", gray_a) == 0.0


def test_detector_needs_two_frames():
    detector = motion.MotionDetector(sensitivity=90)
    assert detector.analyse(_black()) is None
    assert detector.analyse(_black()) is None  # identische Frames -> keine Bewegung


def test_detector_reports_motion():
    detector = motion.MotionDetector(sensitivity=90, cooldown=0)
    detector.analyse(_black())
    event = detector.analyse(_square())
    assert event is not None
    assert event["score"] > 0.05
    status = detector.status()
    assert status["events"] == 1
    assert status["last_motion_age_s"] is not None
    assert status["score"] > 0


def test_detector_cooldown_suppresses_events():
    detector = motion.MotionDetector(sensitivity=90, cooldown=3600)
    detector.analyse(_black())
    first = detector.analyse(_square())
    assert first is not None
    detector._previous = None  # neuen Vergleich erzwingen, ohne Cooldown zu umgehen
    detector.analyse(_black())
    second = detector.analyse(_square())
    assert second is None
    assert detector.status()["events"] == 1


def test_detector_calls_on_motion():
    seen = []
    detector = motion.MotionDetector(sensitivity=90, cooldown=0,
                                     on_motion=lambda jpeg, event: seen.append((len(jpeg), event)))
    detector.analyse(_black())
    detector.analyse(_square())
    assert len(seen) == 1 and seen[0][0] > 0


def test_hub_detects_per_camera_and_writes_snapshot(tmp_path):
    hub = motion.MotionHub(sensitivity=90, cooldown=0, snapshot_root=tmp_path)
    hub.feed("ZIOTA_TESTCAM01", _black())
    assert hub.feed("ZIOTA_TESTCAM01", _square()) is not None

    files = list((tmp_path / "TESTCAM01" / "motion").glob("*.jpg"))
    assert len(files) == 1 and files[0].stat().st_size > 0

    status = hub.status("ZIOTA_TESTCAM01")
    assert status["enabled"] and status["events"] == 1
    events = hub.events("ZIOTA_TESTCAM01")
    assert len(events) == 1 and events[0]["uid"] == "TESTCAM01"

    summary = hub.status()
    assert summary["enabled"] and "TESTCAM01" in summary["cameras"]


def test_hub_without_snapshot_dir_writes_nothing(tmp_path):
    hub = motion.MotionHub(sensitivity=90, cooldown=0, snapshot_root=None)
    hub.feed("cam", _black())
    hub.feed("cam", _square())
    assert hub.events("cam")
    assert not list(tmp_path.iterdir())


def test_hub_merged_events():
    hub = motion.MotionHub(sensitivity=90, cooldown=0)
    for uid in ("cam-a", "cam-b"):
        hub.feed(uid, _black())
        hub.feed(uid, _square())
    events = hub.events(limit=10)
    assert len(events) == 2
    assert {event["uid"] for event in events} == {"cam-a", "cam-b"}

def test_default_sensitivity_detects_quarter_frame_change():
    detector = motion.MotionDetector(sensitivity=50, cooldown=0)
    detector.analyse(_black())
    event = detector.analyse(_square())
    assert event is not None
    assert detector.threshold < 0.05

def test_motion_webhook_posts_json():
    import json
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            received.append(json.loads(self.rfile.read(length)))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        hub = motion.MotionHub(
            sensitivity=90, cooldown=0,
            webhook=f"http://127.0.0.1:{server.server_address[1]}/hook")
        hub.feed("ZIOTA_TESTCAM01", _black())
        hub.feed("ZIOTA_TESTCAM01", _square())
        deadline = time.time() + 5
        while time.time() < deadline and not received:
            time.sleep(0.05)
        assert received, "Webhook wurde nicht aufgerufen"
        payload = received[0]
        assert payload["event"] == "motion"
        assert payload["uid"] == "TESTCAM01"
        assert payload["score"] > 0
        assert "ts_iso" in payload
        assert "Bewegung erkannt" in payload["text"]
        assert payload["content"] == payload["text"]
    finally:
        server.shutdown()
        server.server_close()


def test_wait_for_motion_returns_new_event(monkeypatch):
    from iwfcam4hermes import plugin_tools, relay

    class Ctx:
        def get_config(self, key, default=None):
            return default

    now = time.time()
    monkeypatch.setattr(relay, "motion_events",
                        lambda host, port, uid=None, limit=20: [
                            {"ts": now, "score": 0.2, "uid": "196758286858"}])
    monkeypatch.setattr(plugin_tools.time, "sleep", lambda seconds: None)
    result = json.loads(plugin_tools._h_camera_motion(Ctx(), {"action": "wait", "timeout": 5}))
    assert result["ok"] is True
    assert result["events"][0]["uid"] == "196758286858"
    assert "waited_s" in result


def test_wait_for_motion_without_events_times_out(monkeypatch):
    from iwfcam4hermes import plugin_tools, relay

    class Ctx:
        def get_config(self, key, default=None):
            return default

    monkeypatch.setattr(relay, "motion_events",
                        lambda host, port, uid=None, limit=20: [])
    monkeypatch.setattr(plugin_tools.time, "sleep", lambda seconds: None)
    # Zeit künstlich schnell vergehen lassen
    real_time = time.time
    state = {"t": real_time()}
    def fake_time():
        state["t"] += 10
        return state["t"]
    monkeypatch.setattr(plugin_tools.time, "time", fake_time)
    result = json.loads(plugin_tools._h_camera_motion(Ctx(), {"action": "wait", "timeout": 1}))
    assert result["ok"] is True
    assert result["timed_out"] is True
    assert result["events"] == []

