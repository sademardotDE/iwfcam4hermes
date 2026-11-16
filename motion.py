"""Bewegungsmelder auf Basis der vom Relay empfangenen JPEG-Frames.

Der Relay bekommt ohnehin jedes Kamerabild (RTP/JPEG). Für jede Kamera wird ein
``MotionDetector`` gefüttert, der aufeinanderfolgende Frames vergleicht:

1. JPEG → Graustufen, auf 64×48 herunterskalieren (schnell, rauscharm)
2. Pixel-Differenz zählen (Schwelle pro Pixel), Anteil = ``score``
3. ``score`` über der sensitivitätsabhängigen Schwelle + Cooldown abgelaufen
   → Bewegungsereignis (optional mit Snapshot)
4. Ereignisse werden pro Kamera im Ringpuffer gehalten (max. 50)

Die Detektoren sind unabhängig von der Kamera-Hardware und damit mit
synthetischen JPEGs testbar (Pillow nötig; fehlt es, ist der Melder inaktiv).
"""

from __future__ import annotations

import io
import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - Relay läuft mit Pillow
    Image = None  # type: ignore[assignment]
    PIL_AVAILABLE = False

log = logging.getLogger("iwfcam4hermes.motion")

#: Analyse-Auflösung (Graustufen); klein genug, um pro Frame günstig zu sein.
ANALYSE_SIZE = (64, 48)
#: Pixel gelten als „geändert", wenn sich der Grauwert um mehr als das ändert.
PIXEL_DELTA = 16
#: Maximale Anzahl gehaltener Ereignisse pro Kamera.
MAX_EVENTS = 50


def sensitivity_threshold(sensitivity: int | float) -> float:
    """Sensitivität (1–100) → Anteil geänderter Pixel, ab dem Bewegung gilt.

    1 → sehr unempfindlich (0.30), 50 → 0.16, 100 → sehr empfindlich (0.05).
    """
    try:
        value = max(1.0, min(100.0, float(sensitivity)))
    except (TypeError, ValueError):
        value = 50.0
    return round(0.30 - 0.25 * (value - 1.0) / 99.0, 4)


def frame_score(previous: bytes, current: bytes) -> float:
    """Anteil der Pixel, deren Grauwert sich deutlich geändert hat (0…1)."""
    if not previous or not current or len(previous) != len(current):
        return 0.0
    changed = 0
    for before, after in zip(previous, current):
        if abs(before - after) > PIXEL_DELTA:
            changed += 1
    return changed / len(current)


def _gray_image(jpeg: bytes) -> bytes | None:
    if not PIL_AVAILABLE or not jpeg:
        return None
    try:
        with Image.open(io.BytesIO(jpeg)) as image:
            return image.convert("L").resize(ANALYSE_SIZE).tobytes()
    except Exception:  # noqa: BLE001 - kaputter Frame -> ignorieren
        return None


class MotionDetector:
    """Vergleicht aufeinanderfolgende Frames einer Kamera und meldet Bewegung."""

    def __init__(self, *, sensitivity: int | float = 50, cooldown: float = 10.0,
                 on_motion: Callable[[bytes, dict[str, Any]], None] | None = None):
        self.threshold = sensitivity_threshold(sensitivity)
        self.cooldown = max(0.0, float(cooldown))
        self.on_motion = on_motion
        self._previous: bytes | None = None
        self._last_motion: float | None = None
        self._last_score: float | None = None
        self._events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
        self._lock = threading.Lock()

    def analyse(self, jpeg: bytes) -> dict[str, Any] | None:
        """Frame füttern; gibt bei Bewegung ein Ereignis zurück, sonst ``None``."""
        gray = _gray_image(jpeg)
        if gray is None:
            return None
        with self._lock:
            previous, self._previous = self._previous, gray
            if previous is None:
                return None
            score = frame_score(previous, gray)
            self._last_score = round(score, 4)
            now = time.time()
            cooling = self._last_motion is not None and now - self._last_motion < self.cooldown
            if score < self.threshold or cooling:
                return None
            self._last_motion = now
            event = {"ts": now, "score": round(score, 4)}
            self._events.append(event)
        if self.on_motion is not None:
            try:
                self.on_motion(jpeg, event)
            except Exception:  # noqa: BLE001 - Snapshot-Fehler darf Analyse nicht kippen
                log.exception("motion snapshot failed")
        return event

    def status(self) -> dict[str, Any]:
        with self._lock:
            now = time.time()
            last = self._last_motion
            return {
                "enabled": True,
                "threshold": self.threshold,
                "cooldown": self.cooldown,
                "last_motion_age_s": round(now - last, 1) if last else None,
                "score": self._last_score,
                "events": len(self._events),
                "recent": list(self._events)[-5:],
            }


class MotionHub:
    """Ein :class:`MotionDetector` pro Kamera, gefüttert vom Relay."""

    def __init__(self, *, sensitivity: int | float = 50, cooldown: float = 10.0,
                 snapshot_root: str | Path | None = None, save_snapshot: bool = True,
                 max_snapshots: int = 200):
        self.sensitivity = sensitivity
        self.cooldown = cooldown
        self.snapshot_root = Path(snapshot_root) if snapshot_root else None
        self.save_snapshot = bool(save_snapshot) and self.snapshot_root is not None
        self.max_snapshots = max(1, int(max_snapshots))
        self._lock = threading.Lock()
        self._detectors: dict[str, MotionDetector] = {}

    def _detector(self, uid: str) -> MotionDetector:
        key = _canonical(uid)
        with self._lock:
            detector = self._detectors.get(key)
            if detector is None:
                detector = MotionDetector(
                    sensitivity=self.sensitivity, cooldown=self.cooldown,
                    on_motion=lambda jpeg, event, uid=key: self._save_snapshot(uid, jpeg, event),
                )
                self._detectors[key] = detector
            return detector

    def feed(self, uid: str, jpeg: bytes) -> dict[str, Any] | None:
        """Frame einer Kamera analysieren (wird vom MediaReceiver aufgerufen)."""
        event = self._detector(uid).analyse(jpeg)
        if event is not None:
            log.info("motion detected: uid=%s score=%.3f", _canonical(uid), event["score"])
        return event

    def _save_snapshot(self, uid: str, jpeg: bytes, event: dict[str, Any]) -> None:
        if not self.save_snapshot:
            return
        folder = self.snapshot_root / _safe_uid(uid) / "motion"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(event["ts"]))
            path = folder / f"{stamp}.jpg"
            counter = 1
            while path.exists():
                path = folder / f"{stamp}-{counter}.jpg"
                counter += 1
            path.write_bytes(jpeg)
            files = sorted(folder.glob("*.jpg"), key=lambda item: item.name)
            for old in files[:-self.max_snapshots]:
                old.unlink(missing_ok=True)
        except OSError:
            log.exception("motion snapshot write failed")

    def status(self, uid: str | None = None) -> dict[str, Any]:
        with self._lock:
            detectors = dict(self._detectors)
        if uid is not None:
            key = _canonical(uid)
            detector = detectors.get(key)
            return {"enabled": True, **(detector.status() if detector else
                    {"threshold": sensitivity_threshold(self.sensitivity),
                     "cooldown": self.cooldown, "events": 0, "recent": [],
                     "last_motion_age_s": None, "score": None})}
        cameras = {key: detector.status() for key, detector in detectors.items()}
        return {"enabled": True, "sensitivity": self.sensitivity,
                "threshold": sensitivity_threshold(self.sensitivity),
                "cooldown": self.cooldown, "cameras": cameras,
                "snapshot_dir": str(self.snapshot_root) if self.save_snapshot else None}

    def events(self, uid: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            detectors = dict(self._detectors)
        if uid is not None:
            detector = detectors.get(_canonical(uid))
            events = list(detector._events) if detector else []  # noqa: SLF001
            return [dict(event, uid=_canonical(uid)) for event in events[-max(1, limit):]]
        merged = []
        for key, detector in detectors.items():
            merged.extend(dict(event, uid=key) for event in detector._events)  # noqa: SLF001
        merged.sort(key=lambda event: event.get("ts") or 0)
        return merged[-max(1, limit):]


def _canonical(value: Any) -> str:
    text = str(value or "").strip()
    if text.upper().startswith("ZIOTA_"):
        text = text[len("ZIOTA_"):]
    return text or "unknown"


def _safe_uid(value: Any) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in _canonical(value))
