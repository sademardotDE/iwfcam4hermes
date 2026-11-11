#!/usr/bin/env python3
"""Dump the BLE GATT tree of a ZIOTA camera (find the real service/characteristic UUIDs).

Run this on the Linux host with working Bluetooth (BlueZ + D-Bus). It scans for
ZIOTA_* (or uses --address/--name), connects, and prints every service and
characteristic with its UUID, handle and properties. No secrets are used or shown.

Examples:
    python3 ble_dump.py
    python3 ble_dump.py --name ZIOTA_196758286858
    python3 ble_dump.py --address 18:5F:28:44:26:C6
"""

from __future__ import annotations

import argparse
import asyncio
import sys

NAME_PREFIX = "ZIOTA_"


async def _dump(args) -> int:
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        print("bleak not installed:  pip install bleak", file=sys.stderr)
        return 2

    address = args.address
    name = args.name
    if not address:
        print(f"scanning {args.scan_timeout:.0f}s for {NAME_PREFIX}* ...", flush=True)
        devices = await BleakScanner.discover(timeout=args.scan_timeout)
        zi = [d for d in devices if (d.name or "").upper().startswith(NAME_PREFIX)]
        if name:
            zi = [d for d in zi if (d.name or "").upper() == name.upper()]
        if not zi:
            print(f"no match. devices: {[(d.name, d.address) for d in devices if d.name]}",
                  file=sys.stderr)
            return 1
        zi.sort(key=lambda d: getattr(d, "rssi", -999), reverse=True)
        address = zi[0].address
        name = zi[0].name
        print(f"using {name} [{address}]", flush=True)

    print(f"connecting to {address} ...", flush=True)
    async with BleakClient(address, timeout=args.connect_timeout) as client:
        if not client.is_connected:
            print("connection failed", file=sys.stderr)
            return 1
        print(f"connected: {address}  (mtu={getattr(client, 'mtu_size', '?')})\n", flush=True)

        services = client.services
        for svc in services:
            print(f"service {svc.uuid}  handle={svc.handle}")
            for ch in svc.characteristics:
                props = ",".join(ch.properties)
                print(f"  char  {ch.uuid}  handle={ch.handle}  props=[{props}]")
                for d in getattr(ch, "descriptors", []):
                    print(f"      desc {d.uuid}  handle={d.handle}")
            print("")
        print("done.", flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dump BLE GATT tree of a ZIOTA camera")
    ap.add_argument("--address", default=None)
    ap.add_argument("--name", default=None, help="exact BLE name")
    ap.add_argument("--scan-timeout", type=float, default=10.0)
    ap.add_argument("--connect-timeout", type=float, default=20.0)
    args = ap.parse_args(argv)
    try:
        return asyncio.run(_dump(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
