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

def _capture_server():
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            captured.append({
                "path": self.path,
                "headers": {key.lower(): value for key, value in self.headers.items()},
                "body": self.rfile.read(length),
            })
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, captured


def _wait_for(captured, count, timeout=6.0):
    import time
    deadline = time.time() + timeout
    while time.time() < deadline and len(captured) < count:
        time.sleep(0.05)
    return captured


def test_parse_webhook_specs_variants():
    assert motion.parse_webhook_specs("") == []
    single = motion.parse_webhook_specs("https://example.com/hook")
    assert single == [{"type": "generic", "url": "https://example.com/hook", "chat_id": ""}]
    typed = motion.parse_webhook_specs("slack|https://hooks.slack.com/services/x")
    assert typed[0]["type"] == "slack"
    tg = motion.parse_webhook_specs(
        "telegram|https://api.telegram.org/botX/sendMessage?chat_id=42")
    assert tg[0]["type"] == "telegram" and tg[0]["chat_id"] == "42"
    assert "chat_id" not in tg[0]["url"]
    multi = motion.parse_webhook_specs("ntfy|https://ntfy.sh/topic\nhttps://example.com/x")
    assert [item["type"] for item in multi] == ["ntfy", "generic"]
    json_list = motion.parse_webhook_specs('["https://a.example/h", "https://b.example/h"]')
    assert len(json_list) == 2


def test_multi_webhooks_receive_typed_payloads():
    import json as _json

    server, captured = _capture_server()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    specs = "\n".join([
        f"slack|{base}/slack",
        f"discord|{base}/discord",
        f"ntfy|{base}/ntfy",
        f"telegram|{base}/tg?chat_id=42",
        f"{base}/generic",
    ])
    try:
        hub = motion.MotionHub(sensitivity=90, cooldown=0, webhooks=specs, send_photo=False)
        hub.feed("ZIOTA_TESTCAM01", _black())
        hub.feed("ZIOTA_TESTCAM01", _square())
        _wait_for(captured, 5)
        by_path = {item["path"]: item for item in captured}
        assert len(by_path) == 5, [item["path"] for item in captured]

        slack = _json.loads(by_path["/slack"]["body"])
        assert "text" in slack and "Bewegung erkannt" in slack["text"]
        discord = _json.loads(by_path["/discord"]["body"])
        assert "content" in discord and "Bewegung" in discord["content"]
        assert by_path["/ntfy"]["headers"]["content-type"].startswith("text/plain")
        assert "Bewegung erkannt" in by_path["/ntfy"]["body"].decode()
        telegram = _json.loads(by_path["/tg"]["body"])
        assert telegram["chat_id"] == "42" and "text" in telegram
        generic = _json.loads(by_path["/generic"]["body"])
        assert generic["event"] == "motion" and generic["uid"] == "TESTCAM01"
    finally:
        server.shutdown()
        server.server_close()


def test_send_test_reaches_all_webhooks():
    server, captured = _capture_server()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        hub = motion.MotionHub(webhooks=f"{base}/a\n{base}/b")
        result = hub.send_test()
        assert result["ok"] is True and result["webhooks"] == 2
        _wait_for(captured, 2)
        assert {item["path"] for item in captured} == {"/a", "/b"}
        import json as _json
        payload = _json.loads(captured[0]["body"])
        assert payload.get("test") is True and payload["score"] == 0.0
    finally:
        server.shutdown()
        server.server_close()


def test_status_lists_webhooks_without_tokens():
    hub = motion.MotionHub(webhooks="slack|https://hooks.slack.com/services/SECRET")
    status = hub.status()
    assert status["webhook_count"] == 1
    assert status["webhooks"] == [{"type": "slack", "host": "hooks.slack.com"}]
    assert "SECRET" not in str(status)

def test_telegram_webhook_sends_photo_multipart():
    import json as _json
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            captured.append({"path": self.path,
                             "content_type": self.headers.get("Content-Type"),
                             "body": self.rfile.read(length)})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    spec = f"telegram|http://127.0.0.1:{server.server_address[1]}/sendPhoto?chat_id=42"
    try:
        hub = motion.MotionHub(sensitivity=90, cooldown=0, webhooks=spec, photo_mode="photo")
        hub.feed("ZIOTA_TESTCAM01", _black())
        hub.feed("ZIOTA_TESTCAM01", _square())
        deadline = time.time() + 5
        while time.time() < deadline and not captured:
            time.sleep(0.05)
        assert captured, "Kein Telegram-Aufruf"
        entry = captured[0]
        assert entry["path"].startswith("/sendPhoto")
        assert entry["content_type"].startswith("multipart/form-data")
        body = entry["body"]
        assert b'name="chat_id"' in body and b"42" in body
        assert b'name="caption"' in body and "Bewegung erkannt".encode() in body
        assert b'name="photo"' in body and b"\xff\xd8" in body
    finally:
        server.shutdown()
        server.server_close()


def test_telegram_falls_back_to_text_when_photo_rejected():
    import json as _json
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length)
            captured.append({"path": self.path,
                             "content_type": self.headers.get("Content-Type"), "body": body})
            if "multipart/form-data" in (self.headers.get("Content-Type") or ""):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"ok":false}')
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    spec = f"telegram|http://127.0.0.1:{server.server_address[1]}/sendMessage?chat_id=42"
    try:
        hub = motion.MotionHub(sensitivity=90, cooldown=0, webhooks=spec)
        hub.feed("ZIOTA_TESTCAM01", _black())
        hub.feed("ZIOTA_TESTCAM01", _square())
        deadline = time.time() + 6
        while time.time() < deadline and len(captured) < 2:
            time.sleep(0.05)
        assert len(captured) == 2
        assert captured[0]["path"].startswith("/sendDocument")
        assert captured[0]["content_type"].startswith("multipart/form-data")
        assert captured[1]["path"].startswith("/sendMessage")
        fallback = captured[1]
        assert fallback["content_type"].startswith("application/json")
        payload = _json.loads(fallback["body"])
        assert payload["chat_id"] == "42" and "Bewegung erkannt" in payload["text"]
    finally:
        server.shutdown()
        server.server_close()


def test_photo_can_be_disabled():
    hub = motion.MotionHub(webhooks="telegram|https://api.telegram.org/botX/sendMessage?chat_id=1",
                           send_photo=False)
    assert hub.status()["send_photo"] is False
    url, headers, body = motion.webhook_request(
        motion.parse_webhook_specs("telegram|https://api.telegram.org/botX/sendMessage?chat_id=1")[0],
        {"uid": "cam", "score": 0.1, "ts": time.time(), "event": "motion"})
    assert headers["Content-Type"].startswith("application/json")

def test_telegram_document_mode_sends_original_file():
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            captured.append({"path": self.path, "content_type": self.headers.get("Content-Type"),
                             "body": self.rfile.read(length)})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    spec = f"telegram|http://127.0.0.1:{server.server_address[1]}/sendMessage?chat_id=42"
    try:
        hub = motion.MotionHub(sensitivity=90, cooldown=0, webhooks=spec)  # default: document
        hub.feed("ZIOTA_TESTCAM01", _black())
        hub.feed("ZIOTA_TESTCAM01", _square())
        deadline = time.time() + 5
        while time.time() < deadline and not captured:
            time.sleep(0.05)
        assert captured
        entry = captured[0]
        assert entry["path"].startswith("/sendDocument")
        assert b'name="document"' in entry["body"]
        assert b'name="caption"' in entry["body"]
        assert b"\xff\xd8" in entry["body"]
        assert hub.status()["photo_mode"] == "document"
    finally:
        server.shutdown()
        server.server_close()

