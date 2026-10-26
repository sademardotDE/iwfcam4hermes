#!/usr/bin/env python3
"""Minimal STUN client (RFC 5389)."""

import socket
import struct
import random


STUN_MAGIC = 0x2112A442


def stun_binding(server: str = "stun.gps555.net", port: int = 13478, timeout: float = 5.0):
    """Perform a STUN binding request and return (ip, port) or None."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)

    # Build STUN binding request
    msg_type = 0x0001  # Binding Request
    msg_len = 0
    txn_id = bytes(random.getrandbits(8) for _ in range(12))
    header = struct.pack("!HHI", msg_type, msg_len, STUN_MAGIC) + txn_id

    try:
        sock.sendto(header, (server, port))
        data, _ = sock.recvfrom(1024)
    except Exception as e:
        return None, str(e)
    finally:
        sock.close()

    # Parse response
    if len(data) < 20:
        return None, "response too short"
    msg_type, msg_len, magic = struct.unpack("!HHI", data[:8])
    if magic != STUN_MAGIC:
        return None, "bad magic cookie"
    txn_id_resp = data[8:20]
    if txn_id_resp != txn_id:
        return None, "transaction id mismatch"

    # Parse attributes
    offset = 20
    while offset < len(data):
        if offset + 4 > len(data):
            break
        attr_type, attr_len = struct.unpack("!HH", data[offset:offset + 4])
        offset += 4
        attr_value = data[offset:offset + attr_len]
        offset += attr_len
        # Pad to 4-byte boundary
        if attr_len % 4:
            offset += 4 - (attr_len % 4)

        # XOR-MAPPED-ADDRESS (0x0020)
        if attr_type == 0x0020:
            family = attr_value[1]
            if family == 0x01:  # IPv4
                xport = struct.unpack("!H", attr_value[2:4])[0] ^ (STUN_MAGIC >> 16)
                xip = struct.unpack("!I", attr_value[4:8])[0] ^ STUN_MAGIC
                ip = socket.inet_ntoa(struct.pack("!I", xip))
                return (ip, xport), None
        # MAPPED-ADDRESS (0x0001)
        elif attr_type == 0x0001:
            family = attr_value[1]
            if family == 0x01:
                port = struct.unpack("!H", attr_value[2:4])[0]
                ip = socket.inet_ntoa(attr_value[4:8])
                return (ip, port), None

    return None, "no mapped address found"


if __name__ == "__main__":
    result, err = stun_binding()
    if result:
        print(f"Public address: {result[0]}:{result[1]}")
    else:
        print(f"STUN failed: {err}")
