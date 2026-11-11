"""Lokaler Relay-/Empfänger-Server für Z-IOT-Kameras (mit HTTP-Vorschau).

Kombiniert die drei serverseitigen Teile, die eine Kamera im Heimnetz braucht,
ohne Hersteller-Cloud:

* **Signalisierung** (TCP, Default 8882) — Login `0x1` → `0x8000`, Zeit,
  Ready, Media-Ziel `0x9003`, Keepalive
* **STUN-Responder** (UDP, Default 13478) — RFC 5389 Binding-Response
* **RTP/JPEG-Media** (UDP, Default 10000) — Frames + PCMU-Audio

Zusätzlich gibt es eine kleine HTTP-Vorschau (Default ``127.0.0.1:8099``):

* ``GET /status``        — JSON-Status
* ``GET /snapshot.jpg``  — letztes JPEG
* ``GET /stream.mjpg``   — MJPEG-Livestream (multipart/x-mixed-replace)

Der Server lässt sich direkt starten ...

    python3 relay.py --public-ip 192.168.0.4

... oder als systemd-**User**-Dienst installieren (empfohlen, startet beim Login
und überlebt Hermes-Neustarts):

    python3 -m iwfcam4hermes.relay --install --public-ip 192.168.0.4

bzw. über die Hermes-Tools ``relay_install`` / ``relay_start`` / ``relay_stop``
und ``hermes cameras relay-install``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

log = logging.getLogger("iwfcam4hermes.relay")

UNIT_NAME = "iwfcam4hermes-relay.service"
PLUGIN_ROOT = Path(__file__).resolve().parent
RELAY_SCRIPT = PLUGIN_ROOT / "relay.py"

DEFAULT_SIGNALING_PORT = 8882
DEFAULT_MEDIA_PORT = 10000
DEFAULT_STUN_PORT = 13478
DEFAULT_HTTP_PORT = 8099
DEFAULT_HTTP_HOST = "127.0.0.1"


def _load_receiver():
    """ZiotReceiverServer + Standard-DHT laden (Paket- oder Flat-Import)."""
    try:
        from .ziot_receiver import ZiotReceiverServer
        from .rtp_receiver import default_dht
    except ImportError:  # direkt als Skript gestartet
        from ziot_receiver import ZiotReceiverServer
        from rtp_receiver import default_dht
    return ZiotReceiverServer, default_dht


# --------------------------------------------------------------------------- #
# HTTP-Vorschau
# --------------------------------------------------------------------------- #


def _media_stats(media: Any) -> dict[str, Any]:
    try:
        return media.stats() if media is not None else {}
    except Exception:  # pragma: no cover - Statistik ist optional
        return {}


class _PreviewHandler(BaseHTTPRequestHandler):
    server_version = "iwfcam4hermes-relay"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:  # leise
        log.debug("http: " + fmt, *args)

    def _send(self, code: int, content_type: str, body: bytes, extra: tuple[tuple[str, str], ...] = ()) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in extra:
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        media = getattr(self.server, "media", None)
        if path in ("/", "/status"):
            self._send(200, "application/json; charset=utf-8", json.dumps(
                {"ok": True, "relay": "iwfcam4hermes", "media": _media_stats(media)},
                ensure_ascii=False).encode("utf-8"))
            return
        if path in ("/snapshot", "/snapshot.jpg"):
            jpeg = None
            try:
                jpeg = media.latest_jpeg() if media is not None else None
            except Exception:  # pragma: no cover
                jpeg = None
            if not jpeg:
                self._send(503, "text/plain; charset=utf-8",
                           b"no frame yet (camera not connected?)")
                return
            self._send(200, "image/jpeg", jpeg)
            return
        if path in ("/stream", "/stream.mjpg", "/video"):
            self._stream(media)
            return
        self._send(404, "text/plain; charset=utf-8", b"not found")

    def _stream(self, media: Any) -> None:
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
                    self.wfile.write(
                        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(jpeg)).encode("ascii") + b"\r\n\r\n" + jpeg + b"\r\n"
                    )
                    self.wfile.flush()
                time.sleep(0.2)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


class PreviewHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer, das die MediaReceiver-Instanz an den Handler reicht."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], media: Any) -> None:
        self.media = media
        super().__init__(address, _PreviewHandler)


# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #


class RelayServer:
    """Signalisierung + STUN + RTP/JPEG + HTTP-Vorschau in einem Prozess."""

    def __init__(self, public_ip: str, *,
                 signaling_port: int = DEFAULT_SIGNALING_PORT,
                 media_port: int = DEFAULT_MEDIA_PORT,
                 stun_port: int = DEFAULT_STUN_PORT,
                 http_host: str = DEFAULT_HTTP_HOST,
                 http_port: int = DEFAULT_HTTP_PORT,
                 snapshot_dir: str | None = None,
                 dht: bytes = b""):
        self._receiver_cls, self._default_dht = _load_receiver()
        self.public_ip = public_ip
        self.signaling_port = int(signaling_port)
        self.media_port = int(media_port)
        self.stun_port = int(stun_port)
        self.http_host = http_host
        self.http_port = int(http_port)
        self.snapshot_dir = snapshot_dir
        self.dht = dht
        self.receiver: Any = None
        self.http: PreviewHTTPServer | None = None
        self._http_thread: threading.Thread | None = None

    def start(self) -> dict[str, Any]:
        self.receiver = self._receiver_cls(
            host="0.0.0.0",
            public_ip=self.public_ip,
            signaling_port=self.signaling_port,
            media_port=self.media_port,
            stun_port=self.stun_port,
            dht=self.dht or self._default_dht(),
            snapshot_dir=self.snapshot_dir,
            on_login=lambda uid, fw: log.info("camera login: uid=%s firmware=%s", uid, fw),
        )
        info = self.receiver.start()
        self.signaling_port = info["signaling_port"]
        self.media_port = info["media_port"]
        self.stun_port = info["stun_port"]
        self.http = PreviewHTTPServer((self.http_host, self.http_port), self.receiver.media)
        self.http_port = self.http.server_address[1]
        self._http_thread = threading.Thread(
            target=self.http.serve_forever, name="iwfcam-http", daemon=True)
        self._http_thread.start()
        log.info("relay up: signaling=%d media=%d stun=%d http=%s:%d public_ip=%s",
                 self.signaling_port, self.media_port, self.stun_port,
                 self.http_host, self.http_port, self.public_ip)
        return self.status()

    def status(self) -> dict[str, Any]:
        running = self.receiver is not None
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
            "stream_url": base + "/stream.mjpg",
            "snapshot_url": base + "/snapshot.jpg",
            "media": _media_stats(self.receiver.media) if running else {},
        }

    def stop(self) -> None:
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


def _int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def settings_from(mapping: dict[str, Any] | None = None) -> dict[str, Any]:
    """Relay-Einstellungen aus Plugin-Settings/Argumenten ableiten."""
    data = mapping or {}
    public_ip = str(data.get("relay_public_ip") or data.get("public_ip") or "").strip()
    return {
        "public_ip": public_ip,
        "signaling_port": _int(data.get("signaling_port"), DEFAULT_SIGNALING_PORT),
        "media_port": _int(data.get("media_port"), DEFAULT_MEDIA_PORT),
        "stun_port": _int(data.get("stun_port"), DEFAULT_STUN_PORT),
        "http_port": _int(data.get("relay_http_port"), DEFAULT_HTTP_PORT),
        "http_host": str(data.get("relay_http_host") or DEFAULT_HTTP_HOST).strip() or DEFAULT_HTTP_HOST,
    }


def _http_get(host: str, port: int, path: str, timeout: float = 1.5) -> bytes | None:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None


def probe_http(host: str, port: int, timeout: float = 1.5) -> dict[str, Any] | None:
    """``/status`` eines laufenden Relays lesen (None, wenn nicht erreichbar)."""
    raw = _http_get(host, port, "/status", timeout=timeout)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def snapshot_bytes(host: str, port: int, timeout: float = 2.0) -> bytes | None:
    """Letztes JPEG vom laufenden Relay holen (None, wenn keins/kein Relay)."""
    return _http_get(host, port, "/snapshot.jpg", timeout=timeout)


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
    """Pfad/Argument für eine systemd-Unit quoten (nur wenn nötig)."""
    if not any(ch in value for ch in ' \t"\\'):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_unit(*, python: str, plugin_root: str | Path, public_ip: str,
                signaling_port: int = DEFAULT_SIGNALING_PORT,
                media_port: int = DEFAULT_MEDIA_PORT,
                stun_port: int = DEFAULT_STUN_PORT,
                http_port: int = DEFAULT_HTTP_PORT,
                http_host: str = DEFAULT_HTTP_HOST,
                snapshot_dir: str | None = None) -> str:
    """systemd-Unit-Datei als Text (pure Funktion, testbar)."""
    python = str(python)
    script = Path(plugin_root) / "relay.py"
    args = [
        _unit_quote(python), _unit_quote(str(script)),
        "--public-ip", _unit_quote(public_ip),
        "--signaling-port", str(signaling_port),
        "--media-port", str(media_port),
        "--stun-port", str(stun_port),
        "--http-host", _unit_quote(http_host),
        "--http-port", str(http_port),
    ]
    if snapshot_dir:
        args += ["--snapshots", _unit_quote(str(snapshot_dir))]
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
    """Vollständiger Relay-Status: Dienst + konfigurierte Ports + laufende Stats."""
    cfg = settings_from(settings)
    service = service_status()
    stats = probe_http(cfg["http_host"], cfg["http_port"])
    http_base = f"http://{cfg['http_host']}:{cfg['http_port']}"
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
        },
        "running": stats is not None,
        "http_url": http_base + "/",
        "stream_url": http_base + "/stream.mjpg",
        "snapshot_url": http_base + "/snapshot.jpg",
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
    unit = render_unit(
        python=sys.executable, plugin_root=PLUGIN_ROOT, public_ip=ip,
        signaling_port=cfg["signaling_port"], media_port=cfg["media_port"],
        stun_port=cfg["stun_port"], http_port=cfg["http_port"], http_host=cfg["http_host"],
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
        "ok": True, "unit": UNIT_NAME, "unit_path": str(path),
        "public_ip": ip, **{k: cfg[k] for k in ("signaling_port", "media_port", "stun_port",
                                               "http_port", "http_host")},
    }
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
    """Dienst stoppen/deaktivieren und Unit-Datei entfernen."""
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
    parser.add_argument("--media-port", type=int, default=DEFAULT_MEDIA_PORT)
    parser.add_argument("--stun-port", type=int, default=DEFAULT_STUN_PORT)
    parser.add_argument("--http-host", default=DEFAULT_HTTP_HOST)
    parser.add_argument("--http-port", type=int, default=DEFAULT_HTTP_PORT)
    parser.add_argument("--snapshots", default=None, help="Verzeichnis für automatische Snapshots")
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
        snapshot_dir=args.snapshots, dht=dht,
    )
    try:
        info = server.start()
    except Exception as exc:  # noqa: BLE001 - klare Fehlermeldung statt Traceback
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
            log.info("stats: %s", json.dumps(_media_stats(server.receiver.media), ensure_ascii=False))
    finally:
        server.stop()
        log.info("relay stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
