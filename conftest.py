"""Pytest-Konfiguration für das iwfcam4hermes-Plugin.

Die Testmodule mischen zwei Import-Stile: ``import iwfcam4hermes...`` (Paket)
und ``from rtp_receiver import ...`` (flach, historisch). Damit beide
unabhängig vom Aufrufverzeichnis funktionieren, liegt das Plugin-Verzeichnis
zusätzlich auf ``sys.path``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent
for _entry in (_PLUGIN_DIR.parent, _PLUGIN_DIR):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))
