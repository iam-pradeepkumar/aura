"""Fake CSI generator — distance-to-victim model feeding aura_processor.

Informed by ESP32 CSI constraints; reimplemented for AURA mobile sim.
Vitals phase modulation only when carrier robot is stationary >= vitals_stationary_sec.
"""

from __future__ import annotations

import math
import time

import numpy as np

from .world import DisasterWorld, Victim


class FakeCsiGenerator:
    def __init__(
        self,
        world: DisasterWorld,
        *,
        presence_radius_m: float = 4.5,
        vitals_stationary_sec: float = 3.0,
        n_subcarriers: int = 52,
        fs_hz: float = 20.0,
    ):
        self.world = world
        self.presence_radius_m = presence_radius_m
        self.vitals_stationary_sec = vitals_stationary_sec
        self.n_sc = n_subcarriers
        self.fs_hz = fs_hz
        self._t0 = time.time()
        self._packet_idx = 0
        self._stationary_since: dict[int, float | None] = {}

    def _is_stationary(self, node_id: int, linear_mps: float, angular_rps: float, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        still = linear_mps < 0.05 and angular_rps < 0.08
        if still:
            if self._stationary_since.get(node_id) is None:
                self._stationary_since[node_id] = now
        else:
            self._stationary_since[node_id] = None
        since = self._stationary_since.get(node_id)
        return since is not None and (now - since) >= self.vitals_stationary_sec

    def generate_packet(
        self,
        node_id: int,
        x: float,
        y: float,
        linear_mps: float = 0.0,
        angular_rps: float = 0.0,
        vitals_capable: bool = True,
    ) -> tuple[np.ndarray, float, int]:
        """Return (csi_row complex64, timestamp_ms, rssi)."""
        now = time.time()
        self._packet_idx += 1
        ts_ms = (now - self._t0) * 1000.0

        victim, dist = self.world.nearest_victim(x, y)
        presence = 0.0
        resp_phase = 0.0
        if victim and dist < self.presence_radius_m:
            presence = float(np.clip(1.0 - dist / self.presence_radius_m, 0.15, 1.0))
            stationary_ok = vitals_capable and self._is_stationary(node_id, linear_mps, angular_rps, now)
            if stationary_ok:
                f_resp = victim.resp_bpm / 60.0
                resp_phase = 0.35 * presence * math.sin(2 * math.pi * f_resp * (self._packet_idx / self.fs_hz))

        motion_noise = 0.08 + 0.25 * min(linear_mps, 1.0) + 0.15 * min(abs(angular_rps), 1.0)
        if presence > 0.2:
            motion_noise += 0.12 * presence

        t = self._packet_idx / self.fs_hz
        row = np.zeros(self.n_sc, dtype=np.complex64)
        for sc in range(self.n_sc):
            base = 0.9 + 0.05 * np.sin(0.3 * sc + 0.1 * t)
            phase = resp_phase + motion_noise * np.sin(2 * math.pi * (2.0 + 0.05 * sc) * t)
            row[sc] = base * np.exp(1j * phase)

        rssi = int(-55 - 20 * math.log10(max(dist if victim else 30.0, 1.0)))
        return row, ts_ms, rssi

    def presence_only(self, x: float, y: float) -> bool:
        victim, dist = self.world.nearest_victim(x, y)
        return victim is not None and dist < self.presence_radius_m
