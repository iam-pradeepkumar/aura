"""Wireless UDP receiver for ESP32 CSI frames (no USB cables)."""

from __future__ import annotations

import socket
import threading
import time
from collections import defaultdict, deque

import numpy as np

from .aura_protocol import AURA_MAGIC, HEADER_SIZE, header_fields, unpack_header

DEFAULT_UDP_PORT = 5555
PENDING_TTL_SEC = 0.25


class WirelessReceiver:
    def __init__(self, port: int = DEFAULT_UDP_PORT):
        self.port = port
        self.sock: socket.socket | None = None
        self.lock = threading.Lock()
        self.node_buffers: dict[int, deque] = defaultdict(lambda: deque(maxlen=512))
        self.node_last_seen: dict[int, float] = {}
        self.node_packet_count: dict[int, int] = defaultdict(int)
        self.node_rate_window: dict[int, deque] = defaultdict(lambda: deque(maxlen=60))
        self.node_source_ips: dict[int, set[str]] = defaultdict(set)
        self.ip_last_seen: dict[str, float] = {}
        self.ip_node_id: dict[str, int] = {}
        self.ip_packet_count: dict[str, int] = defaultdict(int)
        self.node_channels: dict[int, int] = {}
        self._pending: dict[tuple, tuple] = {}
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
        while self.running and self.sock:
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                self._expire_pending()
                continue
            except OSError:
                break
            self._handle_datagram(data, addr)
            self._expire_pending()

    def _expire_pending(self) -> None:
        now = time.time()
        stale = [k for k, (_, t) in self._pending.items() if now - t > PENDING_TTL_SEC]
        for k in stale:
            self._pending.pop(k, None)

    def _handle_datagram(self, data: bytes, addr) -> None:
        if len(data) < 4:
            return

        # Combined frame: header + I/Q payload (preferred, post-firmware fix)
        if len(data) >= HEADER_SIZE:
            magic = unpack_header(data, 0)[0]
            if magic == AURA_MAGIC:
                hdr = header_fields(data, 0)
                payload_bytes = int(hdr["payload_bytes"])
                total = HEADER_SIZE + payload_bytes
                if payload_bytes > 0 and len(data) >= total:
                    self._store_frame(hdr, data[HEADER_SIZE:total], addr)
                    if len(data) > total:
                        self._handle_datagram(data[total:], addr)
                    return
                if len(data) == HEADER_SIZE:
                    key = (addr, hdr["node_id"])
                    self._pending[key] = (hdr, time.time())
                    return

        # Legacy firmware: payload-only second UDP packet
        for key, (hdr, _) in list(self._pending.items()):
            if key[0] != addr:
                continue
            payload_bytes = int(hdr["payload_bytes"])
            if len(data) == payload_bytes:
                self._store_frame(hdr, data, addr)
                self._pending.pop(key, None)
                return

    def _store_frame(self, hdr: dict, iq: bytes, addr) -> None:
        if not iq:
            return
        imag = np.frombuffer(iq[0::2], dtype=np.int8).astype(np.float32)
        real = np.frombuffer(iq[1::2], dtype=np.int8).astype(np.float32)
        csi_row = real + 1j * imag
        node_id = int(hdr["node_id"])
        now = time.time()
        src_ip = str(addr[0]) if addr else ""
        with self.lock:
            if src_ip:
                self.node_source_ips[node_id].add(src_ip)
                self.ip_last_seen[src_ip] = now
                self.ip_node_id[src_ip] = node_id
                self.ip_packet_count[src_ip] += 1
            self.node_buffers[node_id].append({
                "csi": csi_row,
                "timestamp_ms": int(hdr["timestamp_ms"]),
                "rssi": int(hdr["rssi"]),
                "channel": int(hdr["channel"]),
            })
            self.node_last_seen[node_id] = now
            self.node_packet_count[node_id] += 1
            self.node_rate_window[node_id].append(now)
            if hdr.get("channel"):
                self.node_channels[node_id] = int(hdr["channel"])

    def get_node_window(
        self, node_id: int, n: int = 128, min_packets: int | None = None
    ) -> tuple[np.ndarray, np.ndarray] | None:
        need = min_packets if min_packets is not None else n
        with self.lock:
            buf = list(self.node_buffers[node_id])
        if len(buf) < need:
            return None
        use_n = min(n, len(buf))
        recent = buf[-use_n:]
        csi = np.stack([f["csi"] for f in recent])
        ts = np.array([f["timestamp_ms"] for f in recent], dtype=np.float64)
        return csi, ts

    def active_nodes(self, timeout_sec: float = 5.0) -> list[int]:
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

    def packet_rate_hz(self, node_id: int) -> float:
        now = time.time()
        with self.lock:
            times = [t for t in self.node_rate_window.get(node_id, []) if now - t < 3.0]
        if len(times) < 2:
            return 0.0
        span = max(times[-1] - times[0], 0.001)
        return float((len(times) - 1) / span)

    def configured_node_ids(self) -> list[int]:
        return sorted(self.node_last_seen.keys())

    def all_node_status(self, expected_ids: list[int], timeout_sec: float = 20.0) -> list[dict]:
        """Return status for every expected node ID (stable dashboard display)."""
        now = time.time()
        rows = []
        for nid in expected_ids:
            last = self.node_last_seen.get(nid)
            age = now - last if last else 999.0
            rate = self.packet_rate_hz(nid) if age < timeout_sec else 0.0
            if age > timeout_sec:
                status = "offline"
            elif rate < 2.0:
                status = "waiting"
            elif rate < 8.0:
                status = "weak"
            else:
                status = "good"
            rows.append({
                "id": nid,
                "status": status,
                "ip": self.node_source_ip(nid),
                "rssi": self.node_rssi(nid),
                "packet_rate_hz": round(rate, 1),
                "packets_total": self.node_packet_count.get(nid, 0),
                "channel": self.node_channels.get(nid),
                "last_seen_sec": round(age, 1) if last else None,
            })
        return rows

    def system_warnings(self, expected_ids: list[int], timeout_sec: float = 20.0) -> list[str]:
        warnings = self.duplicate_node_warnings()
        statuses = self.all_node_status(expected_ids, timeout_sec)
        online = [s for s in statuses if s["status"] != "offline"]
        weak = [s for s in online if s["status"] in ("weak", "waiting")]
        if weak:
            ids = ", ".join(str(s["id"]) for s in weak)
            warnings.append(
                f"Low CSI rate on node(s) {ids} — power TX first (must join AURA_HUB), "
                f"wait 15s, then walk in the search area."
            )
        rates = [s["packet_rate_hz"] for s in online if s["packet_rate_hz"] > 0]
        if online and rates and max(rates) < 8.0:
            warnings.append(
                "CSI packet rate below 8 Hz — re-flash TX firmware (git pull) so TX joins "
                "AURA_HUB on the same channel as RX nodes."
            )
        channels = {s["channel"] for s in online if s.get("channel")}
        if len(channels) > 1:
            warnings.append(f"Nodes on mixed WiFi channels {sorted(channels)} — keep all on same hotspot.")
        return warnings

    def connected_device_count(self, timeout_sec: float = 20.0) -> int:
        now = time.time()
        with self.lock:
            return sum(1 for t in self.ip_last_seen.values() if now - t < timeout_sec)

    def duplicate_node_warnings(self) -> list[str]:
        warnings: list[str] = []
        with self.lock:
            for nid, ips in self.node_source_ips.items():
                if len(ips) > 1:
                    warnings.append(
                        f"Node ID {nid} is used by {len(ips)} boards ({', '.join(sorted(ips))}). "
                        f"Re-flash each RX with AURA_NODE_ID=1..4."
                    )
            recent_ips = {
                ip for ip, t in self.ip_last_seen.items() if time.time() - t < 5.0
            }
            recent_ids = {self.ip_node_id.get(ip) for ip in recent_ips} - {None}
        if len(recent_ips) > len(recent_ids) and not warnings:
            warnings.append(
                f"{len(recent_ips)} ESP32 devices are sending CSI but only "
                f"{len(recent_ids)} unique node ID(s). Re-flash with AURA_NODE_ID=1..4."
            )
        return warnings

    def node_source_ip(self, node_id: int) -> str | None:
        with self.lock:
            ips = self.node_source_ips.get(node_id)
        if not ips:
            return None
        return sorted(ips)[-1]

    def recent_sources(self, timeout_sec: float = 20.0) -> list[dict]:
        now = time.time()
        with self.lock:
            rows = [
                {
                    "ip": ip,
                    "node_id": self.ip_node_id.get(ip),
                    "packets": self.ip_packet_count.get(ip, 0),
                    "age_sec": round(now - t, 1),
                }
                for ip, t in self.ip_last_seen.items()
                if now - t < timeout_sec
            ]
        return sorted(rows, key=lambda r: (r["node_id"] or 0, r["ip"]))

    def link_health(self, node_id: int) -> dict:
        rssi = self.node_rssi(node_id)
        rate = self.packet_rate_hz(node_id)
        with self.lock:
            last = self.node_last_seen.get(node_id)
            total = self.node_packet_count.get(node_id, 0)
        age = time.time() - last if last else 999.0
        if age > 20.0:
            status = "offline"
        elif rate < 2.0:
            status = "waiting"
        elif rate < 8.0:
            status = "weak"
        elif rssi is not None and rssi < -82:
            status = "weak"
        else:
            status = "good"
        return {
            "status": status,
            "rssi": rssi,
            "packet_rate_hz": round(rate, 1),
            "packets_total": total,
            "last_seen_sec": round(age, 2),
        }
