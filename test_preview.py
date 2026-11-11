#!/usr/bin/env python3
"""Tests für die Vorschau-Qualitätsstufen (preview.py)."""

from io import BytesIO

import pytest

from iwfcam4hermes import preview


def _jpeg(size=(640, 480), color=(120, 80, 60)):
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        pytest.skip("Pillow nicht installiert")
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def test_quality_presets_defined():
    assert set(preview.QUALITY_PRESETS) == {"original", "high", "medium", "low"}
    assert preview.DEFAULT_QUALITY == "medium"
    info = preview.quality_info()
    assert info["default"] == preview.DEFAULT_QUALITY
    assert "presets" in info


def test_normalize_quality_and_fps():
    assert preview.normalize_quality("LOW") == "low"
    assert preview.normalize_quality("quatsch") == preview.DEFAULT_QUALITY
    assert preview.normalize_fps(0) == 1
    assert preview.normalize_fps(99) == 30
    assert preview.normalize_fps("7") == 7
    assert preview.normalize_fps(None) == preview.DEFAULT_FPS


@pytest.mark.skipif(not preview.pil_available(), reason="Pillow fehlt")
def test_reencode_scales_and_compresses():
    jpeg = _jpeg()
    original = preview.reencode(jpeg, "original")
    assert original == jpeg
    high = preview.reencode(jpeg, "high")
    medium = preview.reencode(jpeg, "medium")
    low = preview.reencode(jpeg, "low")
    assert len(medium) < len(high)
    assert len(low) < len(medium)
    # Auflösung sinkt gemäß Preset
    from PIL import Image
    assert Image.open(BytesIO(medium)).size == (384, 288)
    assert Image.open(BytesIO(low)).size == (256, 192)


@pytest.mark.skipif(not preview.pil_available(), reason="Pillow fehlt")
def test_reencode_max_width():
    jpeg = _jpeg(size=(640, 480))
    shrunk = preview.reencode(jpeg, "original", max_width=320)
    from PIL import Image
    assert Image.open(BytesIO(shrunk)).size == (320, 240)


def test_reencode_broken_input_returns_original():
    assert preview.reencode(b"not-a-jpeg", "high") == b"not-a-jpeg"
