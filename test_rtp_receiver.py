"""Unit tests for RTP parsing and RFC 2435 JPEG reassembly (no network/camera)."""

import struct

import pytest

from rtp_receiver import (
    JpegRtpReceiver,
    PT_JPEG,
    PT_PCMU,
    parse_rtp,
)


def make_rtp(payload, pt=PT_JPEG, marker=False, seq=1, ts=1000, ssrc=0x11223344,
             csrc=0, padding=b"", ext=None):
    b0 = 0x80 | (csrc & 0x0F)
    if ext is not None:
        b0 |= 0x10
    if padding:
        b0 |= 0x20
    b1 = (0x80 if marker else 0) | (pt & 0x7F)
    hdr = struct.pack(">BBHII", b0, b1, seq, ts, ssrc)
    hdr += b"\x00" * (4 * csrc)
    if ext is not None:
        hdr += struct.pack(">HH", 0xBEDE, len(ext) // 4) + ext
    body = payload
    if padding:
        body += padding
        body += bytes([len(padding) + 1])
    return hdr + body


def make_jpeg_payload(offset, kind, q, width, height, tables=b"", fragment=b"", restart=None):
    p = bytes([0]) + offset.to_bytes(3, "big") + bytes([kind, q, width // 8, height // 8])
    if restart is not None:
        p = p[:4] + bytes([kind | 64, q, width // 8, height // 8]) + struct.pack(">HH", restart, 0) + p[8:]
    if offset == 0:
        p += bytes([0, 0]) + struct.pack(">H", 128) + tables.ljust(128, b"\x00")
    return p + fragment


def test_parse_rtp_basic():
    pkt = parse_rtp(make_rtp(b"hello", pt=PT_PCMU, seq=7, ts=42, ssrc=9))
    assert pkt is not None
    assert pkt.version == 2
    assert pkt.payload_type == PT_PCMU
    assert pkt.sequence == 7
    assert pkt.timestamp == 42
    assert pkt.ssrc == 9
    assert pkt.payload == b"hello"


def test_parse_rtp_padding():
    pkt = parse_rtp(make_rtp(b"data", padding=b"\x00\x00"))
    assert pkt is not None
    assert pkt.padding is True
    assert pkt.payload == b"data"


def test_parse_rtp_csrc_and_extension():
    pkt = parse_rtp(make_rtp(b"xy", csrc=2, ext=b"\x01\x02\x03\x04"))
    assert pkt is not None
    assert pkt.payload == b"xy"


def test_parse_rtp_rejects_garbage():
    assert parse_rtp(b"") is None
    assert parse_rtp(b"\x00" * 12) is None  # version 0
    assert parse_rtp(b"\x80\x1a\x00\x01") is None  # too short


def test_jpeg_single_packet_frame():
    tables = bytes(range(128))
    frag = b"\x11\x22\x33\x44"
    payload = make_jpeg_payload(0, 0, 200, 80, 48, tables=tables, fragment=frag)
    pkt = make_rtp(payload, marker=True, ts=555)
    r = JpegRtpReceiver()
    img = r.receive(pkt)
    assert img is not None
    assert img.startswith(b"\xff\xd8")
    assert img.endswith(b"\xff\xd9")
    assert frag in img
    assert r.width == 80 and r.height == 48
    assert r.frames == 1


def test_jpeg_two_fragment_frame():
    tables = bytes(range(128))
    f1 = b"AAAA"
    f2 = b"BBBBBB"
    p1 = make_rtp(make_jpeg_payload(0, 0, 200, 80, 48, tables=tables, fragment=f1),
                  marker=False, ts=777, seq=1)
    p2 = make_rtp(make_jpeg_payload(len(f1), 0, 200, 80, 48, fragment=f2),
                  marker=True, ts=777, seq=2)
    r = JpegRtpReceiver()
    assert r.receive(p1) is None  # not complete yet
    img = r.receive(p2)
    assert img is not None
    assert f1 + f2 in img
    assert r.frames == 1


def test_jpeg_ignores_audio_pt():
    r = JpegRtpReceiver()
    assert r.receive(make_rtp(b"abc", pt=PT_PCMU)) is None


def test_jpeg_drops_incomplete_on_new_timestamp():
    tables = bytes(range(128))
    p1 = make_rtp(make_jpeg_payload(0, 0, 200, 80, 48, tables=tables, fragment=b"XX"),
                  marker=False, ts=1000)
    r = JpegRtpReceiver()
    assert r.receive(p1) is None
    # new timestamp, complete frame
    frag = b"ZZZZ"
    p2 = make_rtp(make_jpeg_payload(0, 0, 200, 80, 48, tables=tables, fragment=frag),
                  marker=True, ts=2000)
    img = r.receive(p2)
    assert img is not None and frag in img
    assert r.dropped == 1


def test_default_dht_bundled():
    from rtp_receiver import default_dht
    d = default_dht()
    assert d[:2] == b"\xff\xc4" and len(d) > 100


def test_frame_includes_default_dht():
    tables = bytes(range(128))
    frag = b"\x01\x02\x03"
    payload = make_jpeg_payload(0, 0, 200, 80, 48, tables=tables, fragment=frag)
    r = JpegRtpReceiver()  # no explicit dht -> bundled standard tables
    img = r.receive(make_rtp(payload, marker=True, ts=99))
    assert img is not None
    assert b"\xff\xc4" in img  # DHT present in assembled JPEG
