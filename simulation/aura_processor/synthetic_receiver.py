"""Programmatic CSI ingest — same buffer API as WirelessReceiver for mobile/Gazebo sim."""

from __future__ import annotations

import time
from collections import defaultdict, deque

import numpy as np

from .hardware_csi import normalize_esp32_csi


class SyntheticReceiver:
    """Drop-in subset of WirelessReceiver for injected CSI (no UDP socket)."""

    def __init__(self, maxlen: int = 512):
        self.node_buffers: dict[int, deque] = defaultdict(lambda: deque(maxlen=maxlen))
        self.node_last_seen: dict[int, float] = {}
        self.node_packet_count: dict[int, int] = defaultdict(int)
        self.node_rate_window: dict[int, deque] = defaultdict(lambda: deque(maxlen=60))
        self.node_source_ips: dict[int, set[str]] = defaultdict(set)
        self.node_channels: dict[int, int] = {}
        self._linked: set[int] = set()

    def link_node(self, node_id: int, ip: str = "sim") -> None:
        self._linked.add(int(node_id))
        self.node_source_ips[node_id].add(ip)

    def inject(
        self,
        node_id: int,
        csi_row: np.ndarray,
        timestamp_ms: float,
        rssi: int = -55,
        channel: int = 6,
    ) -> None:
        nid = int(node_id)
        row = normalize_esp32_csi(np.asarray(csi_row, dtype=np.complex128).reshape(1, -1))[0]
        now = time.time()
        self.node_buffers[nid].append({
            "csi": row,
            "timestamp_ms": float(timestamp_ms),
            "rssi": int(rssi),
            "channel": int(channel),
        })
        self.node_last_seen[nid] = now
        self.node_packet_count[nid] += 1
        self.node_rate_window[nid].append(now)
        self.node_channels[nid] = channel
        self._linked.add(nid)

    def get_node_window(self, node_id: int, n: int = 80, min_packets: int = 12):
        buf = self.node_buffers.get(node_id)
        if not buf or len(buf) < min_packets:
            return None
        packets = list(buf)[-n:]
        csi = np.stack([p["csi"] for p in packets])
        ts = np.array([p["timestamp_ms"] for p in packets], dtype=float)
        rssi = np.array([p["rssi"] for p in packets], dtype=float)
        return csi, ts, rssi

    def buffer_length(self, node_id: int) -> int:
        return len(self.node_buffers.get(node_id, []))

    def link_health(self, node_id: int) -> dict:
        rate = self.node_packet_rate(node_id)
        return {"packet_rate_hz": rate, "healthy": rate > 0.5}

    def node_packet_rate(self, node_id: int) -> float:
        w = self.node_rate_window.get(node_id, deque())
        if len(w) < 2:
            return 20.0 if node_id in self._linked else 0.0
        span = w[-1] - w[0]
        return len(w) / max(span, 0.05)

    def node_rssi(self, node_id: int) -> float:
        buf = self.node_buffers.get(node_id)
        if not buf:
            return -70.0
        return float(buf[-1].get("rssi", -70))

    def node_source_ip(self, node_id: int) -> str:
        ips = self.node_source_ips.get(node_id, set())
        return next(iter(ips), "sim")

    def system_warnings(self, expected_ids: list[int], timeout_sec: float = 12.0) -> list[str]:
        return []
