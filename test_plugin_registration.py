#!/usr/bin/env python3
"""Tests für die Hermes-Plugin-Oberfläche (Manifest, register(), Tools, Services).

Diese Tests brauchen weder Netzwerk noch Kamera-Hardware: sie prüfen den
Vertrag, den Hermes beim Laden des Verzeichnis-Plugins erwartet.
"""

import json
from pathlib import Path

import pytest

import iwfcam4hermes
from iwfcam4hermes.plugin_tools import TOOL_SCHEMAS

PLUGIN_DIR = Path(__file__).resolve().parent


class RecordingContext:
    """Minimaler PluginContext-Ersatz (wie im Hermes-Validator-Probe)."""

    plugin_config = {}
    profile_name = "default"
    plugin_id = "iwfcam4hermes"

    def __init__(self):
        self.tools = []
        self.commands = []
        self.skills = []

    def register_tool(self, name, toolset, schema, handler, **kwargs):
        self.tools.append({"name": name, "toolset": toolset, "schema": schema,
                           "handler": handler, **kwargs})

    def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
        self.commands.append({"name": name, "help": help, "setup_fn": setup_fn,
                              "handler_fn": handler_fn})

    def register_command(self, name, handler, **kwargs):  # pragma: no cover - nicht genutzt
        self.commands.append({"name": name})

    def register_skill(self, *args, **kwargs):  # pragma: no cover - nicht genutzt
        self.skills.append(args)

    def get_config(self, key, default=None):
        return default


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Nie die echte Nutzer-Konfiguration lesen/schreiben."""
    monkeypatch.delenv("IWFCAM_CONFIG", raising=False)
    home = tmp_path / "hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


@pytest.fixture
def ctx():
    context = RecordingContext()
    iwfcam4hermes.register(context)
    return context


def _manifest() -> dict:
    import yaml

    return yaml.safe_load((PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8"))


def test_manifest_is_loadable():
    manifest = _manifest()
    assert manifest["name"] == "iwfcam4hermes"
    assert manifest["version"] == iwfcam4hermes.__version__
    assert manifest["description"]
    # Hermes braucht __init__.py mit register() als Einstiegspunkt.
    assert (PLUGIN_DIR / "__init__.py").is_file()
    assert callable(iwfcam4hermes.register)


def test_manifest_declares_exactly_the_registered_tools(ctx):
    declared = set(_manifest()["provides_tools"])
    registered = {tool["name"] for tool in ctx.tools}
    assert declared == registered == set(TOOL_SCHEMAS)
    assert len(registered) == 23


def test_register_registers_cli_command(ctx):
    assert [command["name"] for command in ctx.commands] == ["cameras"]


def test_register_is_side_effect_free_without_config(ctx):
    # register() darf keine Konfiguration/Hardware voraussetzen.
    assert ctx.tools
    assert all(tool["toolset"] == "cameras" for tool in ctx.tools)


READ_ONLY_TOOLS = (
    "camera_list", "camera_get", "camera_stream_url", "camera_snapshot_url",
    "camera_sources", "camera_receiver_status",
)

READ_ONLY_RELAY_TOOLS = ("camera_snapshots",)


def test_tools_are_reported_as_json_strings(ctx):
    """Nur lesende Tools aufrufen — mutierende würden systemctl/Netz auslösen."""
    handlers = {tool["name"]: tool["handler"] for tool in ctx.tools}
    for name in READ_ONLY_TOOLS:
        result = handlers[name]({})
        assert isinstance(result, str), name
        parsed = json.loads(result)
        assert isinstance(parsed, dict), name
        assert "ok" in parsed or "error" in parsed, name


def test_mutation_tools_reject_invalid_input_without_side_effects(ctx):
    handlers = {tool["name"]: tool["handler"] for tool in ctx.tools}
    # Ungültige/fehlende Daten müssen als JSON-Fehler enden, bevor etwas geschrieben wird.
    for name in ("camera_add", "camera_update", "camera_remove", "camera_test"):
        parsed = json.loads(handlers[name]({}))
        assert parsed["ok"] is False, name


def test_camera_list_uses_bundled_example(ctx):
    handlers = {tool["name"]: tool["handler"] for tool in ctx.tools}
    result = json.loads(handlers["camera_list"]({}))
    assert result["ok"] is True
    assert result["count"] == 3
    assert {device["id"] for device in result["devices"]} == {"cam1", "cam2", "cam3"}


def test_camera_snapshot_mock(ctx, tmp_path):
    handlers = {tool["name"]: tool["handler"] for tool in ctx.tools}
    output = tmp_path / "snap.jpg"
    result = json.loads(handlers["camera_snapshot"]({"device_id": "cam3", "output": str(output)}))
    assert result["ok"] is True
    assert output.is_file() and output.stat().st_size > 0


def test_unknown_camera_returns_error(ctx):
    handlers = {tool["name"]: tool["handler"] for tool in ctx.tools}
    result = json.loads(handlers["camera_get"]({"device_id": "does-not-exist"}))
    assert result["ok"] is False
    assert "does-not-exist" in result["error"]


def test_receiver_status_when_stopped(ctx):
    handlers = {tool["name"]: tool["handler"] for tool in ctx.tools}
    result = json.loads(handlers["camera_receiver_status"]({}))
    assert result == {"ok": True, "running": False}


def test_hermes_plugin_default_config():
    from iwfcam4hermes.hermes_plugin import create_plugin

    plugin = create_plugin()
    assert plugin.status()["devices"] == 3
    assert plugin.status()["version"] == iwfcam4hermes.__version__


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
