#!/usr/bin/env python3
"""Provision a ZIOTA (X5 / Z5) Wi-Fi camera over Bluetooth LE.

The camera advertises as ``ZIOTA_<device ID>`` and exposes a GATT provisioning
service. This tool scans for it, connects, and writes the provisioning packet
(Wi-Fi credentials + our server endpoint + UTC offset) in 20-byte GATT chunks.

Packet layout (all multi-byte fields big-endian), from the observed stock
protocol (open-ziot, MIT) and verified against the Android implementation:

  frame: 86 86 | u16(body_len + 5) | u16(sequence) | u16(body_len)
         body  | u8(XOR of all preceding) | 0x0D
  body : u16(command = 1)
         u8(len) ssid            (1..32 UTF-8 bytes)
         u8(len) password        (1..64 UTF-8 bytes)
         u8(len) "host:port"     (1..128 ASCII bytes)
         u16(utc offset minutes, signed)
         u32(registration code, random nonzero)

BLE must run on a host with a working BlueZ stack (bluetoothd + D-Bus). It does
NOT work inside the Hermes docker container. Nothing here is vendor code.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys

SERVICE_UUID = "36000001-0001-0002-0003-010203040506"
WRITE_UUID = "36000002-0001-0002-0003-010203040506"
NOTIFY_UUID = "36000003-0001-0002-0003-010203040506"

CHUNK = 20
CHUNK_DELAY = 0.15
NAME_PREFIX = "ZIOTA_"

_HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")


def _field(value: bytes, maximum: int, label: str) -> bytes:
    if not (1 <= len(value) <= maximum):
        raise ValueError(f"{label} must be 1..{maximum} UTF-8 bytes (got {len(value)})")
    return bytes([len(value)]) + value


def build_provisioning_packet(ssid: str, password: str, host: str, port: int,
                              offset_minutes: int, registration_code: int,
                              sequence: int = 1) -> bytes:
    """Build the BLE provisioning frame. Pure function (unit-testable)."""
    if not _HOST_RE.match(host) or len(host) > 100:
        raise ValueError("host must be a hostname or IPv4 address (no scheme/path), <=100 chars")
    if not (1 <= int(port) <= 65535):
        raise ValueError("port must be 1..65535")
    if not (-720 <= int(offset_minutes) <= 840):
        raise ValueError("UTC offset must be -720..840 minutes")
    if not (0 <= int(registration_code) <= 0xFFFFFFFF) or registration_code == 0:
        raise ValueError("registration_code must be a nonzero 32-bit value")
    if not (0 <= int(sequence) <= 0xFFFF):
        raise ValueError("sequence must be 0..65535")

    endpoint = f"{host}:{int(port)}".encode("ascii")

    body = b"\x00\x01"  # u16 command = 1
    body += _field(ssid.encode("utf-8"), 32, "ssid")
    body += _field(password.encode("utf-8"), 64, "password")
    body += _field(endpoint, 128, "endpoint")
    body += (int(offset_minutes) & 0xFFFF).to_bytes(2, "big")
    body += (int(registration_code) & 0xFFFFFFFF).to_bytes(4, "big")

    frame = b"\x86\x86"
    frame += (len(body) + 5).to_bytes(2, "big")
    frame += (int(sequence) & 0xFFFF).to_bytes(2, "big")
    frame += len(body).to_bytes(2, "big")
    frame += body
    xor = 0
    for b in frame:
        xor ^= b
    frame += bytes([xor, 0x0D])
    return frame


def chunks(data: bytes, size: int = CHUNK):
    for i in range(0, len(data), size):
        yield data[i:i + size]


async def _ble_provision(args) -> int:
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        print("bleak is not installed. On the Linux host run:  pip install bleak", file=sys.stderr)
        return 2

    packet = build_provisioning_packet(
        ssid=args.ssid, password=args.password, host=args.server_ip,
        port=args.server_port, offset_minutes=args.utc_offset,
        registration_code=args.registration or (int.from_bytes(os.urandom(4), "big") or 1),
        sequence=args.sequence,
    )
    print(f"packet: {len(packet)} bytes -> {packet.hex()}", flush=True)

    address = args.address
    if not address:
        print(f"scanning {args.scan_timeout:.0f}s for {NAME_PREFIX}* ...", flush=True)
        devices = await BleakScanner.discover(timeout=args.scan_timeout)
        cand = [d for d in devices if (d.name or "").upper().startswith(NAME_PREFIX)]
        if args.name:
            exact = [d for d in cand if (d.name or "").upper() == args.name.upper()]
            if not exact:
                print(f"{args.name} not present. Matches: {[d.name for d in cand]}", file=sys.stderr)
                return 1
            cand = exact
        if not cand:
            print(f"no {NAME_PREFIX}* device found. Camera on & in pairing range? "
                  f"Devices seen: {[d.name for d in devices if d.name]}", file=sys.stderr)
            return 1
        # prefer strongest RSSI when available
        cand.sort(key=lambda d: getattr(d, "rssi", -999), reverse=True)
        address = cand[0].address
        print(f"using {cand[0].name} [{address}]", flush=True)

    print(f"connecting to {address} ...", flush=True)
    async with BleakClient(address, timeout=args.connect_timeout) as client:
        if not client.is_connected:
            print("connection failed", file=sys.stderr)
            return 1
        print("connected; subscribing notify + writing in 20-byte chunks", flush=True)

        def _on_notify(_sender, data: bytearray):
            if data:
                print(f"notify: {bytes(data).hex()}", flush=True)

        try:
            await client.start_notify(NOTIFY_UUID, _on_notify)
        except Exception as exc:  # notify optional on some firmware
            print(f"(notify subscribe skipped: {exc})", flush=True)

        for i, chunk in enumerate(chunks(packet)):
            await client.write_gatt_char(WRITE_UUID, chunk, response=True)
            print(f"  chunk {i + 1}: {chunk.hex()}", flush=True)
            await asyncio.sleep(args.chunk_delay)

        await asyncio.sleep(1.0)
        try:
            await client.stop_notify(NOTIFY_UUID)
        except Exception:
            pass

    print("done. The camera should now join your Wi-Fi and connect to "
          f"{args.server_ip}:{args.server_port}. Verify on your receiver.", flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Provision a ZIOTA camera over BLE")
    ap.add_argument("--ssid", required=True, help="2.4 GHz Wi-Fi SSID")
    ap.add_argument("--password", required=True, help="Wi-Fi password")
    ap.add_argument("--server-ip", required=True, help="IP/host of YOUR receiver (LAN IPv4)")
    ap.add_argument("--server-port", type=int, default=8882)
    ap.add_argument("--utc-offset", type=int, default=60, help="UTC offset in minutes (e.g. 60/120)")
    ap.add_argument("--address", default=None, help="BLE MAC/UUID (skip scan)")
    ap.add_argument("--name", default=None, help="exact BLE name, e.g. ZIOTA_196758286858")
    ap.add_argument("--scan-timeout", type=float, default=10.0)
    ap.add_argument("--connect-timeout", type=float, default=20.0)
    ap.add_argument("--chunk-delay", type=float, default=CHUNK_DELAY)
    ap.add_argument("--sequence", type=int, default=1)
    ap.add_argument("--registration", type=int, default=0, help="override registration code")
    args = ap.parse_args(argv)

    try:
        return asyncio.run(_ble_provision(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
