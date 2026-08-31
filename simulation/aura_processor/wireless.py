"""Wireless UDP receiver for ESP32 CSI frames (no USB cables)."""

from __future__ import annotations

import socket
import struct
import threading
import time
from collections import defaultdict, deque

import numpy as np

AURA_MAGIC = 0x41555241
HEADER_FMT = "<IBBBBIIbBHHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
DEFAULT_UDP_PORT = 5555


class WirelessReceiver:
    def __init__(self, port: int = DEFAULT_UDP_PORT):
        self.port = port
        self.sock: socket.socket | None = None
        self.lock = threading.Lock()
        self.node_buffers: dict[int, deque] = defaultdict(lambda: deque(maxlen=256))
        self.node_last_seen: dict[int, float] = {}
        self.running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.running:
            return
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", self.port))
        self.sock.settimeout(0.05)
        self.running = True
        self._thread = threading.Thread(target=self._parse_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _parse_loop(self) -> None:
        buf = bytearray()
        while self.running and self.sock:
            try:
                data, _addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            buf.extend(data)
            while len(buf) >= HEADER_SIZE:
                hdr = struct.unpack_from(HEADER_FMT, buf, 0)
                magic, _, node_id, _, _, ts_ms, rssi, ch, _sc, payload_bytes = hdr
                total = HEADER_SIZE + payload_bytes
                if magic != AURA_MAGIC or len(buf) < total:
                    if magic != AURA_MAGIC:
                        del buf[0]
                    break
                iq = bytes(buf[HEADER_SIZE:total])
                del buf[:total]
                imag = np.frombuffer(iq[0::2], dtype=np.int8).astype(np.float32)
                real = np.frombuffer(iq[1::2], dtype=np.int8).astype(np.float32)
                csi_row = real + 1j * imag
                with self.lock:
                    self.node_buffers[node_id].append({
                        "csi": csi_row,
                        "timestamp_ms": ts_ms,
                        "rssi": rssi,
                        "channel": ch,
                    })
                    self.node_last_seen[node_id] = time.time()

    def get_node_window(self, node_id: int, n: int = 128) -> tuple[np.ndarray, np.ndarray] | None:
        with self.lock:
            buf = list(self.node_buffers[node_id])
        if len(buf) < n:
            return None
        recent = buf[-n:]
        csi = np.stack([f["csi"] for f in recent])
        ts = np.array([f["timestamp_ms"] for f in recent], dtype=np.float64)
        return csi, ts

    def active_nodes(self, timeout_sec: float = 3.0) -> list[int]:
        now = time.time()
        with self.lock:
            return sorted(nid for nid, t in self.node_last_seen.items() if now - t < timeout_sec)

    def node_rssi(self, node_id: int) -> int | None:
        with self.lock:
            buf = self.node_buffers.get(node_id)
        if not buf:
            return None
        return int(buf[-1]["rssi"])

    def buffer_length(self, node_id: int) -> int:
        with self.lock:
            return len(self.node_buffers.get(node_id, []))
