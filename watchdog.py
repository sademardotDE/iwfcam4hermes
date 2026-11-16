"""Opt-in-Watchdog: offline Kameras automatisch neu provisionieren.

Der Watchdog läuft im Relay-Dienst (oder eigenständig) und prüft periodisch, ob
eine konfigurierte Kamera *offline*/unbekannt ist. Ist ihr ``ZIOTA_…``-AP
sichtbar und sind WLAN-Zugangsdaten gemerkt, wird sie über den AP-Modus neu
provisioniert (inkl. statischem-IP-Fallback bei fehlendem DHCP). Pro Kamera
gilt ein Cooldown, damit nicht dauerhaft das Host-WLAN gewechselt wird.

Alle Abhängigkeiten werden injiziert (Kameras, Config, WLAN-Scan,
Provisionierung) — dadurch ohne Hardware/NM testbar.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

log = logging.getLogger("iwfcam4hermes.watchdog")

DEFAULT_INTERVAL = 300.0
DEFAULT_COOLDOWN = 1800.0
#: Zustände, die als "läuft" gelten und nicht angetastet werden.
ALIVE_STATES = ("streaming", "paused")


def canonical_uid(value: Any) -> str:
    text = str(value or "").strip()
    if text.upper().startswith("ZIOTA_"):
        text = text[len("ZIOTA_"):]
    return text.upper()


class CameraWatchdog:
    """Prüft periodisch konfigurierte Kameras und provisioniert offline neu."""

    def __init__(self, *,
                 cameras_fn: Callable[[], list[dict[str, Any]]],
                 devices_fn: Callable[[], list[dict[str, Any]]],
                 wifi_fn: Callable[[], dict[str, Any]],
                 provision_fn: Callable[..., dict[str, Any]],
                 credentials_fn: Callable[[], dict[str, Any]],
                 public_ip: str,
                 signaling_port: int = 8882,
                 interval: float = DEFAULT_INTERVAL,
                 cooldown: float = DEFAULT_COOLDOWN,
                 utc_offset: int = 60,
                 auto_connect: bool = True,
                 logger: logging.Logger | None = None) -> None:
        self.cameras_fn = cameras_fn
        self.devices_fn = devices_fn
        self.wifi_fn = wifi_fn
        self.provision_fn = provision_fn
        self.credentials_fn = credentials_fn
        self.public_ip = public_ip
        self.signaling_port = int(signaling_port)
        self.interval = max(10.0, float(interval or DEFAULT_INTERVAL))
        self.cooldown = max(60.0, float(cooldown or DEFAULT_COOLDOWN))
        self.utc_offset = int(utc_offset)
        self.auto_connect = bool(auto_connect)
        self._log = logger or log
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._cooldowns: dict[str, float] = {}
        self._actions: list[dict[str, Any]] = []
        self._last_run: float | None = None
        self._running = False

    # ------------------------------------------------------------- Lifecycle
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="iwfcam-watchdog", daemon=True)
        self._thread.start()
        self._log.info("watchdog gestartet (Intervall %.0fs, Cooldown %.0fs)", self.interval, self.cooldown)

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        self._thread = None
        self._running = False
        if thread is not None:
            thread.join(timeout=3)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - Watchdog darf nie sterben
                self._log.exception("watchdog tick failed")

    # ------------------------------------------------------------------ Tick
    def tick(self, force: bool = False) -> list[dict[str, Any]]:
        """Ein Prüflauf: liefert die Aktionen (provisioniert/übersprungen/Fehler)."""
        now = time.time()
        actions: list[dict[str, Any]] = []
        try:
            cameras = self.cameras_fn() or []
        except Exception as exc:  # noqa: BLE001
            self._log.warning("watchdog: Kamera-Status nicht lesbar: %s", exc)
            cameras = []
        states = {canonical_uid(camera.get("uid")): camera.get("state")
                  for camera in cameras if camera.get("uid")}
        try:
            devices = self.devices_fn() or []
        except Exception as exc:  # noqa: BLE001
            self._log.warning("watchdog: Geräte nicht lesbar: %s", exc)
            devices = []

        wifi: dict[str, Any] | None = None
        for device in devices:
            uid = canonical_uid(device.get("uid"))
            if not uid:
                continue
            state = str(states.get(uid) or "unknown")
            if state in ALIVE_STATES:
                continue
            with self._lock:
                last = self._cooldowns.get(uid, 0.0)
            if not force and now - last < self.cooldown:
                continue
            if wifi is None:
                try:
                    wifi = self.wifi_fn() or {}
                except Exception as exc:  # noqa: BLE001
                    self._log.warning("watchdog: WLAN-Scan fehlgeschlagen: %s", exc)
                    wifi = {}
            access_points = {
                canonical_uid(ap.get("ssid")): ap.get("ssid")
                for ap in (wifi.get("camera_aps") or []) if ap.get("ssid")
            }
            ap_ssid = access_points.get(uid)
            if not ap_ssid:
                continue  # Kamera aus/AP nicht sichtbar -> nichts tun

            try:
                credentials = self.credentials_fn() or {}
            except Exception:  # noqa: BLE001
                credentials = {}
            ssid = str(credentials.get("ssid") or "").strip()
            password = str(credentials.get("password") or "")
            if not ssid or not password:
                action = {"uid": uid, "outcome": "skipped",
                          "reason": "keine WLAN-Zugangsdaten gemerkt", "ts": now}
                actions.append(action)
                self._record(action)
                continue

            with self._lock:
                self._cooldowns[uid] = now
            if not self.public_ip:
                action = {"uid": uid, "outcome": "skipped",
                          "reason": "keine Relay-IP (public_ip) bekannt", "ts": now}
                actions.append(action)
                self._record(action)
                continue
            try:
                result = self.provision_fn(
                    camera_ssid=ap_ssid, ssid=ssid, password=password,
                    server_ip=self.public_ip, server_port=self.signaling_port,
                    utc_offset=self.utc_offset, auto_connect=self.auto_connect,
                )
                ok = bool(result.get("ok"))
                action = {"uid": uid, "camera_ssid": ap_ssid,
                          "outcome": "provisioned" if ok else "failed",
                          "error": result.get("error"), "ts": now}
            except Exception as exc:  # noqa: BLE001
                action = {"uid": uid, "camera_ssid": ap_ssid, "outcome": "error",
                          "error": str(exc), "ts": now}
            actions.append(action)
            self._record(action)
            # Höchstens eine Provisionierung pro Lauf (Host-WLAN wird gewechselt).
            break

        with self._lock:
            self._last_run = now
        return actions

    def _record(self, action: dict[str, Any]) -> None:
        with self._lock:
            self._actions.append(action)
            del self._actions[:-20]
        if action["outcome"] in ("provisioned", "failed", "error"):
            self._log.info("watchdog: uid=%s %s (%s)", action["uid"], action["outcome"],
                           action.get("camera_ssid") or action.get("error") or "")

    # ---------------------------------------------------------------- Status
    def status(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            cooldowns = {uid: round(self.cooldown - (now - ts), 0)
                         for uid, ts in self._cooldowns.items()
                         if now - ts < self.cooldown}
            actions = list(self._actions)
            last_run = self._last_run
        return {
            "enabled": True,
            "running": self._running,
            "interval": self.interval,
            "cooldown": self.cooldown,
            "public_ip": self.public_ip,
            "signaling_port": self.signaling_port,
            "last_run_age_s": round(now - last_run, 1) if last_run else None,
            "cooldown_remaining_s": cooldowns,
            "actions": actions[-10:],
        }
