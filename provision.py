"""WLAN-Provisionierung einer ZIOTA-Kamera über ihren Access Point.

Die Kamera im Provisionierungs-/AP-Modus spannt ein offenes WLAN
``ZIOTA_<uid>`` auf. Auf dessen Gateway (typisch ``192.168.1.1``) nimmt der
Kontrollport **TCP 8266** das Provisioning-Frame an:

```
86 86 | u16(len+5) | u16(seq) | u16(len) | body | u8(XOR) | 0x0D

body: u16(command=1)
      u8(len) SSID, u8(len) WLAN-Passwort,
      u8(len) "server-ip:port", u16(UTC-Offset), u32(Registrierungscode)
```

Die Kamera antwortet mit ``0x8001`` (ACK) und ihrer UID; danach verlässt sie
den AP-Modus, verbindet sich mit dem angegebenen 2,4-GHz-WLAN und meldet sich
beim eigenen Relay-Server (``relay.py``) — der Rest läuft ohne Hersteller-Cloud.

Dieses Modul kapselt den Ablauf inklusive Umschalten des Host-WLANs
(``nmcli``) und Wiederherstellen der vorherigen Verbindung. Getestet gegen
``ZIOTA_196758286858`` (Firmware ``TXW817_A_V1.0.12.24``).
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

AP_CONTROL_PORT = 8266
AP_FRAME_MAGIC = b"\x86\x86"
ACK_COMMAND = 0x8001
NAME_PREFIX = "ZIOTA_"
DEFAULT_PROFILE = "ziot-provision-tmp"

_SSID_RE = re.compile(r"^ZIOTA_[A-Za-z0-9]+$", re.IGNORECASE)
_WIFI_LINE_RE = re.compile(r"^(.*):(-?\d+):(.*):(\d+)\s*(?:MHz)?$")


# --------------------------------------------------------------------------- #
# Frame bauen / ACK parsen (pur, testbar)
# --------------------------------------------------------------------------- #


def build_provisioning_packet(*, ssid: str, password: str, host: str, port: int,
                              offset_minutes: int = 60, registration_code: int = 0,
                              sequence: int = 1) -> bytes:
    """Provisioning-Frame bauen (identisch zum BLE-Frame, hier über TCP 8266)."""
    from .provision_ble import build_provisioning_packet as _build

    return _build(ssid=ssid, password=password, host=host, port=port,
                  offset_minutes=offset_minutes,
                  registration_code=registration_code or 0x5A17C0DE,
                  sequence=sequence)


def parse_ack(data: bytes) -> dict[str, Any] | None:
    """Antwort der Kamera parsen; liefert ``{"ack": bool, "command": int, "uid": str}``."""
    if not data or len(data) < 10 or data[:2] != AP_FRAME_MAGIC:
        return None
    body_len = int.from_bytes(data[6:8], "big")
    if body_len < 2 or len(data) < 8 + body_len:
        return None
    body = data[8:8 + body_len]
    command = int.from_bytes(body[0:2], "big")
    payload = body[2:]
    uid = ""
    if len(payload) >= 2:
        uid_len = int.from_bytes(payload[0:2], "big")
        if 0 < uid_len <= len(payload) - 2:
            uid = payload[2:2 + uid_len].decode("ascii", "replace")
    return {"ack": command in (ACK_COMMAND, 0x8000), "command": command,
            "uid": uid, "raw": data.hex()}


# --------------------------------------------------------------------------- #
# Host-WLAN über NetworkManager
# --------------------------------------------------------------------------- #


def _run(*args: str, timeout: float = 40.0) -> tuple[int, str, str]:
    try:
        result = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)
        return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", f"{args[0]} nicht gefunden"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timeout: {' '.join(args)}"


def current_wifi() -> dict[str, Any]:
    """Aktive WLAN-Verbindung des Hosts (Name, SSID, IPv4)."""
    connection = None
    code, out, _err = _run("nmcli", "-t", "-f", "NAME,DEVICE,TYPE", "con", "show", "--active")
    if code == 0:
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[1] == "wlan0" and parts[2] == "802-11-wireless":
                connection = parts[0]
                break
    ssid = None
    ip = None
    if connection:
        code, detail, _err = _run("nmcli", "-t", "-f", "GENERAL.CONNECTION", "dev", "show", "wlan0")
        code2, out2, _err2 = _run("nmcli", "-t", "-f", "IP4.ADDRESS", "dev", "show", "wlan0")
        if code2 == 0 and out2:
            ip = out2.splitlines()[0].split(":")[-1].split("/")[0]
        code3, out3, _err3 = _run("iw", "dev", "wlan0", "link")
        if code3 == 0:
            for line in out3.splitlines():
                if "SSID:" in line:
                    ssid = line.split("SSID:", 1)[1].strip()
    return {"connection": connection, "ssid": ssid, "ipv4": ip}


def nearby_networks(rescan: bool = True, timeout: float = 30.0) -> list[dict[str, Any]]:
    """WLANs in Reichweite (SSID, Signal, Security, Frequenz)."""
    args = ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,FREQ", "dev", "wifi", "list"]
    if rescan:
        args += ["--rescan", "yes"]
    code, out, _err = _run(*args, timeout=timeout)
    if code != 0 or not out:
        return []
    networks: list[dict[str, Any]] = []
    for line in out.splitlines():
        match = _WIFI_LINE_RE.match(line)
        if not match:
            continue
        ssid = match.group(1).replace("\\:", ":").replace("\\\\", "\\").strip()
        if not ssid:
            continue
        try:
            freq = int(match.group(4))
        except ValueError:
            freq = 0
        networks.append({
            "ssid": ssid,
            "signal": int(match.group(2) or 0),
            "security": match.group(3).strip() or None,
            "freq": freq,
            "band": "2.4 GHz" if freq and freq < 3000 else ("5 GHz" if freq else "?"),
            "is_camera_ap": bool(_SSID_RE.match(ssid)),
        })
    return networks


def _gateway() -> str | None:
    code, out, _err = _run("ip", "route")
    if code != 0:
        return None
    for line in out.splitlines():
        if line.startswith("default") and "wlan0" in line:
            parts = line.split()
            if len(parts) >= 3:
                return parts[2]
    return None


def _connect_ap(ssid: str, profile: str = DEFAULT_PROFILE) -> dict[str, Any]:
    _run("nmcli", "con", "delete", profile)
    code, out, err = _run("nmcli", "con", "add", "type", "wifi", "con-name", profile, "ssid", ssid)
    if code != 0:
        return {"ok": False, "message": err or out}
    code, out, err = _run("nmcli", "con", "up", profile, timeout=45)
    return {"ok": code == 0, "message": out or err}


def _restore(connection: str | None, profile: str = DEFAULT_PROFILE) -> dict[str, Any]:
    _run("nmcli", "con", "delete", profile)
    if not connection:
        return {"ok": True, "message": "keine vorherige WLAN-Verbindung"}
    code, out, err = _run("nmcli", "con", "up", connection, timeout=45)
    return {"ok": code == 0, "message": out or err}


def _wait_for_gateway(timeout: float = 20.0) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        gateway = _gateway()
        if gateway:
            return gateway
        time.sleep(1)
    return None


def _send_packet(host: str, port: int, packet: bytes, timeout: float = 8.0) -> bytes:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(packet)
        sock.settimeout(timeout)
        try:
            return sock.recv(4096)
        except socket.timeout:
            return b""


# --------------------------------------------------------------------------- #
# Ablauf
# --------------------------------------------------------------------------- #


def provision(*, camera_ssid: str, ssid: str, password: str,
              server_ip: str, server_port: int = 8882,
              utc_offset: int = 60, auto_connect: bool = True,
              profile: str = DEFAULT_PROFILE, verify_seconds: float = 0.0) -> dict[str, Any]:
    """Kamera per AP-Modus ins WLAN bringen und auf den Relay-Server zeigen.

    ``auto_connect`` verbindet den Host dafür kurz mit dem Kamera-AP und
    stellt anschließend die vorherige WLAN-Verbindung wieder her.
    """
    if not camera_ssid.upper().startswith(NAME_PREFIX):
        return {"ok": False, "error": f"Kein Kamera-AP ({NAME_PREFIX}…): {camera_ssid!r}"}
    if not ssid or not password:
        return {"ok": False, "error": "WLAN-SSID und WLAN-Passwort erforderlich"}
    if not server_ip:
        return {"ok": False, "error": "server_ip (LAN-IPv4 des Relay-Hosts) erforderlich"}

    steps: list[dict[str, Any]] = []
    previous = current_wifi()
    steps.append({"step": "current", **previous})
    reconnected = False
    try:
        if auto_connect:
            connect = _connect_ap(camera_ssid, profile)
            steps.append({"step": "connect-camera-ap", **connect})
            if not connect.get("ok"):
                return {"ok": False, "error": "Host konnte nicht mit dem Kamera-AP verbinden",
                        "steps": steps}
            reconnected = True
            gateway = _wait_for_gateway(20)
            steps.append({"step": "gateway", "gateway": gateway})
        else:
            gateway = _gateway()
            steps.append({"step": "gateway", "gateway": gateway, "auto_connect": False})
        if not gateway:
            return {"ok": False, "error": "Kein Gateway im Kamera-AP-Netz gefunden", "steps": steps}

        packet = build_provisioning_packet(
            ssid=ssid, password=password, host=server_ip, port=int(server_port),
            offset_minutes=int(utc_offset),
        )
        steps.append({"step": "send", "gateway": gateway, "port": AP_CONTROL_PORT,
                      "bytes": len(packet)})
        response = _send_packet(gateway, AP_CONTROL_PORT, packet)
        ack = parse_ack(response)
        steps.append({"step": "response", "ack": ack})
        if not ack or not ack.get("ack"):
            return {"ok": False,
                    "error": "Kamera hat das Provisioning nicht bestätigt (kein 0x8001-ACK)",
                    "steps": steps}

        if verify_seconds > 0:
            time.sleep(verify_seconds)
            steps.append({"step": "verify", "camera_still_visible":
                          any(n["ssid"].upper() == camera_ssid.upper()
                              for n in nearby_networks(rescan=True))})

        return {
            "ok": True,
            "camera_uid": ack.get("uid") or camera_ssid,
            "ssid": ssid,
            "server": f"{server_ip}:{server_port}",
            "steps": steps,
            "hint": "Kamera verbindet sich jetzt mit dem WLAN und meldet sich beim Relay-Server.",
        }
    finally:
        if reconnected:
            restore = _restore(previous.get("connection"), profile)
            steps.append({"step": "restore", **restore})


def status() -> dict[str, Any]:
    """Aktuelle WLAN-Situation + sichtbare Kamera-APs/nachbarliche Netze."""
    current = current_wifi()
    networks = nearby_networks()
    return {
        "ok": True,
        "current": current,
        "camera_aps": [n for n in networks if n["is_camera_ap"]],
        "networks": networks,
    }
