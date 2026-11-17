"""Pytest-Konfiguration für das iwfcam4hermes-Plugin.

Die Testmodule mischen zwei Import-Stile: ``import iwfcam4hermes...`` (Paket)
und ``from rtp_receiver import ...`` (flach, historisch). Damit beide
unabhängig vom Aufrufverzeichnis funktionieren, liegt das Plugin-Verzeichnis
zusätzlich auf ``sys.path``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PLUGIN_DIR = Path(__file__).resolve().parent
for _entry in (_PLUGIN_DIR.parent, _PLUGIN_DIR):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))


@pytest.fixture(autouse=True)
def _isolated_hermes_home(tmp_path, monkeypatch):
    """Jeder Test bekommt ein leeres HERMES_HOME (keine echten Configs anfassen)."""
    home = tmp_path / "hermes-home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home
