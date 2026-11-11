"""Unit tests for the BLE provisioning packet builder (no Bluetooth needed)."""

import pytest

from provision_ble import build_provisioning_packet


def _xor(data: bytes) -> int:
    x = 0
    for b in data:
        x ^= b
    return x


def parse_body(body: bytes) -> dict:
    i = 0
    cmd = int.from_bytes(body[i:i + 2], "big"); i += 2
    out = {"command": cmd}
    for key in ("ssid", "password", "endpoint"):
        n = body[i]; i += 1
        out[key] = body[i:i + n]; i += n
    out["offset"] = int.from_bytes(body[i:i + 2], "big"); i += 2
    out["reg"] = int.from_bytes(body[i:i + 4], "big"); i += 4
    assert i == len(body), "trailing bytes in body"
    return out


def test_frame_structure_and_roundtrip():
    pkt = build_provisioning_packet(
        ssid="MyNet", password="s3cret!", host="192.168.0.10", port=8882,
        offset_minutes=120, registration_code=0x01020304, sequence=7,
    )
    assert pkt[0:2] == b"\x86\x86"
    assert pkt[-1] == 0x0D
    assert _xor(pkt[:-2]) == pkt[-2]

    body_len = int.from_bytes(pkt[6:8], "big")
    assert int.from_bytes(pkt[2:4], "big") == body_len + 5
    assert int.from_bytes(pkt[4:6], "big") == 7
    # frame = 8-byte header + body + xor + 0x0D
    assert len(pkt) == 8 + body_len + 2

    body = pkt[8:8 + body_len]
    b = parse_body(body)
    assert b["command"] == 1
    assert b["ssid"] == b"MyNet"
    assert b["password"] == b"s3cret!"
    assert b["endpoint"] == b"192.168.0.10:8882"
    assert b["offset"] == 120
    assert b["reg"] == 0x01020304


def test_negative_offset_encoded_twos_complement():
    pkt = build_provisioning_packet("n", "p", "h", 1, -300, 1, 1)
    body_len = int.from_bytes(pkt[6:8], "big")
    b = parse_body(pkt[8:8 + body_len])
    assert b["offset"] == (65536 - 300)


def test_utf8_ssid_multibyte():
    pkt = build_provisioning_packet("Café", "p", "h", 1, 0, 1, 1)
    body_len = int.from_bytes(pkt[6:8], "big")
    b = parse_body(pkt[8:8 + body_len])
    assert b["ssid"] == "Café".encode("utf-8")  # 5 bytes, length prefix is byte length


@pytest.mark.parametrize("kwargs", [
    dict(ssid="", password="p", host="h", port=1, offset_minutes=0, registration_code=1),
    dict(ssid="x" * 33, password="p", host="h", port=1, offset_minutes=0, registration_code=1),
    dict(ssid="s", password="", host="h", port=1, offset_minutes=0, registration_code=1),
    dict(ssid="s", password="p", host="http://x", port=1, offset_minutes=0, registration_code=1),
    dict(ssid="s", password="p", host="h", port=0, offset_minutes=0, registration_code=1),
    dict(ssid="s", password="p", host="h", port=70000, offset_minutes=0, registration_code=1),
    dict(ssid="s", password="p", host="h", port=1, offset_minutes=-999, registration_code=1),
    dict(ssid="s", password="p", host="h", port=1, offset_minutes=0, registration_code=0),
])
def test_validation_errors(kwargs):
    with pytest.raises(ValueError):
        build_provisioning_packet(**kwargs)
