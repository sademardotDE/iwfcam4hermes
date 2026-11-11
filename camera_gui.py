#!/usr/bin/env python3
"""Standard Camera Streaming GUI.

Supports local webcams (/dev/video*), IP cameras (RTSP/HTTP),
and any OpenCV-compatible video source. Built with tkinter + OpenCV.

Also adds V4L2 device enumeration, GStreamer pipeline support,
and camera type auto-detection for improved hardware compatibility.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from tkinter import (
    Tk, Frame, Label, Button, Listbox, Scrollbar, Entry, StringVar,
    filedialog, messagebox, ttk,
)
from tkinter.constants import LEFT, RIGHT, TOP, BOTTOM, BOTH, X, Y, W, END

import cv2
from PIL import Image, ImageTk


class CameraStreamGUI:
    """Tkinter-based camera streaming interface with V4L2 and RTSP support."""

    def __init__(self, root: Tk):
        self.root = root
        self.root.title("Camera Streaming GUI")
        self.root.geometry("900x700")

        self.cap: cv2.VideoCapture | None = None
        self.running = False
        self.current_frame = None
        self.snapshot_dir = Path.home() / "camera_snapshots"
        self.snapshot_dir.mkdir(exist_ok=True)

        # Camera source tracking
        self.camera_type: str = "unknown"  # v4l2, rtsp, webcam, gstreamer
        self.camera_model: str | None = None

        self._build_ui()
        self._refresh_sources()

    def _detect_camera_type(self, source: str) -> str:
        """Auto-detect camera source type."""
        source_lower = source.lower().strip()

        # GStreamer pipeline detection
        if source_lower.startswith("gst:"):
            return "gstreamer"

        # RTSP/URL detection
        if source_lower.startswith(("rtsp://", "http://", "https://", "ftp://")):
            return "rtsp"

        # V4L2 device detection
        if source_lower.startswith("/dev/video") or source_lower.startswith("/dev/v4l"):
            return "v4l2"

        # OpenCV index
        try:
            idx = int(source_lower)
            return "webcam"
        except ValueError:
            pass

        return "unknown"

    def _get_v4l2_info(self, device: str) -> dict:
        """Get V4L2 device information using v4l2-ctl."""
        info = {"device": device, "type": "unknown", "name": device, "inputs": []}

        try:
            # Try v4l2-ctl to get device info
            result = subprocess.run(
                ["v4l2-ctl", "--device", device, "--list-inputs"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                current_input = ""
                for line in lines:
                    line = line.strip()
                    if line.startswith("Input "):
                        current_input = line
                    elif line and current_input:
                        info["inputs"].append(line)
                # If we have inputs, use the first one's name
                if info["inputs"]:
                    info["name"] = info["inputs"][0].split("|")[0].strip() if "|" in info["inputs"][0] else info["inputs"][0]
        except Exception:
            pass

        # Try to get card info
        try:
            result = subprocess.run(
                ["v4l2-ctl", "--device", device, "--get-ctrls"],
                capture_output=True, text=True, timeout=5
            )
            # Just check if it runs without error
            pass
        except Exception:
            pass

        return info

    def _refresh_sources(self):
        """Refresh available video sources including V4L2, RTSP, and webcams."""
        sources = []

        # --- V4L2 devices ---
        try:
            # List V4L2 devices
            result = subprocess.run(
                ["v4l2-ctl", "--list-devices"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                devices = result.stdout.strip().split("\n")
                current_device = ""
                for line in devices:
                    line = line.strip()
                    if line and not line.startswith(" ") and line.endswith(":"):
                        current_device = line.rstrip(":")
                        device_path = f"/dev/{current_device.split()[-1] if current_device else ''}"
                        # Validate device exists
                        if os.path.exists(device_path):
                            v4l2_info = self._get_v4l2_info(device_path)
                            name = v4l2_info.get("name", current_device)
                            sources.append(f"V4L2 {name} ({device_path})")
                            self.camera_type = "v4l2"
        except Exception:
            pass

        # Also check direct /dev/video entries
        for i in range(20):
            dev = f"/dev/video{i}"
            if os.path.exists(dev):
                # Check if already listed
                if not any(dev in s for s in sources):
                    v4l2_info = self._get_v4l2_info(dev)
                    name = v4l2_info.get("name", f"Webcam {i}")
                    sources.append(f"V4L2 {name} ({dev})")
                    self.camera_type = "v4l2"

        # --- OpenCV indices ---
        for i in range(10):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                label = f"Webcam {i} (index {i})"
                if label not in sources:
                    sources.append(label)
                    self.camera_type = "webcam"
                cap.release()

        # --- GStreamer pipeline entries (optional) ---
        try:
            # Check if gst-inspect-1.0 is available
            result = subprocess.run(
                ["which", "gst-inspect-1.0"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                # Add a GStreamer pipeline entry
                sources.append("GStreamer Pipeline (gst:...)")
                self.camera_type = "gstreamer"
        except Exception:
            pass

        # --- Default fallback ---
        if not sources:
            sources = ["Keine lokale Kamera gefunden"]

        # Update UI
        self.source_combo["values"] = sources
        if sources:
            self.source_combo.current(0)

        # Update status based on detected type
        if self.camera_type != "unknown":
            self.status_label.config(text=f"Quelle erkannt: {self.camera_type}")
        else:
            self.status_label.config(text="Bereit")

    def _connect(self):
        """Connect to the selected video source."""
        sel = self.source_var.get()
        if not sel:
            messagebox.showwarning("Warnung", "Bitte eine Quelle auswählen")
            return

        # Extract source and index
        source = sel
        idx = 0

        # Handle V4L2 device format: "V4L2 Name (/dev/videoX)"
        if "V4L2" in sel:
            # Extract the device path
            import re
            match = re.search(r'/dev/video\d+', sel)
            if match:
                source = match.group(0)
                idx = int(match.group(0).split("video")[1])
            else:
                # Try to extract from the string
                parts = sel.split("(")
                if len(parts) > 1:
                    device_part = parts[1].rstrip(")")
                    source = device_part

        # Handle "Webcam X (index Y)" format
        elif "index" in sel:
            try:
                idx = int(sel.split("index ")[1].rstrip(")"))
                # Build device path
                source = f"/dev/video{idx}" if f"/dev/video{idx}" else f"0"
            except Exception:
                idx = 0

        # Handle "Webcam X" without index
        elif "Webcam" in sel:
            try:
                idx = int(sel.split()[1]) if len(sel.split()) > 1 else 0
                source = f"/dev/video{idx}"
            except Exception:
                idx = 0
                source = "0"

        # Handle GStreamer pipeline
        elif sel.startswith("GStreamer"):
            # User will enter a pipeline in the URL field
            source = "gst:"  # Will be handled by _open_capture
            idx = 0

        # Handle RTSP/URL - try as URL directly
        elif sel.startswith(("rtsp://", "http://", "https://")):
            source = sel
            idx = 0

        # Default: treat as V4L2 device index or OpenCV index
        else:
            # Try to parse as number
            try:
                idx = int(sel)
                source = f"/dev/video{idx}" if idx < 20 else f"0"
            except ValueError:
                # Try as URL
                if sel.startswith(("rtsp://", "http://", "https://")):
                    source = sel
                else:
                    source = f"/dev/video{0}" if sel.isdigit() else "0"

        self._open_capture(source, idx)

    def _connect_url(self):
        """Connect to a URL/RTSP source from the entry field."""
        url = self.url_entry.get().strip()
        if url:
            # Auto-detect type
            self.camera_type = self._detect_camera_type(url)
            self._open_capture(url)

    def _open_capture(self, source: str, idx: int = 0):
        """Open a video capture source with auto-detection."""
        self._disconnect()

        # Determine the actual source to pass to OpenCV
        actual_source = source

        # Handle V4L2 device paths
        if source.startswith("/dev/video") or source.startswith("/dev/v4l"):
            actual_source = source
            self.camera_type = "v4l2"

        # Handle GStreamer pipelines
        elif source.startswith("gst:"):
            actual_source = source
            self.camera_type = "gstreamer"

        # Handle RTSP/HTTP URLs
        elif source.lower().startswith(("rtsp://", "http://", "https://")):
            actual_source = source
            self.camera_type = "rtsp"

        # Handle numeric indices
        else:
            try:
                num_idx = int(source)
                # Try as V4L2 device first
                test_path = f"/dev/video{num_idx}"
                if os.path.exists(test_path):
                    actual_source = test_path
                    self.camera_type = "v4l2"
                else:
                    # Try as OpenCV index
                    actual_source = str(num_idx)
                    self.camera_type = "webcam"
            except ValueError:
                # Try as URL
                if source.lower().startswith(("rtsp://", "http://", "https://")):
                    actual_source = source
                    self.camera_type = "rtsp"
                else:
                    actual_source = "0"
                    self.camera_type = "webcam"

        try:
            self.cap = cv2.VideoCapture(actual_source)
            if not self.cap.isOpened():
                # Try with CAP_V4L2 backend
                if self.camera_type == "v4l2":
                    try:
                        self.cap = cv2.VideoCapture(actual_source, cv2.CAP_V4L2)
                        if self.cap.isOpened():
                            pass  # Successfully opened with V4L2 backend
                        else:
                            raise Exception("V4L2 backend failed")
                    except Exception:
                        pass

                # Try with CAP_GSTREAMER backend
                if self.camera_type == "gstreamer" and hasattr(cv2, "CAP_GSTREAMER"):
                    try:
                        self.cap = cv2.VideoCapture(actual_source, cv2.CAP_GSTREAMER)
                        if self.cap.isOpened():
                            pass  # Successfully opened with GStreamer backend
                        else:
                            raise Exception("GStreamer backend failed")
                    except Exception:
                        pass

                if not self.cap.isOpened():
                    messagebox.showerror(
                        "Fehler",
                        f"Kann Quelle nicht öffnen: {actual_source}\n"
                        "Versuchte Backends: V4L2, GStreamer, Default"
                    )
                    self.cap = None
                    self.camera_type = "unknown"
                    return

            self.running = True
            # Update status with camera info
            info_parts = [f"Verbunden: {actual_source}"]
            if self.camera_type != "unknown":
                info_parts.append(f"Typ: {self.camera_type}")
            if self.camera_model:
                info_parts.append(f"Modell: {self.camera_model}")
            self.status_label.config(text=" | ".join(info_parts))

            self._update_frame()

        except Exception as e:
            messagebox.showerror("Fehler", str(e))
            self.cap = None
            self.camera_type = "unknown"
            self.status_label.config(text="Fehler")

    def _disconnect(self):
        """Disconnect the current video source."""
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        if self.writer:
            self.writer.release()
            self.writer = None
        self.recording = False
        self.video_label.config(image="")
        self.status_label.config(text="Getrennt")

    def _update_frame(self):
        """Update the video frame display."""
        if not self.running or not self.cap:
            return

        ret, frame = self.cap.read()
        if ret:
            self.current_frame = frame
            # Resize for display
            h, w = frame.shape[:2]
            max_w = 880
            if w > max_w:
                scale = max_w / w
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.config(image=imgtk)

            if self.recording and self.writer:
                self.writer.write(frame)

        self.root.after(30, self._update_frame)

    def _snapshot(self):
        """Take a snapshot of the current frame."""
        if self.current_frame is None:
            messagebox.showwarning("Warnung", "Kein Bild verfügbar")
            return
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = self.snapshot_dir / f"snapshot_{ts}.jpg"
        cv2.imwrite(str(path), self.current_frame)
        self.status_label.config(text=f"Snapshot gespeichert: {path}")
        messagebox.showinfo("Snapshot", f"Gespeichert: {path}")

    def _toggle_record(self):
        """Start/stop video recording."""
        if not self.running or not self.cap:
            return

        if not self.recording:
            ts = time.strftime("%Y%m%d_%H%M%S")
            path = self.snapshot_dir / f"record_{ts}.avi"
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = self.cap.get(cv2.CAP_PROP_FPS) or 20
            self.writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
            self.recording = True
            self.status_label.config(text=f"Aufnahme: {path}")
        else:
            if self.writer:
                self.writer.release()
                self.writer = None
            self.recording = False
            self.status_label.config(text="Aufnahme gestoppt")

    def on_close(self):
        """Clean up on window close."""
        self._disconnect()
        self.root.destroy()


def main():
    root = Tk()
    app = CameraStreamGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()