"""AURA full sensing pipeline — all five detection functions."""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from .srcc import srcc, motion_energy
from .doppler import delay_doppler_map, extract_motion_parameters, detect_peaks_multi_target
from .vitals import extract_vitals
from .localization import TargetTracker, localize_static_target, multinode_localize, Target


@dataclass
class SensingResult:
    timestamp_sec: float
    motion_detected: bool
    motion_energy: float
    target_count: int
    targets: list[Target] = field(default_factory=list)
    respiration_bpm: float = 0.0
    heartbeat_bpm: float = 0.0
    respiration_waveform: np.ndarray | None = None
    heartbeat_waveform: np.ndarray | None = None
    delay_doppler_map: np.ndarray | None = None
    events: list[str] = field(default_factory=list)


class AURAPipeline:
    """
    Processes ESP32 CSI for disaster survivor sensing:
    1. Motion detection
    2. Moving target localization (XY, velocity, acceleration)
    3. Tracking (trajectory, entry/exit)
    4. Static target localization
    5. Vital sign estimation
    """

    def __init__(
        self,
        fs_hz: float = 20.0,
        area_size_m: float = 10.0,
        motion_threshold: float = 0.02,
        window_sec: float = 1.0,
        node_positions: dict[int, tuple[float, float]] | None = None,
    ):
        self.fs_hz = fs_hz
        self.area_size_m = area_size_m
        self.motion_threshold = motion_threshold
        self.window_samples = max(int(window_sec * fs_hz), 32)
        self.tracker = TargetTracker(area_size_m=area_size_m)
        self.node_positions = node_positions or {1: (0.0, 0.0), 2: (10.0, 0.0), 3: (5.0, 8.7)}

    def process_window(
        self,
        csi_window: np.ndarray,
        timestamp_sec: float,
        node_id: int = 1,
    ) -> SensingResult:
        cleaned = srcc(csi_window)
        m_energy = float(np.mean(motion_energy(cleaned)))
        motion = m_energy > self.motion_threshold

        vitals = extract_vitals(cleaned, self.fs_hz)
        motion_params = extract_motion_parameters(cleaned, self.fs_hz, self.area_size_m)
        _, _, ddm = delay_doppler_map(cleaned, self.fs_hz)

        peaks = detect_peaks_multi_target(ddm, max_targets=6)
        detections = []

        if motion:
            for di, ti, _ in peaks:
                doppler_hz = motion_params["doppler_axis"][di] if di < len(motion_params["doppler_axis"]) else 0
                rng = motion_params["range_m"] * (0.6 + 0.4 * (ti / max(ddm.shape[1], 1)))
                angle = np.arctan2(motion_params["y_m"], motion_params["x_m"] + 1e-6)
                angle += (ti - ddm.shape[1] / 2) * 0.05
                x = rng * np.cos(angle)
                y = rng * np.sin(angle)
                detections.append({
                    "x_m": float(np.clip(x, 0, self.area_size_m)),
                    "y_m": float(np.clip(y, 0, self.area_size_m)),
                    "velocity_mps": abs(motion_params["velocity_mps"]),
                    "respiration_bpm": vitals["respiration_bpm"],
                    "heartbeat_bpm": vitals["heartbeat_bpm"],
                    "dt": 1.0 / self.fs_hz,
                })
        else:
            static = localize_static_target(cleaned, self.fs_hz, self.area_size_m)
            if static["is_static"] and vitals["respiration_bpm"] > 4:
                x, y = multinode_localize(
                    self.node_positions,
                    {node_id: static["range_m"]},
                )
                detections.append({
                    "x_m": x if x else static["x_m"],
                    "y_m": y if y else static["y_m"],
                    "velocity_mps": 0.0,
                    "respiration_bpm": vitals["respiration_bpm"],
                    "heartbeat_bpm": vitals["heartbeat_bpm"],
                    "dt": 1.0 / self.fs_hz,
                })

        targets = self.tracker.update(detections, timestamp_sec)
        return SensingResult(
            timestamp_sec=timestamp_sec,
            motion_detected=motion,
            motion_energy=m_energy,
            target_count=len(detections),
            targets=targets,
            respiration_bpm=vitals["respiration_bpm"],
            heartbeat_bpm=vitals["heartbeat_bpm"],
            respiration_waveform=vitals["respiration_waveform"],
            heartbeat_waveform=vitals["heartbeat_waveform"],
            delay_doppler_map=ddm,
            events=list(self.tracker.events),
        )

    def process_session(self, csi: np.ndarray, timestamps_ms: np.ndarray) -> list[SensingResult]:
        """Slide window over full CSI recording."""
        results = []
        n = len(csi)
        hop = max(self.window_samples // 2, 1)
        for start in range(0, n - self.window_samples + 1, hop):
            end = start + self.window_samples
            t_sec = timestamps_ms[start] / 1000.0
            res = self.process_window(csi[start:end], t_sec)
            results.append(res)
        return results
