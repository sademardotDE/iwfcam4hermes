"""Loopback tests for MediaReceiver (no camera; synthetic RTP over UDP)."""

import socket
import struct
import time

import pytest

from media_receiver import MediaReceiver
from rtp_receiver import PT_JPEG, PT_PCMU


def make_rtp(payload, pt=PT_JPEG, marker=False, seq=1, ts=1000, ssrc=0x01020304):
    b0 = 0x80
    b1 = (0x80 if marker else 0) | (pt & 0x7F)
    return struct.pack(">BBHII", b0, b1, seq, ts, ssrc) + payload


def make_jpeg_payload(offset, kind, q, width, height, tables=b"", fragment=b""):
    p = bytes([0]) + offset.to_bytes(3, "big") + bytes([kind, q, width // 8, height // 8])
    if offset == 0:
        p += bytes([0, 0]) + struct.pack(">H", 128) + tables.ljust(128, b"\x00")
    return p + fragment


def _send(sock, port, data):
    sock.sendto(data, ("127.0.0.1", port))


def _wait(pred, timeout=6.0, step=0.02):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return None


def test_receiver_reassembles_frame_over_udp():
    tables = bytes(range(128))
    f1, f2 = b"AAAA", b"BBBBBB"
    rx = MediaReceiver()
    port = rx.start("127.0.0.1", 0)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            p1 = make_rtp(make_jpeg_payload(0, 0, 200, 80, 48, tables=tables, fragment=f1),
                          marker=False, ts=9001, seq=1)
            p2 = make_rtp(make_jpeg_payload(len(f1), 0, 200, 80, 48, fragment=f2),
                          marker=True, ts=9001, seq=2)
            _send(s, port, p1)
            _send(s, port, p2)
        finally:
            s.close()
        img = _wait(rx.latest_jpeg)
        assert img is not None, "no frame assembled"
        assert img.startswith(b"\xff\xd8") and img.endswith(b"\xff\xd9")
        assert f1 + f2 in img
        st = rx.stats()
        assert st["frames"] == 1
        assert st["width"] == 80 and st["height"] == 48
    finally:
        rx.stop()


def test_receiver_handles_audio():
    rx = MediaReceiver()
    port = rx.start("127.0.0.1", 0)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            _send(s, port, make_rtp(b"\x7f\x80" * 10, pt=PT_PCMU, ts=1234, seq=5))
        finally:
            s.close()
        got = _wait(lambda: rx.stats()["audio_packets"] >= 1)
        assert got
        ts, payload = rx.latest_audio()
        assert ts == 1234 and len(payload) == 20
        assert rx.stats()["frames"] == 0  # audio must not count as a frame
    finally:
        rx.stop()


def test_receiver_save_snapshot(tmp_path):
    tables = bytes(range(128))
    frag = b"\x10\x20\x30"
    rx = MediaReceiver()
    port = rx.start("127.0.0.1", 0)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            _send(s, port, make_rtp(make_jpeg_payload(0, 0, 200, 64, 64, tables=tables, fragment=frag),
                                    marker=True, ts=5555))
        finally:
            s.close()
        _wait(rx.latest_jpeg)
        out = tmp_path / "snap.jpg"
        saved = rx.save_snapshot(out)
        assert saved is not None and out.exists()
        assert out.read_bytes().startswith(b"\xff\xd8")
    finally:
        rx.stop()


def test_receiver_ignores_foreign_ssrc_after_first():
    tables = bytes(range(128))
    rx = MediaReceiver()
    port = rx.start("127.0.0.1", 0)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # first frame from ssrc A
            _send(s, port, make_rtp(make_jpeg_payload(0, 0, 200, 80, 48, tables=tables, fragment=b"AA"),
                                    marker=True, ts=1, ssrc=0xAAAA))
            _wait(rx.latest_jpeg)
            # frame from ssrc B must be ignored
            _send(s, port, make_rtp(make_jpeg_payload(0, 0, 200, 80, 48, tables=tables, fragment=b"BB"),
                                    marker=True, ts=2, ssrc=0xBBBB))
            time.sleep(0.8)
            assert rx.stats()["frames"] == 1
            assert rx.stats()["ssrc"] == 0xAAAA
        finally:
            s.close()
    finally:
        rx.stop()
