"""JPEG-Vorschau-Qualität für den Relay-Server (Skalierung + Re-Encoding).

Die Kamera liefert MJPEG in fester Auflösung (z. B. 640×480). Für Vorschau,
Dashboard und Snapshots lässt sich die Qualität serverseitig einstellen:
``original`` (unverändert), ``high``, ``medium``, ``low`` — jeweils
Skalierungsfaktor + JPEG-Qualität. Ohne Pillow wird das Original
zurückgegeben (kein Fehler).

Die *Kamera-interne* Stream-Qualität ist bei dieser Firmware nicht per
Protokoll einstellbar (Clarity-/Property-Kommandos wurden getestet und
bewirken nichts — siehe ``docs/PROTOCOL.md``).
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

QUALITY_PRESETS: dict[str, dict[str, Any]] = {
    "original": {"scale": 1.0, "jpeg_quality": None},
    "high": {"scale": 0.8, "jpeg_quality": 80},
    "medium": {"scale": 0.6, "jpeg_quality": 65},
    "low": {"scale": 0.4, "jpeg_quality": 45},
}
QUALITY_NAMES = tuple(QUALITY_PRESETS)
DEFAULT_QUALITY = "medium"
DEFAULT_FPS = 5

_PIL = None
_PIL_CHECKED = False


def _pil():
    """Pillow lazy laden (None, wenn nicht installiert)."""
    global _PIL, _PIL_CHECKED
    if not _PIL_CHECKED:
        _PIL_CHECKED = True
        try:
            from PIL import Image  # noqa: F401
            _PIL = Image
        except Exception:  # pragma: no cover - abhängig vom Interpreter
            _PIL = None
    return _PIL


def pil_available() -> bool:
    return _pil() is not None


def normalize_quality(value: Any) -> str:
    quality = str(value or "").strip().lower()
    return quality if quality in QUALITY_PRESETS else DEFAULT_QUALITY


def normalize_fps(value: Any) -> int:
    try:
        fps = int(value)
    except (TypeError, ValueError):
        return DEFAULT_FPS
    return max(1, min(30, fps))


def quality_info() -> dict[str, Any]:
    return {
        "presets": list(QUALITY_NAMES),
        "default": DEFAULT_QUALITY,
        "default_fps": DEFAULT_FPS,
        "pil": pil_available(),
        "details": QUALITY_PRESETS,
    }


def reencode(jpeg: bytes, quality: str = DEFAULT_QUALITY,
             max_width: int | None = None) -> bytes:
    """JPEG gemäß Qualitätsstufe skalieren/neu komprimieren (Original bei Fehler)."""
    if not jpeg:
        return jpeg
    preset = QUALITY_PRESETS[normalize_quality(quality)]
    if preset["jpeg_quality"] is None and max_width is None:
        return jpeg
    Image = _pil()
    if Image is None:
        return jpeg
    try:
        image = Image.open(BytesIO(jpeg))
        image = image.convert("RGB")
        width, height = image.size
        target_width = int(width * float(preset["scale"]))
        if max_width:
            target_width = min(target_width, int(max_width))
        target_width = max(16, target_width)
        if target_width != width:
            target_height = max(12, int(height * target_width / width))
            resample = getattr(Image, "Resampling", Image).LANCZOS
            image = image.resize((target_width, target_height), resample)
        out = BytesIO()
        image.save(out, format="JPEG", quality=preset["jpeg_quality"] or 85, optimize=True)
        return out.getvalue()
    except Exception:  # pragma: no cover - kaputtes JPEG o. Ä.
        return jpeg
