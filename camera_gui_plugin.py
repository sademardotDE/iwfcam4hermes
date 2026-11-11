#!/usr/bin/env python3
"""Hermes plugin for standard camera streaming GUI.

Wraps camera_gui.py into a Hermes-compatible plugin that can be
launched from the Hermes CLI or UI. Supports V4L2 devices, RTSP,
GStreamer pipelines, and webcam indices.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

__all__ = ["CameraGUIPlugin", "create_camera_gui_plugin"]


class CameraGUIPlugin:
    """Hermes-compatible plugin wrapper for the camera streaming GUI.

    Supports V4L2 devices, RTSP streams, webcam indices, and
    GStreamer pipelines for maximum camera compatibility.
    """

    name = "camera_gui"
    version = "0.2.0"
    description = "Standard camera streaming GUI (V4L2, RTSP, webcams, GStreamer)"

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path) if config_path else None
        self._process = None

    def launch(self) -> dict[str, Any]:
        """Launch the camera GUI as a subprocess.

        The GUI needs a desktop session (DISPLAY/WAYLAND_DISPLAY), ``tkinter``
        and ``opencv-python``. Missing prerequisites are reported instead of
        surfacing as a silent subprocess failure.
        """
        gui_path = Path(__file__).parent / "camera_gui.py"
        if not gui_path.exists():
            return {"error": "camera_gui.py not found", "path": str(gui_path)}

        problems = []
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            problems.append("keine Desktop-Sitzung (DISPLAY/WAYLAND_DISPLAY nicht gesetzt)")
        try:  # tkinter is stdlib but the Tk libraries are a system package
            import tkinter  # noqa: F401
        except Exception as exc:  # pragma: no cover - depends on the host
            problems.append(f"tkinter nicht nutzbar: {exc}")
        try:
            import cv2  # noqa: F401
        except Exception:  # pragma: no cover - depends on the host
            problems.append("opencv-python (cv2) fehlt")
        if problems:
            return {"error": "Kamera-GUI nicht startbar", "reasons": problems,
                    "hint": "opencv-python installieren und in einer Desktop-Sitzung starten"}

        try:
            self._process = subprocess.Popen(
                [sys.executable, str(gui_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"status": "launched", "pid": self._process.pid, "gui": str(gui_path)}
        except Exception as e:
            return {"error": str(e)}

    def stop(self) -> dict[str, Any]:
        """Stop the running GUI process."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None
            return {"status": "stopped"}
        return {"status": "not_running"}

    def status(self) -> dict[str, Any]:
        """Return plugin status."""
        running = self._process is not None and self._process.poll() is None
        return {
            "plugin": self.name,
            "version": self.version,
            "running": running,
            "pid": self._process.pid if running else None,
        }

    def list_sources(self) -> list[str]:
        """List available video sources with type detection.

        Supports:
        - V4L2 devices (via v4l2-ctl or /dev/video* scanning)
        - OpenCV webcam indices (only when opencv-python is installed)
        - GStreamer pipeline support
        - Fallback to "No camera found"
        """
        try:  # opencv is optional: without it only V4L2/GStreamer are probed
            import cv2
        except Exception:
            cv2 = None

        sources = []

        # --- V4L2 devices ---
        # Try v4l2-ctl first if available
        v4l2_available = False
        try:
            result = subprocess.run(
                ["v4l2-ctl", "--list-devices"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                v4l2_available = True
                devices = result.stdout.strip().split("\n")
                current_device = ""
                for line in devices:
                    line = line.strip()
                    if line and not line.startswith(" ") and line.endswith(":"):
                        current_device = line.rstrip(":")
                        # Extract device name from the line (everything before the colon)
                        device_name = current_device.split()[-1] if current_device else ""
                        device_path = f"/dev/{device_name}"
                        if os.path.exists(device_path):
                            # Use the full device name as displayed
                            sources.append(f"V4L2 {current_device} ({device_path})")
        except Exception:
            pass

        # Fallback: direct /dev/video* scanning if v4l2-ctl not available
        if not v4l2_available:
            for i in range(20):
                dev = f"/dev/video{i}"
                if os.path.exists(dev):
                    # Try to get a readable name
                    name = f"Webcam {i}"
                    # Check if already in list
                    if not any(dev in s for s in sources):
                        sources.append(f"V4L2 {name} ({dev})")

        # --- OpenCV indices (skipped when cv2 is unavailable) ---
        if cv2 is not None:
            for i in range(10):
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    label = f"Webcam {i} (index {i})"
                    # Normalize: don't add if a V4L2 entry with same number exists
                    is_duplicate = any(
                        f"Webcam {i} (index {i})" in s or f"V4L2 Webcam {i} ({'/dev/video{i}'})" in s
                        for s in sources
                    )
                    if not is_duplicate:
                        sources.append(label)
                    cap.release()

        # --- GStreamer pipeline support ---
        try:
            result = subprocess.run(
                ["which", "gst-inspect-1.0"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                if "GStreamer Pipeline" not in [s.split(" (")[0] for s in sources]:
                    sources.append("GStreamer Pipeline (gst:...)")
        except Exception:
            pass

        # --- Default fallback ---
        if not sources:
            sources = ["Keine lokale Kamera gefunden"]

        return sources


def create_camera_gui_plugin(config_path: str | Path | None = None) -> CameraGUIPlugin:
    return CameraGUIPlugin(config_path)


if __name__ == "__main__":
    plugin = create_camera_gui_plugin()
    print(json.dumps(plugin.status(), indent=2))
    print("Sources:", plugin.list_sources())
    result = plugin.launch()
    print(json.dumps(result, indent=2))