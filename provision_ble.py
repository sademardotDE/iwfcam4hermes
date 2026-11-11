#!/usr/bin/env python3
"""Provision a ZIOTA Wi-Fi camera over Bluetooth LE.

The camera advertises as ``ZIOTA_<device ID>``. This tool scans for it, connects,
discovers writable/notify characteristics (firmware variants differ — see
``ble_dump.py``), and writes the provisioning packet (Wi-Fi credentials + our
server endpoint + UTC offset) in 20-byte GATT chunks.

Security: the packet contains the Wi-Fi password. This tool never prints the
packet or chunk bytes, so credentials do not leak into terminal scrollback/logs.

Packet layout (big-endian), from the observed stock protocol (open-ziot, MIT):

  frame: 86 86 | u16(body_len + 5) | u16(sequence) | u16(body_len)
         body  | u8(XOR of all preceding) | 0x0D
  body : u16(command = 1)
         u8(len) ssid            (1..32 UTF-8 bytes)
         u8(len) password        (1..64 UTF-8 bytes)
         u8(len) "host:port"     (1..128 ASCII bytes)
         u16(utc offset minutes, signed)
         u32(registration code, random nonzero)

BLE must run on a host with BlueZ + D-Bus; it does NOT work in the Hermes docker
container. Nothing here is vendor code.
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


def _find_characteristics(client, write_uuid=None, notify_uuid=None):
    """Return (write_uuid, write_response, notify_uuid) discovered from the client."""
    services = client.services
    write = write_uuid
    write_response = True
    notify = notify_uuid

    if write is None:
        cands = []
        for svc in services:
            for ch in svc.characteristics:
                props = ch.properties
                if "write" in props or "write-without-response" in props:
                    cands.append((svc.uuid, ch.uuid, props))
        if cands:
            cands.sort(key=lambda t: (not t[0].startswith("3600"),))
            _, write, props = cands[0]
            write_response = "write" in props

    if notify is None:
        for svc in services:
            for ch in svc.characteristics:
                if "notify" in ch.properties or "indicate" in ch.properties:
                    notify = ch.uuid
                    break
            if notify:
                break

    return write, write_response, notify


def _print_tree(client) -> None:
    for svc in client.services:
        print(f"  service {svc.uuid}")
        for ch in svc.characteristics:
            print(f"    char {ch.uuid}  props=[{','.join(ch.properties)}]")


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
    print(f"packet: {len(packet)} bytes (contents withheld: contains Wi-Fi password)", flush=True)

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
            print(f"no {NAME_PREFIX}* device found. Devices seen: "
                  f"{[d.name for d in devices if d.name]}", file=sys.stderr)
            return 1
        cand.sort(key=lambda d: getattr(d, "rssi", -999), reverse=True)
        address = cand[0].address
        print(f"using {cand[0].name} [{address}]", flush=True)

    print(f"connecting to {address} ...", flush=True)
    async with BleakClient(address, timeout=args.connect_timeout) as client:
        if not client.is_connected:
            print("connection failed", file=sys.stderr)
            return 1

        write, write_response, notify = _find_characteristics(
            client, args.write_uuid, args.notify_uuid)
        if write is None:
            print("No writable characteristic found on this device. GATT tree:", file=sys.stderr)
            _print_tree(client)
            print("\nRun  python3 ble_dump.py  and share the output to map UUIDs.",
                  file=sys.stderr)
            return 3
        print(f"write char: {write} (response={write_response})", flush=True)
        print(f"notify char: {notify or '(none)'}", flush=True)

        if notify:
            def _on_notify(_sender, data: bytearray):
                if data:
                    print(f"notify: {len(data)} bytes", flush=True)
            try:
                await client.start_notify(notify, _on_notify)
            except Exception as exc:
                print(f"(notify subscribe skipped: {exc})", flush=True)

        total = (len(packet) + CHUNK - 1) // CHUNK
        for i, chunk in enumerate(chunks(packet)):
            await client.write_gatt_char(write, chunk, response=write_response)
            print(f"  chunk {i + 1}/{total}: {len(chunk)} bytes", flush=True)
            await asyncio.sleep(args.chunk_delay)

        await asyncio.sleep(1.0)
        if notify:
            try:
                await client.stop_notify(notify)
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
    ap.add_argument("--write-uuid", default=None, help="override write characteristic UUID")
    ap.add_argument("--notify-uuid", default=None, help="override notify characteristic UUID")
    ap.add_argument("--scan-timeout", type=float, default=10.0)
    ap.add_argument("--connect-timeout", type=float, default=20.0)
    ap.add_argument("--chunk-delay", type=float, default=CHUNK_DELAY)
    ap.add_argument("--sequence", type=int, default=1)
    ap.add_argument("--registration", type=int, default=0, help="override registration code")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and print the packet only (no Bluetooth)")
    args = ap.parse_args(argv)

    if args.dry_run:
        reg = args.registration or (int.from_bytes(os.urandom(4), "big") or 1)
        packet = build_provisioning_packet(
            ssid=args.ssid, password=args.password, host=args.server_ip,
            port=args.server_port, offset_minutes=args.utc_offset,
            registration_code=reg, sequence=args.sequence,
        )
        print(f"packet: {len(packet)} bytes")
        print(f"hex: {packet.hex()}")
        body_len = int.from_bytes(packet[6:8], "big")
        print(f"body_len={body_len} seq={int.from_bytes(packet[4:6],'big')} "
              f"endpoint={args.server_ip}:{args.server_port} utc_offset={args.utc_offset} reg=0x{reg:08x}")
        return 0

    try:
        return asyncio.run(_ble_provision(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
