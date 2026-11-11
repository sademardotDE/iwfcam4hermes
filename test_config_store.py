#!/usr/bin/env python3
"""Tests für den schreibbaren Konfigurations-Store (config_store)."""

import json
from pathlib import Path

import pytest

from iwfcam4hermes import config_store


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.delenv("IWFCAM_CONFIG", raising=False)
    home = tmp_path / "hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def _example_count() -> int:
    return len(json.loads((Path(config_store.__file__).parent / "config.example.json")
                          .read_text(encoding="utf-8"))["devices"])


def test_user_config_path_uses_hermes_home(isolated_home):
    assert config_store.user_config_path() == isolated_home / "iwfcam4hermes" / "config.json"


def test_profile_home_maps_to_base_root(tmp_path, monkeypatch):
    base = tmp_path / "base"
    profile = base / "profiles" / "reverser"
    profile.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(profile))
    assert config_store.hermes_root() == base


def test_load_falls_back_to_example():
    data = config_store.load()
    assert isinstance(data["devices"], list)
    assert len(data["devices"]) == _example_count()


def test_ensure_user_config_writes_example_copy(isolated_home):
    path = config_store.ensure_user_config()
    assert path == config_store.user_config_path()
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["devices"]) == _example_count()


def test_add_list_update_remove_roundtrip():
    device, path = config_store.add_device({
        "id": "cam-test", "name": "Test", "type": "ziota",
        "host": "192.168.0.50", "port": 554,
    })
    assert path == config_store.user_config_path()
    assert device["id"] == "cam-test"
    assert device["channel"] == 0

    listed = {entry["id"]: entry for entry in config_store.list_devices()}
    assert "cam-test" in listed
    assert listed["cam-test"]["host"] == "192.168.0.50"

    updated, _ = config_store.update_device("cam-test", {"host": "192.168.0.60", "mock": True})
    assert updated["host"] == "192.168.0.60"
    assert updated["mock"] is True

    config_store.remove_device("cam-test")
    assert "cam-test" not in {entry["id"] for entry in config_store.list_devices()}


def test_add_duplicate_id_is_rejected(isolated_home):
    config_store.add_device({"id": "dup", "name": "A"})
    with pytest.raises(config_store.ConfigError):
        config_store.add_device({"id": "dup", "name": "B"})


@pytest.mark.parametrize("payload", [
    {"name": "ohne id"},
    {"id": "x"},
    {"id": "x", "name": "X", "type": "unknown"},
    {"id": "x", "name": "X", "port": 70000},
    {"id": "x", "name": "X", "unbekannt": 1},
    {"id": "x y", "name": "X"},
])
def test_invalid_devices_rejected(payload):
    with pytest.raises(config_store.ConfigError):
        config_store.add_device(payload)


def test_id_is_immutable_on_update():
    config_store.add_device({"id": "fixed", "name": "Fix"})
    with pytest.raises(config_store.ConfigError):
        config_store.update_device("fixed", {"id": "other"})


def test_save_writes_backup_and_never_example(isolated_home):
    config_store.add_device({"id": "one", "name": "Eins"})
    config_store.add_device({"id": "two", "name": "Zwei"})
    user = config_store.user_config_path()
    assert (user.parent / (user.name + ".bak")).is_file()
    assert (Path(config_store.__file__).parent / "config.example.json").is_file()
    # Beispiel darf nicht verändert sein
    example = json.loads((Path(config_store.__file__).parent / "config.example.json")
                         .read_text(encoding="utf-8"))
    assert "one" not in {d["id"] for d in example["devices"]}


def test_unknown_device_raises():
    with pytest.raises(config_store.ConfigError):
        config_store.get_device("missing")
    with pytest.raises(config_store.ConfigError):
        config_store.remove_device("missing")
