#!/usr/bin/env python3
"""Tests für die WLAN-Provisionierung (provision.py) — ohne echte Hardware/WLAN."""

import pytest

from iwfcam4hermes import provision

ACK_HEX = "86860015000100108001000c313936373538323836383538840d"


def test_build_packet_format():
    packet = provision.build_provisioning_packet(
        ssid="cccp4ever", password="geheim!", host="192.168.0.4", port=8882,
        offset_minutes=60, registration_code=0x5A17C0DE, sequence=1,
    )
    assert packet[:2] == b"\x86\x86"
    assert packet[-1] == 0x0D
    body_len = int.from_bytes(packet[6:8], "big")
    assert len(packet) == 8 + body_len + 2
    assert b"cccp4ever" in packet
    assert b"192.168.0.4:8882" in packet
    # XOR-Checksumme über alle Bytes vor XOR+0D
    xor = 0
    for byte in packet[:-2]:
        xor ^= byte
    assert xor == packet[-2]


def test_parse_ack_real_response():
    ack = provision.parse_ack(bytes.fromhex(ACK_HEX))
    assert ack is not None
    assert ack["ack"] is True
    assert ack["command"] == 0x8001
    assert ack["uid"] == "196758286858"


@pytest.mark.parametrize("data", [b"", b"garbage", b"\x86\x86\x00", b"\x86\x86\x00\x05\x00\x01\x00\x01\x80"])
def test_parse_ack_invalid(data):
    assert provision.parse_ack(data) is None


def _patch_host(monkeypatch, *, ack=bytes.fromhex(ACK_HEX), connect_ok=True):
    calls = {"restore": 0, "connect": 0, "send": 0}

    monkeypatch.setattr(provision, "current_wifi", lambda: {
        "connection": "cccp4ever_5G", "ssid": "cccp4ever_5G", "ipv4": "192.168.0.4"})

    def fake_connect(ssid, profile=provision.DEFAULT_PROFILE):
        calls["connect"] += 1
        return {"ok": connect_ok, "message": "connected" if connect_ok else "failed"}

    def fake_restore(connection, profile=provision.DEFAULT_PROFILE):
        calls["restore"] += 1
        return {"ok": True, "message": "restored"}

    def fake_send(host, port, packet, timeout=8.0):
        calls["send"] += 1
        return ack

    monkeypatch.setattr(provision, "_connect_ap", fake_connect)
    monkeypatch.setattr(provision, "_restore", fake_restore)
    monkeypatch.setattr(provision, "_send_packet", fake_send)
    monkeypatch.setattr(provision, "_wait_for_gateway", lambda timeout=20: "192.168.1.1")
    monkeypatch.setattr(provision, "_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr(provision, "nearby_networks", lambda **kw: [])
    return calls


def test_provision_success(monkeypatch):
    calls = _patch_host(monkeypatch)
    result = provision.provision(
        camera_ssid="ZIOTA_196758286858", ssid="cccp4ever", password="geheim!",
        server_ip="192.168.0.4", server_port=8882, utc_offset=60,
    )
    assert result["ok"] is True
    assert result["camera_uid"] == "196758286858"
    assert result["ssid"] == "cccp4ever"
    assert result["server"] == "192.168.0.4:8882"
    assert calls["connect"] == 1 and calls["send"] == 1 and calls["restore"] == 1
    steps = [step["step"] for step in result["steps"]]
    assert steps == ["current", "connect-camera-ap", "gateway", "send", "response", "restore"]


def test_provision_without_ack_restores_wifi(monkeypatch):
    calls = _patch_host(monkeypatch, ack=b"")
    result = provision.provision(
        camera_ssid="ZIOTA_196758286858", ssid="cccp4ever", password="geheim!",
        server_ip="192.168.0.4",
    )
    assert result["ok"] is False
    assert "bestätigt" in result["error"]
    assert calls["restore"] == 1


def test_provision_rejects_invalid_input(monkeypatch):
    calls = _patch_host(monkeypatch)
    assert provision.provision(camera_ssid="FRITZBOX", ssid="x", password="y",
                               server_ip="192.168.0.4")["ok"] is False
    assert provision.provision(camera_ssid="ZIOTA_1", ssid="", password="y",
                               server_ip="192.168.0.4")["ok"] is False
    assert provision.provision(camera_ssid="ZIOTA_1", ssid="x", password="y",
                               server_ip="")["ok"] is False
    assert calls["connect"] == 0


def test_provision_connect_failure(monkeypatch):
    calls = _patch_host(monkeypatch, connect_ok=False)
    result = provision.provision(camera_ssid="ZIOTA_196758286858", ssid="cccp4ever",
                                 password="geheim!", server_ip="192.168.0.4")
    assert result["ok"] is False
    assert "Kamera-AP" in result["error"]
    assert calls["restore"] == 0


def test_status_shape(monkeypatch):
    monkeypatch.setattr(provision, "current_wifi", lambda: {
        "connection": "home", "ssid": "home", "ipv4": "192.168.0.4"})
    monkeypatch.setattr(provision, "nearby_networks", lambda **kw: [
        {"ssid": "ZIOTA_123", "signal": 80, "security": None, "freq": 2412,
         "band": "2.4 GHz", "is_camera_ap": True},
        {"ssid": "home", "signal": 90, "security": "WPA2", "freq": 2437,
         "band": "2.4 GHz", "is_camera_ap": False},
    ])
    result = provision.status()
    assert result["ok"] is True
    assert result["current"]["ipv4"] == "192.168.0.4"
    assert [n["ssid"] for n in result["camera_aps"]] == ["ZIOTA_123"]
