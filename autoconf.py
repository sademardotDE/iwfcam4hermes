"""Autoconf: ZIOT-Kameras automatisch finden und zur Konfiguration hinzufügen.

Discovery-Kanäle (ohne Cloud, ohne App):

* **WLAN-AP-Scan** — Kameras im Provisionierungs-/AP-Modus senden ihr eigenes
  offenes WLAN ``ZIOTA_<id>``. Der Scan ist der zuverlässigste Weg zur UID.
* **BLE-Advertising** — dieselben Kameras werben mit dem BLE-Namen
  ``ZIOTA_<id>`` (``bleak`` nötig; fehlt es, wird dieser Kanal übersprungen).
* **Aktueller Kamera-AP** — ist der Host gerade mit einem ``ZIOTA_*``-AP
  verbunden, wird dessen Kontrollport (TCP 8266) abgefragt und die RTSP-URL
  (``rtsp://<gw>:7070/webcam/jpeg_dvp``) übernommen.

Aus den Funden werden Konfigurations-Einträge gebaut (ID/Name aus der UID,
AP-Modus-RTSP als Stream-URL) und optional direkt gespeichert.
"""

from __future__ import annotations

import shutil

import os

import asyncio
import json
import re
import socket
import subprocess
from pathlib import Path
from typing import Any

NAME_PREFIX = "ZIOTA_"
AP_CONTROL_PORT = 8266
AP_RTSP_PORT = 7070
AP_STREAM_PATH = "/webcam/jpeg_dvp"
AP_CONTROL_FRAME = bytes.fromhex("8686000900010004000201010e0d")
_RTSP_RE = re.compile(rb"rtsp://[ -~]+")
_UID_RE = re.compile(r"^ZIOTA_([A-Za-z0-9]+)$")


# --------------------------------------------------------------------------- #
# WLAN / AP-Scan
# --------------------------------------------------------------------------- #


def _run(args: list[str], timeout: float = 25.0) -> tuple[int, str, str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", f"{args[0]} nicht gefunden"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timeout: {' '.join(args)}"


def parse_wifi_multiline(text: str) -> list[dict[str, Any]]:
    """``nmcli -m multiline``-Ausgabe in Netzwerk-Dicts übersetzen."""
    networks: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().upper()
        if key == "SSID" and current.get("ssid"):
            networks.append(current)
            current = {}
        if key in ("SSID", "BSSID", "SIGNAL", "SECURITY"):
            current[key.lower()] = value.strip()
    if current.get("ssid"):
        networks.append(current)
    return networks


def parse_wifi_ssid_only(text: str) -> list[dict[str, Any]]:
    """Fallback: eine SSID pro Zeile (nmcli -t -f SSID)."""
    networks = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line:
            networks.append({"ssid": line.replace("\\:", ":").replace("\\\\", "\\")})
    return networks


def discover_wifi(timeout: float = 25.0) -> list[dict[str, Any]]:
    """WLANs scannen (nmcli); nur ``ZIOTA_*``-APs zurückgeben."""
    code, out, _err = _run(
        ["nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,SECURITY", "-m", "multiline",
         "dev", "wifi", "list", "--rescan", "yes"], timeout=timeout)
    networks = parse_wifi_multiline(out) if code == 0 and out else []
    if not networks:
        code, out, _err = _run(["nmcli", "-t", "-f", "SSID", "dev", "wifi", "list"], timeout=timeout)
        if code == 0 and out:
            networks = parse_wifi_ssid_only(out)
    found = []
    for network in networks:
        ssid = str(network.get("ssid") or "").strip()
        if not ssid.upper().startswith(NAME_PREFIX):
            continue
        found.append({
            "ssid": ssid,
            "bssid": network.get("bssid"),
            "signal": _to_int(network.get("signal")),
            "security": network.get("security") or None,
        })
    return found


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def current_ap() -> dict[str, Any] | None:
    """Wenn der Host gerade mit einem ZIOTA-AP verbunden ist: SSID + Gateway."""
    _code, out, _err = _run(["iw", "dev", "wlan0", "link"], timeout=10)
    ssid = None
    for line in out.splitlines():
        line = line.strip()
        if line.lower().startswith("ssid:"):
            ssid = line.split(":", 1)[1].strip()
    if not ssid or not ssid.upper().startswith(NAME_PREFIX):
        return None
    gateway = None
    _code, route, _err = _run(["ip", "route"], timeout=10)
    for line in route.splitlines():
        if line.startswith("default") and "wlan0" in line:
            parts = line.split()
            if len(parts) >= 3:
                gateway = parts[2]
            break
    return {"ssid": ssid, "gateway": gateway}


def query_ap_rtsp(gateway: str, timeout: float = 3.0) -> str | None:
    """Kontrollport 8266 eines Kamera-APs abfragen → RTSP-URL (None bei Fehler)."""
    try:
        with socket.create_connection((gateway, AP_CONTROL_PORT), timeout=timeout) as sock:
            sock.sendall(AP_CONTROL_FRAME)
            sock.settimeout(timeout)
            data = sock.recv(4096)
    except OSError:
        return None
    match = _RTSP_RE.search(data)
    if not match:
        return None
    return match.group(0).decode("ascii", errors="strict").rstrip("/")


def parse_rtsp_url(url: str) -> dict[str, Any] | None:
    """``rtsp://host:port/path`` in host/port/path zerlegen."""
    match = re.match(r"^rtsp://([^/:]+)(?::(\d+))?(/.*)?$", url.strip())
    if not match:
        return None
    host, port, path = match.group(1), match.group(2), match.group(3) or "/"
    return {"host": host, "port": int(port) if port else 554, "path": path}


# --------------------------------------------------------------------------- #
# BLE-Scan
# --------------------------------------------------------------------------- #


_BLE_SCAN_SCRIPT = r"""
import asyncio, json, sys
from bleak import BleakScanner

async def main():
    devices = await BleakScanner.discover(timeout=float(sys.argv[1]))
    found = []
    for device in devices:
        name = getattr(device, "name", None) or ""
        if not str(name).upper().startswith(sys.argv[2].upper()):
            continue
        found.append({
            "ble_name": str(name),
            "ble_address": getattr(device, "address", None),
            "ble_rssi": getattr(device, "rssi", None),
        })
    print(json.dumps(found))

asyncio.run(main())
"""


def _ble_via_subprocess(timeout: float) -> tuple[list[dict[str, Any]] | None, str | None]:
    """BLE-Scan über einen Interpreter mit ``bleak`` (Plugin-Sandbox hat oft keinen Zugriff).

    Kandidaten: ``IWFCAM_BLE_PYTHON``, ``/usr/bin/python3``, ``python3`` im PATH.
    Liefert ``(None, None)``, wenn kein Interpreter mit bleak gefunden wurde.
    """
    candidates = []
    explicit = os.environ.get("IWFCAM_BLE_PYTHON", "").strip()
    if explicit:
        candidates.append(explicit)
    candidates.extend(["/usr/bin/python3", shutil.which("python3") or ""])
    seen = set()
    last_error = None
    for python in candidates:
        if not python or python in seen:
            continue
        seen.add(python)
        try:
            proc = subprocess.run(
                [python, "-c", _BLE_SCAN_SCRIPT, str(float(timeout)), NAME_PREFIX],
                capture_output=True, text=True, timeout=float(timeout) + 20.0,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            last_error = str(exc)
            continue
        if proc.returncode != 0:
            last_error = (proc.stderr or "").strip().splitlines()[-1:] or [None]
            last_error = last_error[0]
            if "No module named 'bleak'" in (proc.stderr or ""):
                continue
            break
        try:
            payload = json.loads(proc.stdout or "[]")
        except ValueError:
            last_error = "ungültige BLE-Scan-Ausgabe"
            continue
        if isinstance(payload, list):
            return payload, None
    return None, last_error


def discover_ble(timeout: float = 8.0) -> tuple[list[dict[str, Any]], str | None]:
    """BLE-Advertising scannen; gibt (Geraete, Fehlerhinweis) zurueck.

    Nutzt zuerst `bleak` im aktuellen Prozess; ist es hier nicht importierbar
    (Plugin-Sandbox) oder fehlt der Adapter, wird der Scan über einen System-
    Interpreter mit bleak (``IWFCAM_BLE_PYTHON``/``/usr/bin/python3``) ausgeführt.
    """
    found: list[dict[str, Any]] = []
    error: str | None = None
    try:
        from bleak import BleakScanner
    except ImportError:
        BleakScanner = None  # type: ignore[assignment]
    if BleakScanner is not None:
        try:
            devices = asyncio.run(BleakScanner.discover(timeout=timeout))
        except Exception as exc:  # noqa: BLE001 - fehlender Adapter/Rechte
            error = f"BLE-Scan fehlgeschlagen: {exc}"
        else:
            for device in devices:
                name = str(getattr(device, "name", "") or "")
                if not name.upper().startswith(NAME_PREFIX):
                    continue
                found.append({
                    "ble_name": name,
                    "ble_address": getattr(device, "address", None),
                    "ble_rssi": getattr(device, "rssi", None),
                })
            return found, None

    # Fallback: Subprozess mit System-Python (dort ist bleak meist installiert).
    payload, sub_error = _ble_via_subprocess(timeout)
    if payload is not None:
        return payload, None
    if sub_error:
        error = f"BLE-Scan nicht möglich: {sub_error}"
    if error is None:
        error = ("bleak nicht verfügbar (weder im Plugin noch in /usr/bin/python3) — "
                 "BLE-Kanal übersprungen, WLAN-AP-Scan genügt")
    return found, error


# --------------------------------------------------------------------------- #
# Zusammenführen / Vorschläge
# --------------------------------------------------------------------------- #


def discover(mode: str = "both", *, ble_timeout: float = 8.0,
             wifi_timeout: float = 25.0) -> dict[str, Any]:
    """Alle Kanäle scannen und pro UID zusammenführen."""
    mode = (mode or "both").lower()
    wifi = discover_wifi(timeout=wifi_timeout) if mode in ("both", "wifi") else []
    ble, ble_error = discover_ble(ble_timeout) if mode in ("both", "ble") else ([], None)

    cameras: dict[str, dict[str, Any]] = {}

    def entry(uid: str) -> dict[str, Any]:
        return cameras.setdefault(uid, {
            "uid": uid, "sources": [], "ssid": None, "bssid": None, "signal": None,
            "security": None, "ble_address": None, "ble_rssi": None,
        })

    for network in wifi:
        uid = network["ssid"].upper()
        item = entry(uid)
        item.update({"ssid": network.get("ssid"), "bssid": network.get("bssid"),
                     "signal": network.get("signal"), "security": network.get("security")})
        if "wifi" not in item["sources"]:
            item["sources"].append("wifi")

    for device in ble:
        uid = device["ble_name"].upper()
        item = entry(uid)
        item.update({"ble_address": device.get("ble_address"), "ble_rssi": device.get("ble_rssi")})
        if "ble" not in item["sources"]:
            item["sources"].append("ble")

    ap = current_ap()
    rtsp_url = None
    if ap and ap.get("gateway"):
        rtsp_url = query_ap_rtsp(ap["gateway"])
        uid = ap["ssid"].upper()
        item = entry(uid)
        item["ap_ssid"] = ap["ssid"]
        item["ap_gateway"] = ap["gateway"]
        item["rtsp_url"] = rtsp_url
        if "ap" not in item["sources"]:
            item["sources"].append("ap")

    ordered = sorted(cameras.values(), key=lambda item: item["uid"])
    return {
        "ok": True,
        "mode": mode,
        "cameras": ordered,
        "wifi": wifi,
        "ble": ble,
        "ble_error": ble_error,
        "current_ap": ap,
    }


def _device_id(uid: str, taken: set[str]) -> str:
    match = _UID_RE.match(uid.strip().upper())
    base = f"ziota-{match.group(1).lower()}" if match else uid.lower().replace("_", "-")
    candidate = base
    counter = 2
    while candidate in taken:
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def suggest_device(camera: dict[str, Any], *, taken: set[str] | None = None) -> dict[str, Any]:
    """Konfigurations-Eintrag für eine gefundene Kamera vorschlagen."""
    uid = str(camera.get("uid") or "").strip()
    device_id = _device_id(uid, taken or set())
    match = _UID_RE.match(uid)
    number = match.group(1) if match else device_id

    rtsp = parse_rtsp_url(camera.get("rtsp_url") or "") or {}
    host = rtsp.get("host") or (camera.get("ap_gateway") or "192.168.1.1")
    port = rtsp.get("port") or AP_RTSP_PORT
    path = rtsp.get("path") or AP_STREAM_PATH
    sources = ", ".join(camera.get("sources") or [])
    notes = (f"Autoconf ({sources}): Kamera im AP-Modus; Host muss im WLAN "
             f"'{camera.get('ssid') or uid}' sein, RTSP {host}:{port}{path}")
    return {
        "id": device_id,
        "name": f"ZIOTA {number}",
        "type": "iwfcam",
        "uid": uid,
        "host": host,
        "port": port,
        "stream_path": path,
        "snapshot_path": "/snapshot",
        "relay_mode": True,
        "mock": False,
        "notes": notes,
    }


def autoconf(*, apply: bool = False, mode: str = "both", path: str | Path | None = None,
             ble_timeout: float = 8.0, wifi_timeout: float = 25.0) -> dict[str, Any]:
    """Kameras finden (und optional direkt zur Konfiguration hinzufügen)."""
    from . import config_store

    discovery = discover(mode=mode, ble_timeout=ble_timeout, wifi_timeout=wifi_timeout)
    resolved = config_store.resolve_config_path(path)
    fresh = resolved.name == "config.example.json" or not resolved.is_file()
    existing = [] if fresh else config_store.list_devices(path)
    existing_ids = {str(item.get("id")) for item in existing if item.get("id")}
    existing_uids = {str(item.get("uid")).upper() for item in existing if item.get("uid")}

    suggestions: list[dict[str, Any]] = []
    added: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    if apply and fresh:
        # Erste Nutzerkonfiguration: ohne die fiktiven Beispielgeräte starten.
        config_store.save({"devices": []}, path)

    for camera in discovery["cameras"]:
        uid = camera["uid"]
        if uid in existing_uids:
            skipped.append({"uid": uid, "reason": "bereits konfiguriert"})
            continue
        suggestion = suggest_device(camera, taken=existing_ids)
        suggestions.append(suggestion)
        if not apply:
            continue
        try:
            device, written = config_store.add_device(suggestion, path)
            existing_ids.add(device["id"])
            existing_uids.add(uid)
            added.append({"device": device, "config": str(written)})
        except config_store.ConfigError as exc:
            skipped.append({"uid": uid, "reason": str(exc)})

    return {
        "ok": True,
        "applied": bool(apply),
        "found": len(discovery["cameras"]),
        "cameras": discovery["cameras"],
        "suggestions": suggestions,
        "added": added,
        "skipped": skipped,
        "ble_error": discovery.get("ble_error"),
        "current_ap": discovery.get("current_ap"),
    }
