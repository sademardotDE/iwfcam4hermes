#!/usr/bin/env python3
"""Hermes plugin for standard camera streaming GUI.

Wraps camera_gui.py into a Hermes-compatible plugin that can be
launched from the Hermes CLI or UI.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

__all__ = ["CameraGUIPlugin", "create_camera_gui_plugin"]


class CameraGUIPlugin:
    """Hermes-compatible plugin wrapper for the camera streaming GUI."""

    name = "camera_gui"
    version = "0.1.0"
    description = "Standard camera streaming GUI (webcams, IP cameras, RTSP)"

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path) if config_path else None
        self._process = None

    def launch(self) -> dict[str, Any]:
        """Launch the camera GUI as a subprocess."""
        gui_path = Path(__file__).parent / "camera_gui.py"
        if not gui_path.exists():
            gui_path = Path("/workspace/iwfcam/camera_gui.py")
        if not gui_path.exists():
            return {"error": "camera_gui.py not found", "path": str(gui_path)}

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
        running = self._process is not None and self._process.poll() is None
        return {
            "plugin": self.name,
            "version": self.version,
            "running": running,
            "pid": self._process.pid if running else None,
        }

    def list_sources(self) -> list[str]:
        """List available video sources."""
        import cv2
        import os

        sources = []
        for i in range(10):
            dev = f"/dev/video{i}"
            if os.path.exists(dev):
                sources.append(f"Webcam {i} ({dev})")
        for i in range(5):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                label = f"Webcam {i} (index {i})"
                if label not in sources:
                    sources.append(label)
                cap.release()
        return sources or ["Keine lokale Kamera gefunden"]


def create_camera_gui_plugin(config_path: str | Path | None = None) -> CameraGUIPlugin:
    return CameraGUIPlugin(config_path)


if __name__ == "__main__":
    plugin = create_camera_gui_plugin()
    print(json.dumps(plugin.status(), indent=2))
    print("Sources:", plugin.list_sources())
    result = plugin.launch()
    print(json.dumps(result, indent=2))
