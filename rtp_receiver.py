"""RTP parsing and RFC 2435 JPEG reassembly for Z-IOT camera media.

The camera, once signaled, streams:
  * video: RTP, payload type 26, RFC 2435 JPEG (fragmented, reassembled here)
  * audio: RTP, payload type 0 (PCMU / G.711 mu-law)

This module is transport-agnostic: feed it raw UDP payloads from the media
socket. It parses the RTP header (RFC 3550) and, for JPEG, reassembles the
fragments into a complete JPEG image.

NOTE on JPEG Huffman tables: RFC 2435 entropy codes the scan with the standard
JPEG Huffman tables; they are NOT carried in the RTP stream. The receiver must
supply them (`dht`). Use `load_dht_from_jpeg()` to extract the DHT segment from
any reference JPEG produced by the same camera, or pass the standard tables.

Header layout reference: RFC 3550 (RTP), RFC 2435 (RTP/JPEG).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PT_JPEG = 26
PT_PCMU = 0


@dataclass
class RtpPacket:
    version: int
    padding: bool
    extension: bool
    marker: bool
    payload_type: int
    sequence: int
    timestamp: int
    ssrc: int
    payload: bytes


def parse_rtp(data: bytes) -> Optional[RtpPacket]:
    """Parse an RTP packet (RFC 3550). Returns None if malformed."""
    if len(data) < 12:
        return None
    b0, b1 = data[0], data[1]
    version = b0 >> 6
    if version != 2:
        return None
    padding = bool(b0 & 0x20)
    extension = bool(b0 & 0x10)
    csrc_count = b0 & 0x0F
    marker = bool(b1 & 0x80)
    payload_type = b1 & 0x7F
    sequence, timestamp, ssrc = struct.unpack_from(">HII", data, 2)
    cursor = 12 + 4 * csrc_count
    if extension:
        if len(data) < cursor + 4:
            return None
        ext_words = struct.unpack_from(">H", data, cursor + 2)[0]
        cursor += 4 + 4 * ext_words
    end = len(data)
    if padding:
        if end <= cursor:
            return None
        pad = data[-1]
        if pad == 0 or pad > end - cursor:
            return None
        end -= pad
    if end < cursor:
        return None
    return RtpPacket(version, padding, extension, marker, payload_type,
                     sequence, timestamp, ssrc, data[cursor:end])


def load_dht_from_jpeg(path: str | Path) -> bytes:
    """Extract the concatenated DHT (0xFFC4) segments from a reference JPEG."""
    buf = Path(path).read_bytes()
    out = bytearray()
    i = 2
    while i + 4 <= len(buf):
        if buf[i] != 0xFF:
            break
        marker = buf[i + 1]
        if marker == 0xDA:  # start of scan -> stop
            break
        seg_len = struct.unpack_from(">H", buf, i + 2)[0]
        if marker == 0xC4:
            out += buf[i:i + 2 + seg_len]
        i += 2 + seg_len
    return bytes(out)


_BUNDLED_DHT: Optional[bytes] = None


def default_dht() -> bytes:
    """Return the bundled standard JPEG Huffman tables (jpeg-huffman.bin).

    These are the standard Annex-K tables the camera's RFC 2435 stream is
    entropy-coded with; bundled so frames decode without a reference JPEG.
    """
    global _BUNDLED_DHT
    if _BUNDLED_DHT is None:
        try:
            _BUNDLED_DHT = Path(__file__).with_name("jpeg-huffman.bin").read_bytes()
        except OSError:
            _BUNDLED_DHT = b""
    return _BUNDLED_DHT


def _segment(marker: int, body: bytes) -> bytes:
    return b"\xff" + bytes([marker]) + struct.pack(">H", len(body) + 2) + body


class JpegRtpReceiver:
    """Reassemble one JPEG frame across RFC 2435 RTP packets.

    `dht` must be the standard JPEG Huffman tables (see module docstring).
    Call `receive(packet_bytes)` for each RTP packet; it returns a complete
    JPEG (bytes) when a frame closes, else None.
    """

    def __init__(self, dht: bytes = b""):
        self.dht = dht or default_dht()
        self.timestamp: Optional[int] = None
        self.parts: dict[int, bytes] = {}
        self.header: Optional[bytes] = None
        self.last: Optional[int] = None
        self.width: Optional[int] = None
        self.height: Optional[int] = None
        self.frames = 0
        self.dropped = 0

    def receive(self, data: bytes) -> Optional[bytes]:
        pkt = parse_rtp(data)
        if pkt is None or pkt.payload_type != PT_JPEG:
            return None
        if not pkt.marker and len(pkt.payload) < 8:
            return None
        payload = pkt.payload
        if len(payload) < 8:
            return None

        offset = int.from_bytes(payload[1:4], "big")
        kind, q, w8, h8 = payload[4], payload[5], payload[6], payload[7]
        width = (w8 or 256) * 8
        height = (h8 or 256) * 8
        cursor = 8
        restart = 0
        if kind >= 64:  # restart-interval header present
            if len(payload) < cursor + 4:
                return None
            restart = struct.unpack_from(">H", payload, cursor)[0]
            cursor += 4
            kind -= 64
        if kind not in (0, 1):  # 0 = YUV420, 1 = YUV422
            return None

        if pkt.timestamp != self.timestamp:
            if self.parts:
                self.dropped += 1
            self.timestamp = pkt.timestamp
            self.parts = {}
            self.header = None
            self.last = None

        if offset == 0:
            if q < 128 or len(payload) < cursor + 4:
                return None
            _ = payload[cursor]  # P byte (ignored)
            precision = payload[cursor + 1]
            length = struct.unpack_from(">H", payload, cursor + 2)[0]
            cursor += 4
            if precision != 0 or length != 128 or len(payload) < cursor + length:
                return None
            tables = payload[cursor:cursor + length]
            cursor += length
            self.width, self.height = width, height
            sof = struct.pack(">BHHB", 8, height, width, 3) + bytes(
                [1, 0x22 if kind == 1 else 0x21, 0, 2, 0x11, 1, 3, 0x11, 1]
            )
            self.header = (
                b"\xff\xd8"
                + _segment(0xDB, b"\x00" + tables[:64])
                + _segment(0xDB, b"\x01" + tables[64:])
                + _segment(0xC0, sof)
                + self.dht
                + (_segment(0xDD, struct.pack(">H", restart)) if restart else b"")
                + _segment(0xDA, bytes([3, 1, 0, 2, 0x11, 3, 0x11, 0, 63, 0]))
            )

        fragment = payload[cursor:]
        if offset + len(fragment) > 512 * 1024 or len(self.parts) > 1024:
            return None
        self.parts[offset] = fragment
        if pkt.marker:
            self.last = offset + len(fragment)
        if self.header is None or self.last is None:
            return None

        pieces = []
        expected = 0
        for position in sorted(self.parts):
            if position != expected:
                return None
            piece = self.parts[position]
            pieces.append(piece)
            expected += len(piece)
        if expected != self.last:
            return None
        image = self.header + b"".join(pieces) + b"\xff\xd9"
        self.parts = {}
        self.header = None
        self.last = None
        self.frames += 1
        return image
