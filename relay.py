"""Lokaler Relay-/Empfänger-Server für Z-IOT-Kameras (Multi-Kamera + Qualität).

Bündelt die serverseitigen Teile, die Kameras im Heimnetz brauchen — ohne
Hersteller-Cloud:

* **Signalisierung** (TCP, Default 8882) — pro Login wird der Kamera ein
  **eigener UDP-Media-Port** zugewiesen (mehrere Kameras parallel)
* **STUN-Responder** (UDP, Default 13478)
* **RTP/JPEG-Media** — ein ``MediaReceiver`` pro Kamera (PT26 JPEG + PCMU)
* **HTTP-Vorschau** (Default ``127.0.0.1:8099``) mit einstellbarer Qualität:

  * ``GET /status``                — JSON (Kameras, Ports, Frames)
  * ``GET /cameras``               — Liste der aktiven Kameras
  * ``GET /snapshot.jpg?uid=&quality=``
  * ``GET /stream.mjpg?uid=&quality=&fps=`` (MJPEG)

Qualitätsstufen: ``original``, ``high``, ``medium`` (Default), ``low`` —
serverseitiges Skalieren/Re-Encoding (Pillow). Die Kamera-interne
Stream-Qualität ist bei dieser Firmware nicht per Protokoll einstellbar.

Der Server läuft im Vordergrund (``python3 relay.py --public-ip …``) oder als
systemd-User-Dienst (``--install``, empfohlen).
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

try:  # Paket-Import
    from .preview import (DEFAULT_FPS, DEFAULT_QUALITY, QUALITY_NAMES,
                          normalize_fps, normalize_quality, pil_available, reencode)
except ImportError:  # direkt als Skript (systemd)
    from preview import (DEFAULT_FPS, DEFAULT_QUALITY, QUALITY_NAMES,
                         normalize_fps, normalize_quality, pil_available, reencode)

log = logging.getLogger("iwfcam4hermes.relay")

UNIT_NAME = "iwfcam4hermes-relay.service"
PLUGIN_ROOT = Path(__file__).resolve().parent
RELAY_SCRIPT = PLUGIN_ROOT / "relay.py"

DEFAULT_SIGNALING_PORT = 8882
DEFAULT_MEDIA_PORT = 10000
DEFAULT_STUN_PORT = 13478
DEFAULT_HTTP_PORT = 8099
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_MAX_CAMERAS = 16
DEFAULT_SNAPSHOT_INTERVAL = 60.0
DEFAULT_SNAPSHOT_RETAIN = 200


def _load_receiver():
    try:
        from .ziot_receiver import ZiotReceiverServer
        from .rtp_receiver import default_dht
    except ImportError:
        from ziot_receiver import ZiotReceiverServer
        from rtp_receiver import default_dht
    return ZiotReceiverServer, default_dht


def _safe_uid(uid: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in (uid or "unknown"))


def _media_stats(media: Any) -> dict[str, Any]:
    try:
        return media.stats() if media is not None else {}
    except Exception:  # pragma: no cover
        return {}


# --------------------------------------------------------------------------- #
# HTTP-Vorschau
# --------------------------------------------------------------------------- #


class _PreviewHandler(BaseHTTPRequestHandler):
    server_version = "iwfcam4hermes-relay"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        log.debug("http: " + fmt, *args)

    # -- Helfer ------------------------------------------------------------
    def _query(self) -> dict[str, str]:
        params = parse_qs(urlsplit(self.path).query)
        return {key: values[-1] for key, values in params.items() if values}

    def _receiver(self):
        return getattr(self.server, "receiver", None)

    def _camera(self, query: dict[str, str]):
        receiver = self._receiver()
        if receiver is None:
            return None, "", None
        uid = str(query.get("uid") or "").strip()
        if uid:
            return receiver, uid, receiver.media_for(uid)
        cameras = receiver.cameras()
        if not cameras:
            return receiver, "", None
        first = cameras[0]["uid"]
        return receiver, first, receiver.media_for(first)

    def _send(self, code: int, content_type: str, body: bytes,
              extra: tuple[tuple[str, str], ...] = ()) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in extra:
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, payload: dict[str, Any], code: int = 200) -> None:
        self._send(code, "application/json; charset=utf-8",
                   json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    # -- Routen ------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = urlsplit(self.path).path.rstrip("/") or "/"
        query = self._query()
        receiver = self._receiver()

        if path in ("/", "/status", "/cameras"):
            cameras = receiver.cameras() if receiver is not None else []
            payload: dict[str, Any] = {
                "ok": True,
                "relay": "iwfcam4hermes",
                "quality": normalize_quality(query.get("quality")
                                             or getattr(self.server, "default_quality", DEFAULT_QUALITY)),
                "fps": normalize_fps(query.get("fps")
                                     or getattr(self.server, "default_fps", DEFAULT_FPS)),
                "cameras": cameras,
                "totals": receiver.media_hub.totals() if receiver is not None else
                          {"cameras": 0, "frames": 0, "audio_packets": 0},
                "pil": pil_available(),
                "quality_presets": list(QUALITY_NAMES),
            }
            self._json(payload)
            return

        if path in ("/snapshot", "/snapshot.jpg"):
            _receiver, uid, media = self._camera(query)
            jpeg = None
            try:
                jpeg = media.latest_jpeg() if media is not None else None
            except Exception:  # pragma: no cover
                jpeg = None
            if not jpeg:
                self._send(503, "text/plain; charset=utf-8",
                           f"no frame yet for {uid or 'any camera'}".encode())
                return
            quality = normalize_quality(query.get("quality")
                                        or getattr(self.server, "default_quality", DEFAULT_QUALITY))
            self._send(200, "image/jpeg", reencode(jpeg, quality),
                       extra=(("X-Camera-Uid", uid), ("X-Quality", quality)))
            return

        if path in ("/stream", "/stream.mjpg", "/video"):
            _receiver, uid, media = self._camera(query)
            self._stream(media, query)
            return

        if path == "/snapshots":
            store = getattr(self.server, "snapshot_store", None)
            payload = {"ok": True, **(store.stats() if store is not None else {"enabled": False})}
            self._json(payload)
            return

        self._send(404, "text/plain; charset=utf-8", b"not found")

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        path = urlsplit(self.path).path.rstrip("/") or "/"
        query = self._query()
        if path == "/snapshots/save":
            store = getattr(self.server, "snapshot_store", None)
            if store is None:
                self._json({"ok": False, "error": "Snapshot-Ablage nicht konfiguriert"}, 400)
                return
            saved = store.save_now(query.get("uid") or None)
            self._json({"ok": True, "saved": saved, "stats": store.stats()})
            return
        self._send(404, "text/plain; charset=utf-8", b"not found")

    def _stream(self, media: Any, query: dict[str, str]) -> None:
        quality = normalize_quality(query.get("quality")
                                    or getattr(self.server, "default_quality", DEFAULT_QUALITY))
        fps = normalize_fps(query.get("fps") or getattr(self.server, "default_fps", DEFAULT_FPS))
        interval = 1.0 / fps
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            while True:
                jpeg = None
                try:
                    jpeg = media.latest_jpeg() if media is not None else None
                except Exception:  # pragma: no cover
                    jpeg = None
                if jpeg:
                    frame = reencode(jpeg, quality)
                    self.wfile.write(
                        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(frame)).encode("ascii") + b"\r\n\r\n" + frame + b"\r\n"
                    )
                    self.wfile.flush()
                time.sleep(interval)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


class PreviewHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer mit Zugriff auf Receiver + Qualitäts-Defaults."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], receiver: Any, *,
                 default_quality: str = DEFAULT_QUALITY,
                 default_fps: int = DEFAULT_FPS) -> None:
        self.receiver = receiver
        self.default_quality = normalize_quality(default_quality)
        self.default_fps = normalize_fps(default_fps)
        self.snapshot_store: SnapshotStore | None = None
        super().__init__(address, _PreviewHandler)



class SnapshotStore:
    """Ringpuffer: speichert regelmäßig das letzte JPEG jeder Kamera.

    Pro Kamera liegt ein Unterordner mit ``<YYYYmmdd-HHMMSS>.jpg``; pro Kamera
    werden höchstens ``retain`` Bilder behalten (ältere werden gelöscht). Das
    Intervall ist konfigurierbar (``relay_snapshot_interval``); ein Speichern
    auf Abruf geht über :meth:`save_now`.
    """

    def __init__(self, root: str | Path, interval: float = DEFAULT_SNAPSHOT_INTERVAL,
                 retain: int = DEFAULT_SNAPSHOT_RETAIN):
        self.root = Path(root)
        self.interval = max(1.0, float(interval or DEFAULT_SNAPSHOT_INTERVAL))
        self.retain = max(1, int(retain or DEFAULT_SNAPSHOT_RETAIN))
        self.receiver: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._saved = 0
        self._last_saved_at: float | None = None

    def start(self, receiver: Any) -> None:
        self.receiver = receiver
        self.root.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._loop, name="iwfcam-snapshots", daemon=True)
        self._thread.start()
        log.info("snapshot store: dir=%s interval=%.0fs retain=%d",
                 self.root, self.interval, self.retain)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.save_now()
            except Exception:  # noqa: BLE001 - Hintergrundspeichern darf nicht sterben
                log.exception("snapshot save failed")

    def _cameras(self) -> list[dict[str, Any]]:
        if self.receiver is None:
            return []
        try:
            return self.receiver.cameras()
        except Exception:  # noqa: BLE001
            return []

    def save_now(self, uid: str | None = None) -> list[str]:
        """Aktuelles JPEG jeder (oder einer) Kamera sofort ablegen."""
        saved: list[str] = []
        for camera in self._cameras():
            if uid and camera.get("uid") != uid:
                continue
            media = None
            try:
                media = self.receiver.media_for(camera["uid"])
            except Exception:  # noqa: BLE001
                media = None
            jpeg = media.latest_jpeg() if media is not None else None
            if not jpeg:
                continue
            path = self._write(camera["uid"], jpeg)
            if path is not None:
                saved.append(str(path))
        if saved:
            with self._lock:
                self._saved += len(saved)
                self._last_saved_at = time.time()
        return saved

    def _write(self, uid: str, jpeg: bytes) -> Path | None:
        folder = self.root / _safe_uid(uid)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = folder / f"{stamp}.jpg"
        counter = 1
        while path.exists():
            path = folder / f"{stamp}-{counter}.jpg"
            counter += 1
        try:
            path.write_bytes(jpeg)
        except OSError:
            log.exception("snapshot write failed: %s", path)
            return None
        self._prune(folder)
        return path

    def _prune(self, folder: Path) -> None:
        try:
            files = sorted(folder.glob("*.jpg"), key=lambda f: f.name)
        except OSError:
            return
        for old in files[:-self.retain]:
            try:
                old.unlink()
            except OSError:
                pass

    def stats(self) -> dict[str, Any]:
        cameras: dict[str, dict[str, Any]] = {}
        total = 0
        if self.root.is_dir():
            for folder in sorted(self.root.iterdir()):
                if not folder.is_dir():
                    continue
                files = sorted(folder.glob("*.jpg"), key=lambda f: f.name)
                total += len(files)
                latest = files[-1] if files else None
                cameras[folder.name] = {
                    "count": len(files),
                    "latest": latest.name if latest else None,
                    "latest_at": (datetime.datetime.fromtimestamp(latest.stat().st_mtime).isoformat(timespec="seconds")
                                  if latest and latest.exists() else None),
                }
        with self._lock:
            saved = self._saved
            last = self._last_saved_at
        return {
            "dir": str(self.root),
            "interval": self.interval,
            "retain": self.retain,
            "total": total,
            "saved": saved,
            "last_save_age_s": round(time.time() - last, 1) if last else None,
            "cameras": cameras,
        }

# --------------------------------------------------------------------------- #
# Relay-Server (Signalisierung + STUN + Multi-Media + HTTP)
# --------------------------------------------------------------------------- #


class RelayServer:
    """Mehrere Kameras gleichzeitig + HTTP-Vorschau mit Qualitätsstufe."""

    def __init__(self, public_ip: str, *,
                 signaling_port: int = DEFAULT_SIGNALING_PORT,
                 media_port: int = DEFAULT_MEDIA_PORT,
                 stun_port: int = DEFAULT_STUN_PORT,
                 http_host: str = DEFAULT_HTTP_HOST,
                 http_port: int = DEFAULT_HTTP_PORT,
                 dht: bytes = b"",
                 default_quality: str = DEFAULT_QUALITY,
                 default_fps: int = DEFAULT_FPS,
                 max_cameras: int = DEFAULT_MAX_CAMERAS,
                 snapshot_dir: str | None = None,
                 snapshot_interval: float = DEFAULT_SNAPSHOT_INTERVAL,
                 snapshot_retain: int = DEFAULT_SNAPSHOT_RETAIN):
        self._receiver_cls, self._default_dht = _load_receiver()
        self.public_ip = public_ip
        self.signaling_port = int(signaling_port)
        self.media_port = int(media_port)
        self.stun_port = int(stun_port)
        self.http_host = http_host
        self.http_port = int(http_port)
        self.snapshot_dir = snapshot_dir
        self.dht = dht
        self.default_quality = normalize_quality(default_quality)
        self.default_fps = normalize_fps(default_fps)
        self.max_cameras = max(1, int(max_cameras))
        self.snapshot_dir = snapshot_dir or None
        self.snapshot_interval = float(snapshot_interval or DEFAULT_SNAPSHOT_INTERVAL)
        self.snapshot_retain = max(1, int(snapshot_retain or DEFAULT_SNAPSHOT_RETAIN))
        self.snapshot_store: SnapshotStore | None = None
        self.receiver: Any = None
        self.http: PreviewHTTPServer | None = None
        self._http_thread: threading.Thread | None = None

    def start(self) -> dict[str, Any]:
        self.receiver = self._receiver_cls(
            host="0.0.0.0",
            public_ip=self.public_ip,
            signaling_port=self.signaling_port,
            media_port=0,  # pro Kamera vom MediaHub vergeben
            stun_port=self.stun_port,
            dht=self.dht or self._default_dht(),
            snapshot_dir=self.snapshot_dir,
            on_login=lambda uid, fw: log.info("camera login: uid=%s firmware=%s", uid, fw),
        )
        self.receiver.media_hub.max_cameras = self.max_cameras
        info = self.receiver.start()
        self.signaling_port = info["signaling_port"]
        self.stun_port = info["stun_port"]
        self.http = PreviewHTTPServer((self.http_host, self.http_port), self.receiver,
                                      default_quality=self.default_quality,
                                      default_fps=self.default_fps)
        self.http_port = self.http.server_address[1]
        if self.snapshot_dir:
            self.snapshot_store = SnapshotStore(
                self.snapshot_dir, interval=self.snapshot_interval, retain=self.snapshot_retain)
            self.http.snapshot_store = self.snapshot_store
            self.snapshot_store.start(self.receiver)
        self._http_thread = threading.Thread(
            target=self.http.serve_forever, name="iwfcam-http", daemon=True)
        self._http_thread.start()
        log.info("relay up: signaling=%d stun=%d http=%s:%d public_ip=%s "
                 "quality=%s fps=%d pil=%s",
                 self.signaling_port, self.stun_port, self.http_host, self.http_port,
                 self.public_ip, self.default_quality, self.default_fps, pil_available())
        return self.status()

    def status(self) -> dict[str, Any]:
        running = self.receiver is not None
        cameras = self.receiver.cameras() if running else []
        base = f"http://{self.http_host}:{self.http_port}"
        return {
            "ok": True,
            "running": running,
            "public_ip": self.public_ip,
            "signaling_port": self.signaling_port,
            "media_port": self.media_port,
            "stun_port": self.stun_port,
            "http_host": self.http_host,
            "http_port": self.http_port,
            "http_url": base + "/",
            "cameras_url": base + "/cameras",
            "stream_url": base + "/stream.mjpg",
            "snapshot_url": base + "/snapshot.jpg",
            "quality": self.default_quality,
            "fps": self.default_fps,
            "quality_presets": list(QUALITY_NAMES),
            "pil": pil_available(),
            "cameras": cameras,
            "media": (self.receiver.totals() if running
                      else {"cameras": 0, "frames": 0, "audio_packets": 0,
                            "streaming": 0, "paused": 0, "offline": 0}),
            "snapshots": (self.snapshot_store.stats() if self.snapshot_store is not None
                          else {"enabled": False}),
        }

    def stop(self) -> None:
        if self.snapshot_store is not None:
            try:
                self.snapshot_store.stop()
            except Exception:  # pragma: no cover
                pass
            self.snapshot_store = None
        if self.http is not None:
            try:
                self.http.shutdown()
            except Exception:  # pragma: no cover
                pass
            try:
                self.http.server_close()
            except Exception:  # pragma: no cover
                pass
            self.http = None
        if self.receiver is not None:
            try:
                self.receiver.stop()
            except Exception:  # pragma: no cover
                pass
            self.receiver = None


# --------------------------------------------------------------------------- #
# Einstellungen / HTTP-Probes
# --------------------------------------------------------------------------- #


def default_snapshot_dir() -> str:
    """Standard-Ablage für den Snapshot-Ringpuffer (Basis-Hermes-Home)."""
    try:
        from .config_store import hermes_root
    except ImportError:  # direkt als Skript
        from config_store import hermes_root
    return str(hermes_root() / "iwfcam4hermes" / "snapshots")


def _int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 0 else default


def settings_from(mapping: dict[str, Any] | None = None) -> dict[str, Any]:
    data = mapping or {}
    public_ip = str(data.get("relay_public_ip") or data.get("public_ip") or "").strip()
    return {
        "public_ip": public_ip,
        "signaling_port": _int(data.get("signaling_port"), DEFAULT_SIGNALING_PORT),
        "media_port": _int(data.get("media_port"), DEFAULT_MEDIA_PORT),
        "stun_port": _int(data.get("stun_port"), DEFAULT_STUN_PORT),
        "http_port": _int(data.get("relay_http_port"), DEFAULT_HTTP_PORT),
        "http_host": str(data.get("relay_http_host") or DEFAULT_HTTP_HOST).strip() or DEFAULT_HTTP_HOST,
        "quality": normalize_quality(data.get("relay_quality")),
        "fps": normalize_fps(data.get("relay_fps")),
        "max_cameras": _int(data.get("relay_max_cameras"), DEFAULT_MAX_CAMERAS) or DEFAULT_MAX_CAMERAS,
        "snapshot_dir": (str(data.get("snapshot_dir") or "").strip()
                         or default_snapshot_dir()),
        "snapshot_interval": _int(data.get("relay_snapshot_interval"),
                                  int(DEFAULT_SNAPSHOT_INTERVAL)) or int(DEFAULT_SNAPSHOT_INTERVAL),
        "snapshot_retain": _int(data.get("relay_snapshot_retain"),
                                DEFAULT_SNAPSHOT_RETAIN) or DEFAULT_SNAPSHOT_RETAIN,
    }


def _http_get(host: str, port: int, path: str, timeout: float = 1.5) -> bytes | None:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None


def probe_http(host: str, port: int, timeout: float = 1.5) -> dict[str, Any] | None:
    raw = _http_get(host, port, "/status", timeout=timeout)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def snapshots_status(host: str, port: int, timeout: float = 1.5) -> dict[str, Any] | None:
    """Snapshot-Ablage-Status über HTTP (None, wenn Relay nicht erreichbar)."""
    raw = _http_get(host, port, "/snapshots", timeout=timeout)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def snapshots_save(host: str, port: int, uid: str | None = None,
                   timeout: float = 3.0) -> dict[str, Any] | None:
    """Snapshot(s) sofort in die Ablage schreiben (POST /snapshots/save)."""
    import urllib.parse

    path = "/snapshots/save" + (
        "?uid=" + urllib.parse.quote(str(uid)) if uid else "")
    request = urllib.request.Request(f"http://{host}:{port}{path}", data=b"", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def snapshot_bytes(host: str, port: int, timeout: float = 2.0,
                   uid: str | None = None, quality: str | None = None) -> bytes | None:
    """Aktuelles JPEG einer Kamera über die HTTP-Vorschau holen."""
    params = []
    if uid:
        params.append("uid=" + urllib.parse.quote(str(uid)))
    if quality:
        params.append("quality=" + urllib.parse.quote(str(quality)))
    path = "/snapshot.jpg" + ("?" + "&".join(params) if params else "")
    return _http_get(host, port, path, timeout=timeout)



# --------------------------------------------------------------------------- #
# systemd-User-Dienst
# --------------------------------------------------------------------------- #


def unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / UNIT_NAME


def _systemctl(*args: str, timeout: float = 15.0) -> tuple[int, str, str]:
    try:
        result = subprocess.run(["systemctl", "--user", *args],
                                capture_output=True, text=True, timeout=timeout)
        return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "systemctl nicht gefunden (kein systemd?)"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timeout: systemctl --user {' '.join(args)}"


def _unit_quote(value: str) -> str:
    if not any(ch in value for ch in ' \t"\\'):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _python_has_pillow(python: str) -> bool:
    """Prüft, ob *python* Pillow importieren kann (ohne PYTHONPATH-Tricks)."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    try:
        probe = subprocess.run([python, "-c", "import PIL"], capture_output=True,
                               timeout=15, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def _python_with_pillow() -> str:
    """Interpreter wählen, der Pillow kann (für Qualitäts-Skalierung)."""
    import shutil

    for candidate in (sys.executable, "/usr/bin/python3", shutil.which("python3")):
        if candidate and _python_has_pillow(candidate):
            return candidate
    return sys.executable


def render_unit(*, python: str, plugin_root: str | Path, public_ip: str,
                signaling_port: int = DEFAULT_SIGNALING_PORT,
                media_port: int = DEFAULT_MEDIA_PORT,
                stun_port: int = DEFAULT_STUN_PORT,
                http_port: int = DEFAULT_HTTP_PORT,
                http_host: str = DEFAULT_HTTP_HOST,
                quality: str = DEFAULT_QUALITY,
                fps: int = DEFAULT_FPS,
                max_cameras: int = DEFAULT_MAX_CAMERAS,
                snapshot_dir: str | None = None,
                snapshot_interval: int = int(DEFAULT_SNAPSHOT_INTERVAL),
                snapshot_retain: int = DEFAULT_SNAPSHOT_RETAIN) -> str:
    """systemd-Unit-Datei als Text (pure Funktion, testbar)."""
    script = Path(plugin_root) / "relay.py"
    args = [
        _unit_quote(str(python)), _unit_quote(str(script)),
        "--public-ip", _unit_quote(public_ip),
        "--signaling-port", str(signaling_port),
        "--media-port", str(media_port),
        "--stun-port", str(stun_port),
        "--http-host", _unit_quote(http_host),
        "--http-port", str(http_port),
        "--quality", normalize_quality(quality),
        "--fps", str(normalize_fps(fps)),
        "--max-cameras", str(max(1, int(max_cameras))),
    ]
    if snapshot_dir:
        args += ["--snapshots", _unit_quote(str(snapshot_dir)),
                 "--snapshot-interval", str(max(1, int(snapshot_interval))),
                 "--snapshot-retain", str(max(1, int(snapshot_retain)))]
    return (
        "[Unit]\n"
        "Description=iwfcam4hermes local relay (signaling + STUN + RTP/JPEG + HTTP preview)\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={_unit_quote(str(Path(plugin_root)))}\n"
        "Environment=PYTHONUNBUFFERED=1\n"
        f"ExecStart={' '.join(args)}\n"
        "Restart=on-failure\n"
        "RestartSec=3\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def service_status() -> dict[str, Any]:
    path = unit_path()
    active_code, _, _ = _systemctl("is-active", UNIT_NAME)
    enabled_code, _, _ = _systemctl("is-enabled", UNIT_NAME)
    return {
        "unit": UNIT_NAME,
        "unit_path": str(path),
        "installed": path.is_file(),
        "active": active_code == 0,
        "enabled": enabled_code == 0,
    }


def status(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Vollständiger Relay-Status: Dienst, Ports, Qualität + laufende Kameras."""
    cfg = settings_from(settings)
    service = service_status()
    stats = probe_http(cfg["http_host"], cfg["http_port"])
    http_base = f"http://{cfg['http_host']}:{cfg['http_port']}"
    cameras = (stats or {}).get("cameras") or []
    pil = (stats or {}).get("pil")
    if pil is None:
        pil = pil_available()
    return {
        "ok": True,
        **service,
        "configured": {
            "public_ip": cfg["public_ip"],
            "signaling_port": cfg["signaling_port"],
            "media_port": cfg["media_port"],
            "stun_port": cfg["stun_port"],
            "http_port": cfg["http_port"],
            "http_host": cfg["http_host"],
            "quality": cfg["quality"],
            "fps": cfg["fps"],
            "max_cameras": cfg["max_cameras"],
        },
        "running": stats is not None,
        "http_url": http_base + "/",
        "cameras_url": http_base + "/cameras",
        "stream_url": http_base + "/stream.mjpg",
        "snapshot_url": http_base + "/snapshot.jpg",
        "quality_presets": list(QUALITY_NAMES),
        "pil": pil,
        "cameras": cameras,
        "snapshots": (stats or {}).get("snapshots") or {"enabled": False},
        "stats": stats,
    }


def install(settings: dict[str, Any] | None = None, *, public_ip: str | None = None,
            start: bool = True, run: bool = True) -> dict[str, Any]:
    """systemd-User-Unit schreiben und (optional) aktivieren+starten."""
    cfg = settings_from(settings)
    ip = (public_ip or cfg["public_ip"] or "").strip()
    if not ip:
        return {"ok": False, "error": "public_ip erforderlich (LAN-IPv4, unter der die Kamera "
                                     "diesen Host erreicht, z. B. 192.168.0.4)"}
    python = _python_with_pillow()
    unit = render_unit(
        python=python, plugin_root=PLUGIN_ROOT, public_ip=ip,
        signaling_port=cfg["signaling_port"], media_port=cfg["media_port"],
        stun_port=cfg["stun_port"], http_port=cfg["http_port"], http_host=cfg["http_host"],
        quality=cfg["quality"], fps=cfg["fps"], max_cameras=cfg["max_cameras"],
        snapshot_dir=cfg["snapshot_dir"] or None,
        snapshot_interval=cfg["snapshot_interval"], snapshot_retain=cfg["snapshot_retain"],
    )
    path = unit_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            try:
                path.with_suffix(path.suffix + ".bak").write_text(
                    path.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError:
                pass
        path.write_text(unit, encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"Unit-Datei nicht schreibbar: {exc}", "unit_path": str(path)}

    result: dict[str, Any] = {
        "ok": True, "unit": UNIT_NAME, "unit_path": str(path), "python": python,
        "public_ip": ip,
        **{k: cfg[k] for k in ("signaling_port", "media_port", "stun_port",
                              "http_port", "http_host", "quality", "fps", "max_cameras",
                              "snapshot_dir", "snapshot_interval", "snapshot_retain")},
        "pil": _python_has_pillow(python),
    }
    if not result["pil"]:
        result["warning"] = ("Kein Pillow im Dienst-Interpreter — Qualitätsstufen wirken "
                             "nur als 'original' (Pillow installieren oder /usr/bin/python3 nutzen).")
    if not run:
        return result

    actions: dict[str, Any] = {}
    code, out, err = _systemctl("daemon-reload")
    actions["daemon-reload"] = {"ok": code == 0, "message": out or err}
    code, out, err = _systemctl("enable", UNIT_NAME)
    actions["enable"] = {"ok": code == 0, "message": out or err}
    if start:
        code, out, err = _systemctl("restart", UNIT_NAME)
        actions["start"] = {"ok": code == 0, "message": out or err}
    result["actions"] = actions
    result["ok"] = all(item["ok"] for item in actions.values())
    if not result["ok"]:
        result["error"] = "systemctl --user ist fehlgeschlagen (siehe actions)"
    result.update(service_status())
    return result


def uninstall(*, run: bool = True) -> dict[str, Any]:
    actions: dict[str, Any] = {}
    if run:
        for action in ("stop", "disable"):
            code, out, err = _systemctl(action, UNIT_NAME)
            actions[action] = {"ok": code == 0, "message": out or err}
    path = unit_path()
    removed = False
    if path.is_file():
        try:
            path.unlink()
            removed = True
        except OSError as exc:
            return {"ok": False, "error": f"Unit-Datei nicht löschbar: {exc}",
                    "unit_path": str(path), "actions": actions}
    if run:
        _systemctl("daemon-reload")
    return {"ok": True, "removed": removed, "unit": UNIT_NAME,
            "unit_path": str(path), "actions": actions}


def start() -> dict[str, Any]:
    code, out, err = _systemctl("start", UNIT_NAME)
    return {"ok": code == 0, "action": "start", "message": out or err, **service_status()}


def stop() -> dict[str, Any]:
    code, out, err = _systemctl("stop", UNIT_NAME)
    return {"ok": code == 0, "action": "stop", "message": out or err, **service_status()}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="iwfcam4hermes-relay",
        description="Lokaler Relay-Server (Signalisierung + STUN + RTP/JPEG + HTTP-Vorschau)")
    parser.add_argument("--public-ip", default=os.environ.get("IWFCAM_PUBLIC_IP", ""),
                        help="IP, unter der die Kamera diesen Host erreicht (LAN-IPv4)")
    parser.add_argument("--signaling-port", type=int, default=DEFAULT_SIGNALING_PORT)
    parser.add_argument("--media-port", type=int, default=DEFAULT_MEDIA_PORT,
                        help="Basis (pro Kamera wird ein eigener Port vergeben)")
    parser.add_argument("--stun-port", type=int, default=DEFAULT_STUN_PORT)
    parser.add_argument("--http-host", default=DEFAULT_HTTP_HOST)
    parser.add_argument("--http-port", type=int, default=DEFAULT_HTTP_PORT)
    parser.add_argument("--quality", choices=list(QUALITY_NAMES), default=DEFAULT_QUALITY)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--max-cameras", type=int, default=DEFAULT_MAX_CAMERAS)
    parser.add_argument("--snapshots", default=None, help="Verzeichnis für automatische Snapshots")
    parser.add_argument("--snapshot-interval", type=int, default=int(DEFAULT_SNAPSHOT_INTERVAL),
                        help="Sekunden zwischen automatischen Snapshots (0=aus)")
    parser.add_argument("--snapshot-retain", type=int, default=DEFAULT_SNAPSHOT_RETAIN,
                        help="Maximale Anzahl Snapshots pro Kamera (Ringpuffer)")
    parser.add_argument("--dht", default=None, help="Referenz-JPEG für die Huffman-Tabellen")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--install", action="store_true",
                        help="systemd-User-Dienst installieren/aktualisieren (statt Vordergrund)")
    parser.add_argument("--uninstall", action="store_true", help="systemd-User-Dienst entfernen")
    parser.add_argument("--start", action="store_true", help="Dienst starten (mit --install default)")
    parser.add_argument("--stop", action="store_true", help="Dienst stoppen")
    parser.add_argument("--status", action="store_true", help="Status als JSON ausgeben")
    parser.add_argument("--no-start", action="store_true", help="bei --install nicht starten")
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = settings_from(vars(args))
    cfg["quality"] = normalize_quality(args.quality)
    cfg["fps"] = normalize_fps(args.fps)
    cfg["max_cameras"] = max(1, int(args.max_cameras))
    cfg["snapshot_dir"] = str(args.snapshots or cfg["snapshot_dir"] or "")
    cfg["snapshot_interval"] = int(args.snapshot_interval or cfg["snapshot_interval"])
    cfg["snapshot_retain"] = max(1, int(args.snapshot_retain or cfg["snapshot_retain"]))

    if args.uninstall:
        print(json.dumps(uninstall(), indent=2, ensure_ascii=False))
        return 0
    if args.status:
        print(json.dumps(status(cfg), indent=2, ensure_ascii=False))
        return 0
    if args.stop:
        print(json.dumps(stop(), indent=2, ensure_ascii=False))
        return 0
    if args.install:
        result = install(cfg, public_ip=args.public_ip, start=not args.no_start)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    dht = b""
    if args.dht:
        try:
            from rtp_receiver import load_dht_from_jpeg
        except ImportError:
            from .rtp_receiver import load_dht_from_jpeg
        dht = load_dht_from_jpeg(args.dht)
    if not args.public_ip:
        print("--public-ip fehlt (LAN-IPv4, unter der die Kamera diesen Host erreicht)",
              file=sys.stderr)
        return 2

    server = RelayServer(
        args.public_ip,
        signaling_port=cfg["signaling_port"], media_port=cfg["media_port"],
        stun_port=cfg["stun_port"], http_host=cfg["http_host"], http_port=cfg["http_port"],
        snapshot_dir=cfg["snapshot_dir"] or None, dht=dht,
        default_quality=cfg["quality"], default_fps=cfg["fps"],
        max_cameras=cfg["max_cameras"],
        snapshot_interval=cfg["snapshot_interval"], snapshot_retain=cfg["snapshot_retain"],
    )
    try:
        info = server.start()
    except Exception as exc:  # noqa: BLE001 - klare Meldung statt Traceback
        print(f"Relay-Start fehlgeschlagen: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(info, indent=2, ensure_ascii=False), flush=True)

    stop_event = threading.Event()

    def _stop(_signum: int, _frame: Any) -> None:
        stop_event.set()

    for signame in ("SIGTERM", "SIGINT"):
        signum = getattr(signal, signame, None)
        if signum is not None:
            try:
                signal.signal(signum, _stop)
            except (ValueError, OSError):  # z. B. nicht im Hauptthread
                pass

    try:
        while not stop_event.is_set():
            time.sleep(5)
            log.info("stats: %s", json.dumps(server.receiver.totals(),
                                             ensure_ascii=False))
    finally:
        server.stop()
        log.info("relay stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
