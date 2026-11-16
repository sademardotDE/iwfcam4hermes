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


def test_snapshot_store_automatic_interval(tmp_path):
    """Der Hintergrund-Thread speichert selbstständig im eingestellten Intervall."""
    import time

    jpeg = _test_jpeg() or b"\xff\xd8AUTO\xff\xd9"
    server = relay.RelayServer(
        "127.0.0.1", signaling_port=0, media_port=0, stun_port=0,
        http_host="127.0.0.1", http_port=0,
        snapshot_dir=str(tmp_path), snapshot_interval=1, snapshot_retain=5,
    )
    server.start()
    try:
        media = server.receiver.media_hub.acquire("196758286858")
        media._latest = jpeg
        deadline = time.time() + 4
        while time.time() < deadline:
            if server.snapshot_store.stats()["total"] >= 1:
                break
            time.sleep(0.1)
        assert server.snapshot_store.stats()["total"] >= 1
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

def test_watchdog_status_disabled_and_run_rejected():
    server = relay.RelayServer(
        "127.0.0.1", signaling_port=0, media_port=0, stun_port=0,
        http_host="127.0.0.1", http_port=0,
    )
    info = server.start()
    try:
        assert info["watchdog"]["enabled"] is False
        with urllib.request.urlopen(f"http://127.0.0.1:{info['http_port']}/watchdog", timeout=5) as response:
            payload = json.loads(response.read())
        assert payload["ok"] is True and payload["enabled"] is False
        request = urllib.request.Request(
            f"http://127.0.0.1:{info['http_port']}/watchdog/run", data=b"", method="POST")
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(request, timeout=5)
        assert excinfo.value.code == 400
    finally:
        server.stop()


def test_watchdog_enabled_reports_status():
    server = relay.RelayServer(
        "127.0.0.1", signaling_port=0, media_port=0, stun_port=0,
        http_host="127.0.0.1", http_port=0,
        watchdog=True, watchdog_interval=3600, watchdog_cooldown=1800,
    )
    info = server.start()
    try:
        assert info["watchdog"]["enabled"] is True
        assert info["watchdog"]["interval"] == 3600
        assert info["watchdog"]["cooldown"] == 1800
        with urllib.request.urlopen(f"http://127.0.0.1:{info['http_port']}/watchdog", timeout=5) as response:
            payload = json.loads(response.read())
        assert payload["ok"] is True and payload["enabled"] is True
    finally:
        server.stop()

def _motion_jpegs():
    """Zwei synthetische JPEGs (schwarz / weißes Quadrat) für Bewegungstests."""
    try:
        from io import BytesIO

        from PIL import Image, ImageDraw
    except ImportError:  # pragma: no cover
        return None
    first = Image.new("RGB", (320, 240), (0, 0, 0))
    second = Image.new("RGB", (320, 240), (0, 0, 0))
    draw = ImageDraw.Draw(second)
    draw.rectangle([80, 60, 240, 180], fill=(255, 255, 255))
    out = []
    for image in (first, second):
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        out.append(buffer.getvalue())
    return out


def test_motion_disabled_by_default():
    server = relay.RelayServer(
        "127.0.0.1", signaling_port=0, media_port=0, stun_port=0,
        http_host="127.0.0.1", http_port=0,
    )
    info = server.start()
    try:
        assert info["motion"]["enabled"] is False
        with urllib.request.urlopen(f"http://127.0.0.1:{info['http_port']}/motion", timeout=5) as response:
            payload = json.loads(response.read())
        assert payload["ok"] is True and payload["enabled"] is False
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(f"http://127.0.0.1:{info['http_port']}/motion/events", timeout=5)
        assert excinfo.value.code == 400
    finally:
        server.stop()


def test_motion_detects_and_lists_events(tmp_path):
    frames = _motion_jpegs()
    if frames is None:  # pragma: no cover
        pytest.skip("Pillow fehlt")
    server = relay.RelayServer(
        "127.0.0.1", signaling_port=0, media_port=0, stun_port=0,
        http_host="127.0.0.1", http_port=0,
        motion=True, motion_sensitivity=90, motion_cooldown=0,
        snapshot_dir=str(tmp_path), motion_snapshot=True,
    )
    info = server.start()
    try:
        assert info["motion"]["enabled"] is True
        uid = "196758286858"
        server.motion.feed(uid, frames[0])
        event = server.motion.feed(uid, frames[1])
        assert event is not None
        with urllib.request.urlopen(f"http://127.0.0.1:{info['http_port']}/motion", timeout=5) as response:
            payload = json.loads(response.read())
        assert payload["ok"] is True and payload["enabled"] is True
        assert payload["cameras"][uid]["events"] == 1
        with urllib.request.urlopen(
                f"http://127.0.0.1:{info['http_port']}/motion/events?uid={uid}", timeout=5) as response:
            events = json.loads(response.read())["events"]
        assert len(events) == 1 and events[0]["uid"] == uid
        assert list((tmp_path / uid / "motion").glob("*.jpg"))
    finally:
        server.stop()

def test_motion_webhook_in_unit_and_settings(tmp_path):
    cfg = relay.settings_from({"relay_motion": True, "relay_motion_webhook": "http://example/hook"})
    assert cfg["motion"] is True and cfg["motion_webhook"] == "http://example/hook"
    unit = relay.render_unit(
        python="/usr/bin/python3", plugin_root=tmp_path, public_ip="192.168.0.4",
        motion=True, motion_webhook="http://example/hook",
    )
    assert "--motion" in unit
    assert "--motion-webhook" in unit and "http://example/hook" in unit

def test_multi_webhook_settings_and_unit(tmp_path):
    cfg = relay.settings_from({
        "relay_motion": True,
        "relay_motion_webhooks": "slack|https://hooks.slack.com/services/x\nhttps://example.com/h",
    })
    assert len(cfg["motion_webhooks"]) == 2
    unit = relay.render_unit(
        python="/usr/bin/python3", plugin_root=tmp_path, public_ip="192.168.0.4",
        motion=True, motion_webhooks=cfg["motion_webhooks"],
    )
    assert unit.count("--motion-webhook") == 2
    assert "hooks.slack.com" in unit and "example.com/h" in unit


def test_motion_test_endpoint_sends_to_webhooks():
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            received.append(self.rfile.read(length))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    webhook = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=webhook.serve_forever, daemon=True).start()
    hook_url = f"http://127.0.0.1:{webhook.server_address[1]}/hook"
    server = relay.RelayServer(
        "127.0.0.1", signaling_port=0, media_port=0, stun_port=0,
        http_host="127.0.0.1", http_port=0,
        motion=True, motion_webhooks=[hook_url],
    )
    info = server.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{info['http_port']}/motion/test", data=b"", method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = _json.loads(response.read())
        assert payload["ok"] is True and payload["webhooks"] == 1
        deadline = __import__("time").time() + 5
        while __import__("time").time() < deadline and not received:
            __import__("time").sleep(0.05)
        assert received
        body = _json.loads(received[0])
        assert body.get("test") is True and body["event"] == "motion"
    finally:
        server.stop()
        webhook.shutdown()
        webhook.server_close()

def test_motion_test_endpoint_includes_snapshot_photo(tmp_path):
    import json as _json
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    frames = _motion_jpegs()
    if frames is None:  # pragma: no cover
        pytest.skip("Pillow fehlt")
    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            captured.append({"content_type": self.headers.get("Content-Type"),
                             "body": self.rfile.read(length)})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    webhook = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=webhook.serve_forever, daemon=True).start()
    hook_url = f"telegram|http://127.0.0.1:{webhook.server_address[1]}/sendPhoto?chat_id=42"
    server = relay.RelayServer(
        "127.0.0.1", signaling_port=0, media_port=0, stun_port=0,
        http_host="127.0.0.1", http_port=0,
        motion=True, motion_webhooks=[hook_url], motion_photo=True,
    )
    info = server.start()
    try:
        media = server.receiver.media_hub.acquire("196758286858")
        media._latest = frames[1]
        request = urllib.request.Request(
            f"http://127.0.0.1:{info['http_port']}/motion/test", data=b"", method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = _json.loads(response.read())
        assert payload["ok"] is True and payload["webhooks"] == 1
        deadline = time.time() + 5
        while time.time() < deadline and not captured:
            time.sleep(0.05)
        assert captured
        entry = captured[0]
        assert entry["content_type"].startswith("multipart/form-data")
        assert b'name="photo"' in entry["body"] and b"\xff\xd8" in entry["body"]
    finally:
        server.stop()
        webhook.shutdown()
        webhook.server_close()

