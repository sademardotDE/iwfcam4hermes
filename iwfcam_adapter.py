#!/usr/bin/env python3
"""iWFCam-Adapter (libZGP2PComm.so).

Die native Bibliothek ist ARM64 (aarch64); auf x86_64-Hosts wird sie nicht
geladen. Der Adapter liefert dann nur die per ``strings`` extrahierten
JNI-Funktionsnamen (Stubs) — das ist der dokumentierte, ehrliche Fallback.

Der Bibliothekspfad ist konfigurierbar (Reihenfolge):
``$IWFCAM_LIB`` > ``so/lib/arm64-v8a/libZGP2PComm.so`` im Plugin-Verzeichnis >
``~/.hermes/iwfcam4hermes/libZGP2PComm.so``.
"""

from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger("iwfcam_adapter")

_PLUGIN_ROOT = Path(__file__).resolve().parent
LIB_CANDIDATES = [
    _PLUGIN_ROOT / "so" / "lib" / "arm64-v8a" / "libZGP2PComm.so",
    _PLUGIN_ROOT / "libZGP2PComm.so",
    Path.home() / ".hermes" / "iwfcam4hermes" / "libZGP2PComm.so",
]


def _default_lib_path() -> Path:
    env = os.environ.get("IWFCAM_LIB", "").strip()
    if env:
        return Path(env).expanduser()
    for candidate in LIB_CANDIDATES:
        if candidate.exists():
            return candidate
    return LIB_CANDIDATES[0]


LIB_PATH = _default_lib_path()

try:  # package import
    from .iwfcam_jni_stubs import JNI_FUNCTIONS
except ImportError:  # run as a standalone script
    from iwfcam_jni_stubs import JNI_FUNCTIONS


class IWFCamAdapter:
    """Minimal adapter for iWFCam/ESNTD cameras via libZGP2PComm.so."""

    def __init__(self, lib_path: str | None = None):
        self.lib_path = str(lib_path or _default_lib_path())
        self._lib = None
        self.functions = JNI_FUNCTIONS

    def load(self) -> bool:
        """Bibliothek laden (oder Stubs aktiv lassen). ``False`` nur bei echtem Fehler."""
        if not os.path.exists(self.lib_path):
            log.warning("Library not found (%s); using stubs only", self.lib_path)
            self._lib = None
            return True
        import platform

        if platform.machine() not in ("aarch64", "arm64"):
            log.warning("Host arch %s != lib arch; using stubs only", platform.machine())
            self._lib = None
            return True
        try:
            self._lib = ctypes.CDLL(self.lib_path)
            log.info("Loaded %s", self.lib_path)
            return True
        except Exception as e:
            log.error("Failed to load library: %s", e)
            return False

    def list_functions(self, pattern: str = "") -> list[str]:
        if pattern:
            return [f for f in self.functions if pattern.lower() in f.lower()]
        return self.functions

    # Historischer Name aus der CLI; bleibt als Alias erhalten.
    list_symbols = list_functions

    def close(self) -> None:
        self._lib = None


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="iwfcam_adapter")
    parser.add_argument("--lib", default=None, help="Pfad zu libZGP2PComm.so")
    parser.add_argument("--pattern", default="P2P", help="Filter für Funktionsnamen")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    adapter = IWFCamAdapter(lib_path=args.lib)
    if not adapter.load():
        print("Failed to load library.")
        return 1
    funcs = adapter.list_functions(args.pattern)
    print(f"Found {len(funcs)} functions matching '{args.pattern}'")
    for name in funcs[:50]:
        print("  ", name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
