"""End-to-end test of the self-hosted receiver with a simulated camera.

No real hardware: a simulated client logs in over TCP, requests time, and streams
synthetic RTP/JPEG to the announced media port; the server must decode a frame.
Also verifies the STUN responder and the login-reply layout.
"""

import socket
import struct
import time

import pytest

from ziot_receiver import (
    CMD_LOGIN_REPLY,
    CMD_TIME_REPLY,
    ZiotReceiverServer,
    login_reply_body,
)
from ziota_adapter import build_frame, build_login_frame, parse_frame, parse_login_reply
from rtp_receiver import PT_PCMU


UID = "ZIOTA_SIMCAM0001"
FW = "TXW817_A_V1.0.11.84"


def read_frame(conn, timeout=3.0):
    conn.settimeout(timeout)
    buf = b""
    while True:
        while len(buf) < 10:
            chunk = conn.recv(4096)
            if not chunk:
                raise RuntimeError("connection closed")
            buf += chunk
        cmd, length, cseq, uidlen = struct.unpack(">HHHH", buf[2:10])
        total = length + 12
        while len(buf) < total:
            chunk = conn.recv(4096)
            if not chunk:
                raise RuntimeError("connection closed mid-frame")
            buf += chunk
        return buf[:total]


def make_rtp(payload, pt, marker, seq, ts, ssrc=0x0A0B0C0D):
    return struct.pack(">BBHII", 0x80, (0x80 if marker else 0) | (pt & 0x7F),
                       seq, ts, ssrc) + payload


def make_jpeg_payload(offset, frag, width=80, height=48, tables=None):
    tables = tables or bytes(range(128))
    p = bytes([0]) + offset.to_bytes(3, "big") + bytes([0, 200, width // 8, height // 8])
    if offset == 0:
        p += bytes([0, 0]) + struct.pack(">H", 128) + tables.ljust(128, b"\x00")
    return p + frag


def test_login_reply_layout_roundtrip():
    body = login_reply_body(7, "203.0.113.9", 10000, "203.0.113.9", 13478, "203.0.113.9", 0)
    frame = {"command": CMD_LOGIN_REPLY, "sequence": 1, "uid": UID, "body": body, "raw": b""}
    r = parse_login_reply(frame)
    assert r["login_sequence"] == 7
    assert r["relay_ip"] == "203.0.113.9"
    assert r["media_port"] == 10000
    assert r["stun_ip"] == "203.0.113.9"
    assert r["stun_port"] == 13478


def test_full_flow_simulated_camera():
    server = ZiotReceiverServer(host="127.0.0.1", public_ip="127.0.0.1")
    info = server.start()
    try:
        conn = socket.create_connection(("127.0.0.1", info["signaling_port"]), timeout=3)
        try:
            # login
            conn.sendall(build_login_frame(UID, FW, 1))
            reply = parse_frame(read_frame(conn))
            assert reply is not None and reply["command"] == CMD_LOGIN_REPLY
            r = parse_login_reply(reply)
            # Pro Kamera wird ein eigener UDP-Media-Port vergeben.
            media_port = r["media_port"]
            assert media_port > 0
            assert server.media_for(UID).stats()["port"] == media_port

            # time request
            conn.sendall(build_frame(0x21, 2, UID))
            t = parse_frame(read_frame(conn))
            assert t is not None and t["command"] == CMD_TIME_REPLY
            assert abs(struct.unpack(">I", t["body"][:4])[0] - int(time.time())) <= 5
        finally:
            conn.close()

        # stream a JPEG frame to the announced media port
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            f1, f2 = b"AAAA", b"BBBBBB"
            p1 = make_rtp(make_jpeg_payload(0, f1), 26, False, 1, 4242)
            p2 = make_rtp(make_jpeg_payload(len(f1), f2), 26, True, 2, 4242)
            s.sendto(p1, ("127.0.0.1", media_port))
            s.sendto(p2, ("127.0.0.1", media_port))
            # one audio packet
            s.sendto(make_rtp(b"\x7f\x80" * 8, PT_PCMU, False, 3, 4242), ("127.0.0.1", media_port))
        finally:
            s.close()

        # Bild *und* Audio-Zähler abwarten: die UDP-Pakete werden vom
        # Empfänger-Thread in Reihenfolge verarbeitet, das letzte kann also
        # noch in der Queue liegen, wenn der Frame schon sichtbar ist.
        img = None
        st = {}
        end = time.time() + 3
        while time.time() < end:
            img = server.media.latest_jpeg()
            st = server.media.stats()
            if img and st["frames"] == 1 and st["audio_packets"] == 1:
                break
            time.sleep(0.02)
        assert img is not None, "server did not decode a frame"
        assert img.startswith(b"\xff\xd8") and img.endswith(b"\xff\xd9")
        assert f1 + f2 in img
        assert st["frames"] == 1 and st["audio_packets"] == 1
    finally:
        server.stop()


def test_two_cameras_get_separate_media_ports_and_decode():
    """Mehrkamera: zwei Logins erhalten unterschiedliche UDP-Ports und Frames."""
    server = ZiotReceiverServer(host="127.0.0.1", public_ip="127.0.0.1")
    info = server.start()
    uid_a, uid_b = "ZIOTA_CAMAAAAA01", "ZIOTA_CAMBBBBB02"
    try:
        ports = {}
        for uid in (uid_a, uid_b):
            conn = socket.create_connection(("127.0.0.1", info["signaling_port"]), timeout=3)
            try:
                conn.sendall(build_login_frame(uid, FW, 1))
                reply = parse_frame(read_frame(conn))
                assert reply is not None and reply["command"] == CMD_LOGIN_REPLY
                ports[uid] = parse_login_reply(reply)["media_port"]
                conn.sendall(build_frame(0x21, 2, uid))
                read_frame(conn)
            finally:
                conn.close()

        assert ports[uid_a] != ports[uid_b]
        assert len(server.cameras()) == 2

        # Jede Kamera streamt einen eigenen Frame (eigene SSRC/Port).
        for index, uid in enumerate((uid_a, uid_b)):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                ssrc = 0x1000 + index
                f1, f2 = b"AAAA", b"BBBBBB"
                sock.sendto(make_rtp(make_jpeg_payload(0, f1), 26, False, 1, 4242,
                                     ssrc=ssrc), ("127.0.0.1", ports[uid]))
                sock.sendto(make_rtp(make_jpeg_payload(len(f1), f2), 26, True, 2, 4242,
                                     ssrc=ssrc), ("127.0.0.1", ports[uid]))
            finally:
                sock.close()

        deadline = time.time() + 3
        while time.time() < deadline:
            medias = [server.media_for(uid) for uid in (uid_a, uid_b)]
            if all(m is not None and m.latest_jpeg() for m in medias):
                break
            time.sleep(0.02)
        for uid in (uid_a, uid_b):
            media = server.media_for(uid)
            assert media is not None and media.latest_jpeg() is not None, uid
            assert media.stats()["frames"] == 1, uid
        stats = {camera["uid"]: camera for camera in server.cameras()}
        assert stats[uid_a]["port"] != stats[uid_b]["port"]
    finally:
        server.stop()


def test_stun_responder():
    server = ZiotReceiverServer(host="127.0.0.1", public_ip="127.0.0.1")
    info = server.start()
    try:
        txid = b"\x11\x22\x33\x44\x55\x66\x77\x88\x99\xaa\xbb\xcc"
        req = struct.pack(">HH", 0x0001, 0) + b"\x21\x12\xa4\x42" + txid
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        try:
            s.sendto(req, ("127.0.0.1", info["stun_port"]))
            resp, _ = s.recvfrom(2048)
            local_port = s.getsockname()[1]
        finally:
            s.close()
        assert resp[0:2] == b"\x01\x01"  # binding success
        assert resp[8:20] == txid
        # XOR-MAPPED-ADDRESS at offset 20
        attr_type, attr_len = struct.unpack(">HH", resp[20:24])
        assert attr_type == 0x0020 and attr_len == 8
        xport = struct.unpack(">H", resp[26:28])[0] ^ 0x2112
        assert xport == local_port
    finally:
        server.stop()


def test_plugin_cli_signaling_login(capsys):
    import argparse

    from plugin import _cmd_signaling_login

    server = ZiotReceiverServer(host="127.0.0.1", public_ip="127.0.0.1")
    info = server.start()
    try:
        args = argparse.Namespace(uid=UID, host="127.0.0.1",
                                  port=info["signaling_port"], firmware=FW, timeout=5.0)
        rc = _cmd_signaling_login(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert '"media_port"' in out
        media_port = server.media_for(UID).stats()["port"]
        assert media_port > 0 and str(media_port) in out
    finally:
        server.stop()
