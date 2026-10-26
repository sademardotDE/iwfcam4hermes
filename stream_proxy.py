#!/usr/bin/env python3
"""Simple HTTP stream proxy for WiFi cameras."""

import http.server
import socket
import socketserver
import threading
import urllib.request
from typing import Optional

from .plugin import Camera


class StreamProxy:
    """Proxy a camera stream to a local port (HTTP or RTSP)."""

    def __init__(self, cam: Camera, local_port: int = 8088):
        self.cam = cam
        self.local_port = local_port
        self._server: Optional[socketserver.TCPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._rtsp_thread: Optional[threading.Thread] = None
        self._rtsp_stop = threading.Event()

    def start(self) -> bool:
        url = self.cam.stream_url()
        if not url:
            return False

        if url.startswith("rtsp://"):
            return self._start_rtsp_proxy(url)
        else:
            return self._start_http_proxy(url)

    def _start_http_proxy(self, url: str) -> bool:
        class ProxyHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    req = urllib.request.urlopen(url)
                    self.send_response(200)
                    self.send_header("Content-Type", req.headers.get("Content-Type", "application/octet-stream"))
                    self.end_headers()
                    while True:
                        chunk = req.read(4096)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                except Exception as e:
                    self.send_error(502, str(e))

            def log_message(self, format, *args):
                pass

        try:
            self._server = socketserver.TCPServer(("", self.local_port), ProxyHandler)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            return True
        except Exception:
            return False

    def _start_rtsp_proxy(self, url: str) -> bool:
        # Parse target
        from urllib.parse import urlparse

        parsed = urlparse(url)
        target_host = parsed.hostname
        target_port = parsed.port or 554

        def _forward():
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.bind(("", self.local_port))
                server.listen(5)
                while not self._rtsp_stop.is_set():
                    conn, _ = server.accept()
                    # Forward to target
                    target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    target.connect((target_host, target_port))
                    # Bidirectional relay
                    def relay(src, dst):
                        try:
                            while True:
                                data = src.recv(4096)
                                if not data:
                                    break
                                dst.sendall(data)
                        except Exception:
                            pass
                        finally:
                            src.close()
                            dst.close()

                    t1 = threading.Thread(target=relay, args=(conn, target), daemon=True)
                    t2 = threading.Thread(target=relay, args=(target, conn), daemon=True)
                    t1.start()
                    t2.start()
            except Exception:
                pass

        self._rtsp_thread = threading.Thread(target=_forward, daemon=True)
        self._rtsp_thread.start()
        return True

    def stop(self) -> None:
        self._rtsp_stop.set()
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        if self._rtsp_thread:
            self._rtsp_thread.join(timeout=5)
            self._rtsp_thread = None

    @property
    def local_url(self) -> str:
        url = self.cam.stream_url()
        if url.startswith("rtsp://"):
            return f"rtsp://127.0.0.1:{self.local_port}/"
        return f"http://127.0.0.1:{self.local_port}/"


if __name__ == "__main__":
    from .plugin import load_config

    import sys

    if len(sys.argv) < 3:
        print("Usage: stream_proxy.py <config.json> <device_id> [port]")
        sys.exit(1)

    cfg = load_config(sys.argv[1])
    cam = next((c for c in cfg["devices"] if c.id == sys.argv[2]), None)
    if not cam:
        print("Unknown device")
        sys.exit(1)

    port = int(sys.argv[3]) if len(sys.argv) > 3 else 8088
    proxy = StreamProxy(cam, local_port=port)
    if proxy.start():
        print(f"Proxying {cam.stream_url()} -> {proxy.local_url}")
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            proxy.stop()
    else:
        print("Failed to start proxy")
        sys.exit(1)
