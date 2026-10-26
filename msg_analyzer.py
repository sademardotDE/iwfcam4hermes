#!/usr/bin/env python3
"""Message format analyzer for Z-IOT WebSocket traffic."""

import json
import logging
import time
from typing import Any

import websocket

log = logging.getLogger("msg_analyzer")


class MessageAnalyzer:
    """Analyze WebSocket messages from Z-IOT cameras."""

    def __init__(self, ws_url: str = "ws://ws.gps555.net:7080/ws"):
        self.ws_url = ws_url
        self.messages: list[dict[str, Any]] = []

    def capture(self, duration: float = 10.0, uid: str = "ZIOTX_TEST") -> list[dict]:
        """Connect and capture all messages for a duration."""
        ws = websocket.create_connection(self.ws_url, timeout=5)
        ws.send(json.dumps({"cmd": "register", "uid": uid}))
        start = time.time()
        while time.time() - start < duration:
            try:
                ws.settimeout(1)
                data = ws.recv()
                msg = {"timestamp": time.time(), "raw": data, "decoded": None}
                try:
                    msg["decoded"] = json.loads(data)
                except Exception:
                    msg["decoded"] = None
                self.messages.append(msg)
                log.info("Received: %s", data[:200])
            except Exception as e:
                log.debug("Recv timeout/error: %s", e)
                break
        ws.close()
        return self.messages

    def analyze(self) -> dict[str, Any]:
        """Analyze captured messages."""
        text_msgs = [m for m in self.messages if m["decoded"] is not None]
        binary_msgs = [m for m in self.messages if m["decoded"] is None]
        return {
            "total": len(self.messages),
            "text": len(text_msgs),
            "binary": len(binary_msgs),
            "sample_text": text_msgs[:3],
            "sample_binary": [m["raw"][:50].hex() for m in binary_msgs[:3]],
        }

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            for m in self.messages:
                f.write(json.dumps(m, default=str) + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--ws-url", default="ws://ws.gps555.net:7080/ws")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--uid", default="ZIOTX_TEST")
    parser.add_argument("--output", default="messages.jsonl")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    analyzer = MessageAnalyzer(ws_url=args.ws_url)
    msgs = analyzer.capture(duration=args.duration, uid=args.uid)
    analysis = analyzer.analyze()
    print(json.dumps(analysis, indent=2))
    analyzer.save(args.output)
    print(f"Saved {len(msgs)} messages to {args.output}")
