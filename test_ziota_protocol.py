"""Unit tests for the verified Z-IOT signaling protocol (no network)."""

import struct

import pytest

from ziota_adapter import (
    CMD_LOGIN,
    CMD_LOGIN_REPLY,
    FRAME_MAGIC,
    FRAME_TERMINATOR,
    ZIOTAdapter,
    build_login_frame,
    parse_frame,
    parse_login_reply,
    xor_bytes,
)


def test_xor_bytes():
    assert xor_bytes(b"\x00") == 0x00
    assert xor_bytes(b"\xff") == 0xFF
    assert xor_bytes(b"\x01\x02") == 0x03
    assert xor_bytes(FRAME_MAGIC) == 0x00


def test_login_frame_structure():
    frame = build_login_frame("ZIOTA_ABCDEFGHIJ", "TXW817_A_V1.0.11.84", sequence=1)
    assert frame[:2] == FRAME_MAGIC
    assert frame[-1:] == FRAME_TERMINATOR
    assert struct.unpack(">H", frame[2:4])[0] == CMD_LOGIN
    # checksum is the byte before the terminator
    assert xor_bytes(frame[:-2]) == frame[-2]


def test_login_frame_roundtrip():
    uid = "ZIOTA_ABCDEFGHIJ"
    fw = "TXW817_A_V1.0.11.84"
    frame = build_login_frame(uid, fw, sequence=7)
    parsed = parse_frame(frame)
    assert parsed is not None
    assert parsed["command"] == CMD_LOGIN
    assert parsed["sequence"] == 7
    assert parsed["uid"] == uid
    assert parsed["body"] == fw.encode()


def test_parse_login_reply_verified_layout():
    # Build a synthetic 0x8000 reply with the verified 94-byte payload.
    def make_body(relay, rport, mport, stun, sport, cloud, cport):
        b = struct.pack(">H", 1)
        b += relay.encode().ljust(20, b"\x00")
        b += struct.pack(">H", rport) + struct.pack(">H", mport)
        b += stun.encode().ljust(32, b"\x00")
        b += struct.pack(">H", sport)
        b += cloud.encode().ljust(32, b"\x00")
        b += struct.pack(">H", cport)
        b += bytes([xor_bytes(b)]) + b"\x0d"
        return b

    body = make_body("156.246.16.114", 554, 10000, "stun.gps555.net", 13478, "47.110.77.193", 8885)
    # parse_frame strips the trailing XOR + 0x0D, so feed it a full frame.
    header = FRAME_MAGIC + struct.pack(">H", CMD_LOGIN_REPLY)
    header += struct.pack(">H", 12 + len(body))
    header += struct.pack(">H", 1) + struct.pack(">H", 12)
    uid = b"ZIOTA_ABCDEF"
    full = header + uid + body
    parsed = parse_frame(full)
    reply = parse_login_reply(parsed)
    assert reply == {
        "login_sequence": 1,
        "relay_ip": "156.246.16.114",
        "relay_port": 554,
        "media_port": 10000,
        "stun_ip": "stun.gps555.net",
        "stun_port": 13478,
        "cloud_ip": "47.110.77.193",
        "cloud_port": 8885,
    }


def test_parse_rejects_malformed():
    assert parse_frame(b"") is None
    assert parse_frame(b"\x86\x86") is None
    assert parse_frame(b"\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x0d") is None


def test_sequence_increment():
    a = ZIOTAdapter(uid="TEST")
    assert a._sequence == 0
    assert a._next_sequence() == 1
    assert a._next_sequence() == 2
    a._sequence = 0xFFFF
    assert a._next_sequence() == 0  # wraps


def test_build_login_uses_sequence():
    a = ZIOTAdapter(uid="TEST", firmware="FW")
    f = a.build_login()
    assert parse_frame(f)["sequence"] == 1
    f2 = a.build_login()
    assert parse_frame(f2)["sequence"] == 2
