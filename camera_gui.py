#!/usr/bin/env python3
"""Standard Camera Streaming GUI.

Supports local webcams (/dev/video*), IP cameras (RTSP/HTTP),
and any OpenCV-compatible video source. Built with tkinter + OpenCV.
"""
from __future__ import annotations

import os
import threading
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
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("Camera Streaming GUI")
        self.root.geometry("900x700")

        self.cap: cv2.VideoCapture | None = None
        self.running = False
        self.current_frame = None
        self.snapshot_dir = Path.home() / "camera_snapshots"
        self.snapshot_dir.mkdir(exist_ok=True)

        self._build_ui()
        self._refresh_sources()

    def _build_ui(self):
        # --- Top bar: source selection ---
        top = Frame(self.root)
        top.pack(side=TOP, fill=X, padx=8, pady=4)

        Label(top, text="Quelle:").pack(side=LEFT)
        self.source_var = StringVar()
        self.source_combo = ttk.Combobox(top, textvariable=self.source_var, width=40)
        self.source_combo.pack(side=LEFT, padx=4)
        Button(top, text="Aktualisieren", command=self._refresh_sources).pack(side=LEFT, padx=2)
        Button(top, text="Verbinden", command=self._connect).pack(side=LEFT, padx=2)
        Button(top, text="Trennen", command=self._disconnect).pack(side=LEFT, padx=2)

        # --- IP/URL entry ---
        url_frame = Frame(self.root)
        url_frame.pack(side=TOP, fill=X, padx=8, pady=2)
        Label(url_frame, text="URL/RTSP:").pack(side=LEFT)
        self.url_entry = Entry(url_frame, width=60)
        self.url_entry.pack(side=LEFT, padx=4)
        Button(url_frame, text="URL öffnen", command=self._connect_url).pack(side=LEFT, padx=2)

        # --- Video display ---
        self.video_label = Label(self.root, bg="black")
        self.video_label.pack(side=TOP, fill=BOTH, expand=True, padx=8, pady=4)

        # --- Bottom bar: controls ---
        bottom = Frame(self.root)
        bottom.pack(side=BOTTOM, fill=X, padx=8, pady=4)
        Button(bottom, text="Snapshot", command=self._snapshot).pack(side=LEFT, padx=2)
        Button(bottom, text="Aufnahme Start/Stop", command=self._toggle_record).pack(side=LEFT, padx=2)
        self.status_label = Label(bottom, text="Bereit")
        self.status_label.pack(side=RIGHT, padx=4)

        self.recording = False
        self.writer = None

    def _refresh_sources(self):
        sources = []
        # Local video devices
        for i in range(10):
            dev = f"/dev/video{i}"
            if os.path.exists(dev):
                sources.append(f"Webcam {i} ({dev})")
        # Also try OpenCV indices
        for i in range(5):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                if f"Webcam {i}" not in [s.split(" (")[0] for s in sources]:
                    sources.append(f"Webcam {i} (index {i})")
                cap.release()
        if not sources:
            sources = ["Keine lokale Kamera gefunden"]
        self.source_combo["values"] = sources
        if sources:
            self.source_combo.current(0)

    def _connect(self):
        sel = self.source_var.get()
        # Extract index
        idx = 0
        if "index" in sel:
            try:
                idx = int(sel.split("index ")[1].rstrip(")"))
            except Exception:
                idx = 0
        elif "video" in sel:
            try:
                idx = int(sel.split("video")[1].split()[0])
            except Exception:
                idx = 0
        self._open_capture(idx)

    def _connect_url(self):
        url = self.url_entry.get().strip()
        if url:
            self._open_capture(url)

    def _open_capture(self, source):
        self._disconnect()
        try:
            self.cap = cv2.VideoCapture(source)
            if not self.cap.isOpened():
                messagebox.showerror("Fehler", f"Kann Quelle nicht öffnen: {source}")
                self.cap = None
                return
            self.running = True
            self.status_label.config(text=f"Verbunden: {source}")
            self._update_frame()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def _disconnect(self):
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
        if self.current_frame is None:
            messagebox.showwarning("Warnung", "Kein Bild verfügbar")
            return
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = self.snapshot_dir / f"snapshot_{ts}.jpg"
        cv2.imwrite(str(path), self.current_frame)
        self.status_label.config(text=f"Snapshot gespeichert: {path}")
        messagebox.showinfo("Snapshot", f"Gespeichert: {path}")

    def _toggle_record(self):
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
        self._disconnect()
        self.root.destroy()


def main():
    root = Tk()
    app = CameraStreamGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
