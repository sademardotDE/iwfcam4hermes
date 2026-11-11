"""Steuerung der Samba- und MiniDLNA-Dienste (systemd).

Bewusst eigenständig und ohne Fremdcode: das Plugin startet/stoppt die
systemd-Units ``smb.service``/``nmb.service`` (Samba) und
``minidlna.service`` (MiniDLNA) und meldet deren Zustand. Für start/stop wird
``sudo`` verwendet, für Statusabfragen nicht. Fehlen die Units oder ist kein
systemd vorhanden, liefern die Funktionen einen Fehler statt einer Exception.
"""

from __future__ import annotations

import subprocess
from typing import Any

TIMEOUT_SECONDS = 15

# service name -> (systemd units)
SERVICES: dict[str, tuple[str, ...]] = {
    "smb": ("smb.service", "nmb.service"),
    "dlna": ("minidlna.service",),
}


def _run(*args: str) -> tuple[int, str, str]:
    """Führe einen Befehl aus und liefere ``(returncode, stdout, stderr)``."""
    try:
        res = subprocess.run(
            list(args), capture_output=True, text=True, timeout=TIMEOUT_SECONDS
        )
        return res.returncode, (res.stdout or "").strip(), (res.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", f"Befehl nicht gefunden: {args[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timeout nach {TIMEOUT_SECONDS}s: {' '.join(args)}"


def _systemctl(action: str, unit: str, *, sudo: bool = False) -> tuple[bool, str]:
    cmd = (["sudo", "systemctl", action, unit] if sudo
           else ["systemctl", action, unit])
    code, out, err = _run(*cmd)
    ok = code == 0
    message = out or err or f"systemctl {action} {unit}"
    return ok, message


def unit_status(unit: str) -> dict[str, Any]:
    """Zustand einer Unit: ``active``/``enabled``.""" 
    active_code, _, _ = _run("systemctl", "is-active", unit)
    enabled_code, _, _ = _run("systemctl", "is-enabled", unit)
    return {"unit": unit, "active": active_code == 0, "enabled": enabled_code == 0}


def status() -> dict[str, Any]:
    """Status aller bekannten Dienste als JSON-fähiges Dict."""
    services: dict[str, Any] = {}
    for name, units in SERVICES.items():
        services[name] = {
            "units": {unit: unit_status(unit) for unit in units},
            "active": all(unit_status(unit)["active"] for unit in units),
        }
    return {"ok": True, "services": services}


def _select(service: str) -> list[str]:
    name = (service or "all").strip().lower()
    if name in ("all", "*", ""):
        return list(SERVICES)
    if name not in SERVICES:
        raise ValueError(
            f"Unbekannter Dienst {service!r}; erwartet: all, {', '.join(SERVICES)}"
        )
    return [name]


def start(service: str = "all") -> dict[str, Any]:
    """Starte ``smb``, ``dlna`` oder ``all``."""
    try:
        names = _select(service)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    results: dict[str, Any] = {}
    for name in names:
        unit_results = []
        for unit in SERVICES[name]:
            ok, message = _systemctl("start", unit, sudo=True)
            unit_results.append({"unit": unit, "ok": ok, "message": message})
        results[name] = {
            "ok": all(item["ok"] for item in unit_results),
            "units": unit_results,
        }
    return {"ok": all(item["ok"] for item in results.values()), "started": results}


def stop(service: str = "all") -> dict[str, Any]:
    """Stoppe ``smb``, ``dlna`` oder ``all``."""
    try:
        names = _select(service)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    results: dict[str, Any] = {}
    for name in names:
        unit_results = []
        # nmb zuerst stoppen, dann smb; das ist die übliche Reihenfolge.
        for unit in reversed(SERVICES[name]):
            ok, message = _systemctl("stop", unit, sudo=True)
            unit_results.append({"unit": unit, "ok": ok, "message": message})
        results[name] = {
            "ok": all(item["ok"] for item in unit_results),
            "units": unit_results,
        }
    return {"ok": all(item["ok"] for item in results.values()), "stopped": results}
