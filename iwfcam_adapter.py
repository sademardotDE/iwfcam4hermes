#!/usr/bin/env python3
"""iWFCam adapter (libZGP2PComm.so based)."""

import ctypes
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger("iwfcam_adapter")

LIB_PATH = Path("/workspace/iwfcam/so/lib/arm64-v8a/libZGP2PComm.so")


from .iwfcam_jni_stubs import JNI_FUNCTIONS

class IWFCamAdapter:
    """Minimal adapter for iWFCam/ESNTD cameras via libZGP2PComm.so."""

    def __init__(self, lib_path: str = str(LIB_PATH)):
        self.lib_path = lib_path
        self._lib = None
        self.functions = JNI_FUNCTIONS

    def load(self) -> bool:
        if not os.path.exists(self.lib_path):
            log.error("Library not found: %s", self.lib_path)
            return False
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

    def close(self) -> None:
        self._lib = None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--lib", default=str(LIB_PATH))
    parser.add_argument("--pattern", default="P2P")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    adapter = IWFCamAdapter(lib_path=args.lib)
    if adapter.load():
        syms = adapter.list_symbols(args.pattern)
        print(f"Found {len(syms)} symbols matching '{args.pattern}':")
        for s in syms[:50]:
            print("  ", s)
    else:
        print("Failed to load library.")
