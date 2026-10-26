"""PPPP protocol adapter using aiopppp for IoT camera integration.

This adapter wraps the aiopppp library to provide a consistent interface
with the rest of the iwfcam4hermes plugin. It supports device discovery,
connection, video streaming, and snapshots via the PPPP protocol used by
many cheap IoT cameras.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

try:
    from aiopppp import Device, find_device, Discovery
    AIOPPPP_AVAILABLE = True
except ImportError:
    AIOPPPP_AVAILABLE = False


class PPPPAdapter:
    """Adapter for PPPP-protocol cameras using aiopppp."""

    def __init__(self, ip_address: str = "", username: str = "", password: str = ""):
        self.ip_address = ip_address
        self.username = username
        self.password = password
        self._device: Optional[Any] = None
        self._connected = False
        self._properties: dict = {}

    @property
    def available(self) -> bool:
        return AIOPPPP_AVAILABLE

    @property
    def connected(self) -> bool:
        return self._connected and self._device is not None

    @property
    def properties(self) -> dict:
        return self._properties

    async def discover(self, timeout: int = 10) -> list:
        """Discover PPPP devices on the network via UDP broadcast."""
        if not AIOPPPP_AVAILABLE:
            return []
        found = []
        disc = Discovery('255.255.255.255', remote_port=32108)
        def cb(dev):
            found.append(dev)
        task = asyncio.ensure_future(disc.discover(cb, period=2))
        await asyncio.sleep(min(timeout, 6))
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return found

    async def connect(self, timeout: int = 15) -> bool:
        """Connect to a PPPP camera."""
        if not AIOPPPP_AVAILABLE:
            return False
        try:
            self._device = Device(self.ip_address, self.username, self.password)
            await self._device.connect(timeout=timeout)
            self._connected = True
            self._properties = getattr(self._device, 'properties', {})
            return True
        except Exception as e:
            self._connected = False
            self._device = None
            return False

    async def disconnect(self) -> None:
        if self._device:
            try:
                await self._device.close()
            except Exception:
                pass
        self._device = None
        self._connected = False

    async def start_video(self) -> bool:
        if not self._connected or not self._device:
            return False
        try:
            await self._device.start_video()
            return True
        except Exception:
            return False

    async def stop_video(self) -> bool:
        if not self._connected or not self._device:
            return False
        try:
            await self._device.stop_video()
            return True
        except Exception:
            return False

    async def get_frame(self) -> Optional[bytes]:
        if not self._connected or not self._device:
            return None
        try:
            return await self._device.get_video_frame()
        except Exception:
            return None

    async def reboot(self) -> bool:
        if not self._connected or not self._device:
            return False
        try:
            await self._device.reboot()
            return True
        except Exception:
            return False

    def stream_url(self) -> str:
        """PPPP doesn't use HTTP URLs; return a placeholder."""
        return f"pppp://{self.ip_address}"

    def snapshot_url(self) -> str:
        return f"pppp://{self.ip_address}/snapshot"
