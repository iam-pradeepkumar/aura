#!/usr/bin/env python3
"""
AURA Wireless Hub — receive CSI from ALL ESP32 nodes over WiFi (no USB cables).

1. Start laptop hotspot: SSID=AURA_HUB, password=aura2026
2. Set laptop IP to 192.168.4.1 (default on most hotspots)
3. Flash aura_rx on all nodes with unique NODE_ID
4. Run: python tools/wireless_hub.py

Shows live: people count, localization map, vitals, per-node status.
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "simulation"))

from aura_processor import AURAPipeline

AURA_MAGIC = 0x41555241
HEADER_FMT = "<IBBBBIIbBHHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
UDP_PORT = 5555


class WirelessReceiver:
    def __init__(self, port: int = UDP_PORT):
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", port))
        self.sock.settimeout(0.05)
        self.lock = threading.Lock()
        self.node_buffers: dict[int, deque] = defaultdict(lambda: deque(maxlen=128))
        self.node_last_seen: dict[int, float] = {}
        self.running = True

    def _parse_loop(self):
        buf = bytearray()
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            buf.extend(data)
            while len(buf) >= HEADER_SIZE:
                hdr = struct.unpack_from(HEADER_FMT, buf, 0)
                magic, _, node_id, _, _, ts_ms, rssi, ch, sc_count, payload_bytes = hdr
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
                    })
                    self.node_last_seen[node_id] = time.time()

    def get_node_window(self, node_id: int, n: int = 40) -> tuple[np.ndarray, np.ndarray] | None:
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
            return [nid for nid, t in self.node_last_seen.items() if now - t < timeout_sec]

    def stop(self):
        self.running = False
        self.sock.close()


def main():
    parser = argparse.ArgumentParser(description="AURA wireless laptop hub")
    parser.add_argument("--port", type=int, default=UDP_PORT)
    parser.add_argument("--config", default="simulation/config.yaml")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    cfg = {}
    if cfg_path.exists():
        with cfg_path.open() as f:
            cfg = yaml.safe_load(f) or {}

    area = cfg.get("area_size_m", 10.0)
    node_pos = {int(k): tuple(v) for k, v in cfg.get("node_positions", {}).items()}
    pipeline = AURAPipeline(area_size_m=area, node_positions=node_pos)

    rx = WirelessReceiver(port=args.port)
    threading.Thread(target=rx._parse_loop, daemon=True).start()

    print(f"Listening on UDP :{args.port}")
    print("Start laptop hotspot: SSID=AURA_HUB  password=aura2026")
    print("Power on all ESP32 RX nodes — results appear live below.")

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    fig.suptitle("AURA Wireless Hub — All Nodes Live", fontweight="bold")
    ax_map, ax_count, ax_resp, ax_nodes = axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]

    ax_map.set_xlim(0, area)
    ax_map.set_ylim(0, area)
    ax_map.set_aspect("equal")
    ax_map.set_title("Survivor Map (CSI)")
    ax_map.grid(True, alpha=0.3)
    for nid, (nx, ny) in node_pos.items():
        ax_map.plot(nx, ny, "s", color="#2563eb", markersize=10)
    scatter = ax_map.scatter([], [], c="#ef4444", s=150, zorder=5)

    count_text = ax_count.text(0.5, 0.5, "0", ha="center", va="center", fontsize=56, fontweight="bold")
    ax_count.set_title("People Count")
    ax_count.axis("off")

    resp_line, = ax_resp.plot([], [], color="#10b981")
    ax_resp.set_title("Respiration / Heartbeat")
    ax_resp.set_xlabel("Time (s)")

    node_status = ax_nodes.text(0.05, 0.95, "", va="top", family="monospace", fontsize=10)
    ax_nodes.set_title("Node Status (wireless)")
    ax_nodes.axis("off")

    latest_result = {"res": None, "nodes": []}

    def update(_):
        active = rx.active_nodes()
        all_targets = []
        total_count = 0
        resp_waves = []
        status_lines = [f"Active nodes: {len(active)}", ""]

        for nid in active:
            win = rx.get_node_window(nid, n=40)
            if win is None:
                status_lines.append(f"  Node {nid}: buffering...")
                continue
            csi, ts = win
            fs = 20.0
            if len(ts) > 1:
                fs = 1000.0 / max(np.median(np.diff(ts)), 1.0)
            res = pipeline.process_window(csi, ts[-1] / 1000.0, node_id=nid)
            total_count = max(total_count, res.target_count)
            all_targets.extend(res.targets)
            if res.respiration_waveform is not None:
                resp_waves.append(res.respiration_waveform)
            status_lines.append(
                f"  Node {nid}: RSSI ok | motion={res.motion_detected} | "
                f"count={res.target_count} | resp={res.respiration_bpm:.0f} HR={res.heartbeat_bpm:.0f}"
            )

        if all_targets:
            xs = [t.x_m for t in all_targets]
            ys = [t.y_m for t in all_targets]
            scatter.set_offsets(np.c_[xs, ys])
        else:
            scatter.set_offsets(np.empty((0, 2)))

        count_text.set_text(str(total_count))
        node_status.set_text("\n".join(status_lines) if status_lines else "Waiting for nodes...")

        if resp_waves:
            wave = resp_waves[0]
            t_ax = np.linspace(0, len(wave) / 20.0, len(wave))
            resp_line.set_data(t_ax, wave)
            ax_resp.relim()
            ax_resp.autoscale_view()

        return [scatter, count_text, resp_line, node_status]

    ani = animation.FuncAnimation(fig, update, interval=200, blit=False)
    try:
        plt.show()
    finally:
        rx.stop()


if __name__ == "__main__":
    main()
