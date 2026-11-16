#!/usr/bin/env python3
"""Tests für den Bewegungsmelder (motion.py) — mit synthetischen JPEGs."""

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

