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
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
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
#: Pixel gelten als „geändert", wenn sich der Grauwert um mehr als das ändert
#: (klein genug für Personen/Bewegung, groß genug gegen Sensorrauschen).
PIXEL_DELTA = 12
#: Maximale Anzahl gehaltener Ereignisse pro Kamera.
MAX_EVENTS = 50


def sensitivity_threshold(sensitivity: int | float) -> float:
    """Sensitivität (1–100) → Anteil geänderter Pixel, ab dem Bewegung gilt.

    1 → unempfindlich (6 % geänderte Pixel), 50 → 3,3 %, 100 → 0,5 %.
    Personen/Bewegung im Bild liegen typischerweise deutlich über 3 %.
    """
    try:
        value = max(1.0, min(100.0, float(sensitivity)))
    except (TypeError, ValueError):
        value = 50.0
    return round(0.06 - 0.055 * (value - 1.0) / 99.0, 4)


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


WEBHOOK_TYPES = ("generic", "slack", "discord", "ntfy", "telegram")


def infer_webhook_type(url: str) -> str:
    """Webhook-Typ aus der URL ableiten (falls nicht explizit angegeben)."""
    lowered = str(url or "").lower()
    if "api.telegram.org" in lowered:
        return "telegram"
    if "discord.com" in lowered or "discordapp.com" in lowered:
        return "discord"
    if "hooks.slack.com" in lowered:
        return "slack"
    if "ntfy.sh" in lowered:
        return "ntfy"
    return "generic"


def parse_webhook_specs(value: Any) -> list[dict[str, str]]:
    """Webhook-Ziele aus Konfigurationswert parsen.

    Akzeptiert:

    * eine einzelne URL (rückwärtskompatibel),
    * mehrzeiligen Text, eine Zeile pro Ziel: ``typ|url`` oder nur ``url``
      (Typ wird aus der URL erraten),
    * eine JSON-Liste von URLs,
    * bereits geparste Listen von Strings.

    Telegram-Ziele können ``?chat_id=…`` in der URL tragen; die Chat-ID wird
    herausgezogen und im Body verwendet.
    """
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        raw = [str(item) for item in value]
    else:
        text = str(value).strip()
        if not text:
            return []
        raw = []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                raw = [str(item) for item in parsed] if isinstance(parsed, list) else []
            except ValueError:
                raw = []
        if not raw:
            raw = text.splitlines()

    entries: list[dict[str, str]] = []
    for line in raw:
        line = str(line).strip()
        if not line or line.startswith("#"):
            continue
        kind = ""
        url = line
        if "|" in line:
            head, _, tail = line.partition("|")
            head = head.strip().lower()
            tail = tail.strip()
            if head in WEBHOOK_TYPES:
                kind, url = head, tail
        if not url.lower().startswith(("http://", "https://")):
            continue
        if not kind:
            kind = infer_webhook_type(url)
        chat_id = ""
        if kind == "telegram":
            parts = urlsplit(url)
            query = dict(parse_qsl(parts.query))
            chat_id = str(query.pop("chat_id", "") or "")
            url = urlunsplit((parts.scheme, parts.netloc, parts.path,
                              urlencode(query), parts.fragment))
        entries.append({"type": kind, "url": url, "chat_id": chat_id})
    return entries


def _message_for_event(event: dict[str, Any]) -> str:
    shown = event.get("ts") or time.time()
    return (f"Bewegung erkannt: Kamera {event.get('uid') or '?'} "
            f"(Score {float(event.get('score') or 0):.3f}) um "
            f"{time.strftime('%H:%M:%S', time.localtime(shown))}")


def webhook_request(entry: dict[str, str], event: dict[str, Any]) -> tuple[str, dict[str, str], bytes]:
    """(url, headers, body) für einen Webhook-Typ bauen."""
    kind = entry.get("type") or "generic"
    message = _message_for_event(event)
    payload = dict(event)
    payload["event"] = event.get("event") or "motion"
    payload["text"] = message
    payload["content"] = message
    shown = event.get("ts") or time.time()
    payload["ts_iso"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(shown))

    if kind == "slack":
        return entry["url"], {"Content-Type": "application/json",
                              "User-Agent": "iwfcam4hermes-motion"}, \
            json.dumps({"text": message}, ensure_ascii=False).encode("utf-8")
    if kind == "discord":
        return entry["url"], {"Content-Type": "application/json",
                              "User-Agent": "iwfcam4hermes-motion"}, \
            json.dumps({"content": message}, ensure_ascii=False).encode("utf-8")
    if kind == "ntfy":
        return entry["url"], {"Content-Type": "text/plain; charset=utf-8",
                              "Title": "Kamera-Bewegung",
                              "Tags": "camera,motion",
                              "User-Agent": "iwfcam4hermes-motion"}, \
            message.encode("utf-8")
    if kind == "telegram":
        body = {"chat_id": entry.get("chat_id") or "", "text": message}
        return entry["url"], {"Content-Type": "application/json",
                              "User-Agent": "iwfcam4hermes-motion"}, \
            json.dumps(body, ensure_ascii=False).encode("utf-8")
    return entry["url"], {"Content-Type": "application/json",
                          "User-Agent": "iwfcam4hermes-motion"}, \
        json.dumps(payload, ensure_ascii=False).encode("utf-8")


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
                 max_snapshots: int = 200, webhook: str | None = None,
                 webhooks: str | list[str] | None = None,
                 webhook_timeout: float = 5.0):
        self.sensitivity = sensitivity
        self.cooldown = cooldown
        self.snapshot_root = Path(snapshot_root) if snapshot_root else None
        self.save_snapshot = bool(save_snapshot) and self.snapshot_root is not None
        self.max_snapshots = max(1, int(max_snapshots))
        specs = parse_webhook_specs(webhook) + parse_webhook_specs(webhooks)
        self.webhooks: list[dict[str, str]] = specs
        self.webhook_timeout = max(1.0, float(webhook_timeout or 5.0))
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
            event["uid"] = _canonical(uid)
            log.info("motion detected: uid=%s score=%.3f", _canonical(uid), event["score"])
            if self.webhooks:
                threading.Thread(target=self._notify, args=(event,),
                                 name="iwfcam-motion-webhook", daemon=True).start()
        return event

    def _notify(self, event: dict[str, Any]) -> None:
        """Bewegungsereignis parallel an alle konfigurierten Webhooks schicken."""
        for entry in list(self.webhooks):
            threading.Thread(target=self._post_webhook, args=(entry, event),
                             name=f"iwfcam-motion-webhook-{entry.get('type')}",
                             daemon=True).start()

    def _post_webhook(self, entry: dict[str, str], event: dict[str, Any]) -> None:
        try:
            url, headers, body = webhook_request(entry, event)
            request = urllib.request.Request(url, data=body, method="POST", headers=headers)
            with urllib.request.urlopen(request, timeout=self.webhook_timeout) as response:
                response.read(256)
            log.info("motion webhook ok (%s): uid=%s", entry.get("type"), event.get("uid"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log.warning("motion webhook failed (%s): %s", entry.get("type"), exc)

    def send_test(self) -> dict[str, Any]:
        """Test-Bewegungsereignis an alle konfigurierten Webhooks senden."""
        event = {"uid": "test", "score": 0.0, "ts": time.time(), "event": "motion",
                 "test": True}
        self._notify(event)
        return {"ok": True, "webhooks": len(self.webhooks),
                "targets": [entry.get("type") for entry in self.webhooks]}

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
            event["snapshot"] = str(path)
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
        webhook_info = [{"type": entry.get("type"),
                         "host": urlsplit(entry.get("url") or "").netloc}
                        for entry in self.webhooks]
        return {"enabled": True, "sensitivity": self.sensitivity,
                "threshold": sensitivity_threshold(self.sensitivity),
                "cooldown": self.cooldown, "cameras": cameras,
                "webhooks": webhook_info, "webhook_count": len(webhook_info),
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
