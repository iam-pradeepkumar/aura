"""AURA full sensing pipeline — all five detection functions."""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from .srcc import srcc, motion_energy
from .doppler import delay_doppler_map
from .vitals import extract_vitals, extract_vitals_for_target
from .multitarget import detect_and_localize
from .localization import TargetTracker, Target


def _fallback_detections(
    csi: np.ndarray,
    area_size_m: float,
    max_targets: int,
    sensor_xy: tuple[float, float],
) -> list[dict]:
    """Energy-based fallback when delay peaks are weak."""
    amp = np.abs(csi)
    sc_energy = amp.var(axis=0)
    peaks, _ = __import__("scipy.signal", fromlist=["find_peaks"]).find_peaks(
        sc_energy, distance=max(2, len(sc_energy) // 8)
    )
    if len(peaks) == 0:
        peaks = np.argsort(sc_energy)[-max_targets:]
    sx, sy = sensor_xy
    dets = []
    for i, pk in enumerate(peaks[:max_targets]):
        angle = (pk / max(len(sc_energy), 1) - 0.5) * 1.8
        r = area_size_m * (0.35 + 0.2 * i)
        x = float(np.clip(sx + r * np.sin(angle), 0.5, area_size_m - 0.5))
        y = float(np.clip(sy + r * np.cos(angle), 0.5, area_size_m - 0.5))
        dets.append({"x_m": x, "y_m": y, "velocity_mps": 0.1, "weight": 1.0, "delay_bin": int(pk), "dt": 0.05})
    return dets


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
        window_sec: float = 2.0,
        max_targets: int = 3,
        node_positions: dict[int, tuple[float, float]] | None = None,
    ):
        self.fs_hz = fs_hz
        self.area_size_m = area_size_m
        self.motion_threshold = motion_threshold
        self.max_targets = max_targets
        self.window_samples = max(int(window_sec * fs_hz), 32)
        self.tracker = TargetTracker(area_size_m=area_size_m, max_targets=max_targets)
        self.node_positions = node_positions or {1: (0.0, 0.0), 2: (10.0, 0.0), 3: (10.0, 10.0), 4: (0.0, 10.0)}
        # Sensor reference: center of bottom edge (between nodes 1 & 2)
        self.sensor_xy = (area_size_m / 2.0, 0.0)

    def reset(self) -> None:
        self.tracker.reset()

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
        _, _, ddm = delay_doppler_map(cleaned, self.fs_hz)

        detections = detect_and_localize(
            cleaned,
            self.fs_hz,
            self.area_size_m,
            max_targets=self.max_targets,
            sensor_xy=self.sensor_xy,
        )

        # Fallback: if no delay peaks but clear motion, place targets from energy regions
        if not detections and m_energy > self.motion_threshold * 0.5:
            detections = _fallback_detections(cleaned, self.area_size_m, self.max_targets, self.sensor_xy)

        # Per-target vitals from subcarrier bands near each detection
        for i, det in enumerate(detections):
            delay_bin = int(det.get("delay_bin", i * 3 + 2))
            tv = extract_vitals_for_target(cleaned, self.fs_hz, delay_bin)
            det["respiration_bpm"] = tv["respiration_bpm"] or vitals["respiration_bpm"]
            det["heartbeat_bpm"] = tv["heartbeat_bpm"] or vitals["heartbeat_bpm"]
            if not motion and vitals["respiration_bpm"] > 0:
                det["velocity_mps"] = 0.0

        targets = self.tracker.update(detections, timestamp_sec)

        # Show only targets detected in THIS frame (not full tracker history)
        display_targets: list[Target] = []
        for det in detections:
            best = None
            best_d = 1.5
            for t in targets:
                d = np.hypot(t.x_m - det["x_m"], t.y_m - det["y_m"])
                if d < best_d:
                    best_d = d
                    best = t
            if best and best not in display_targets:
                display_targets.append(best)
            elif not best:
                display_targets.append(Target(
                    id=len(display_targets) + 1,
                    x_m=det["x_m"],
                    y_m=det["y_m"],
                    velocity_mps=det.get("velocity_mps", 0),
                    respiration_bpm=det.get("respiration_bpm", 0),
                    heartbeat_bpm=det.get("heartbeat_bpm", 0),
                    is_moving=det.get("velocity_mps", 0) > 0.08,
                ))

        # Session-level vitals: median across targets or global
        resp_bpm = vitals["respiration_bpm"]
        hr_bpm = vitals["heartbeat_bpm"]
        if targets:
            r_vals = [t.respiration_bpm for t in display_targets if t.respiration_bpm > 0]
            h_vals = [t.heartbeat_bpm for t in display_targets if t.heartbeat_bpm > 0]
            if r_vals:
                resp_bpm = float(np.median(r_vals))
            if h_vals:
                hr_bpm = float(np.median(h_vals))

        return SensingResult(
            timestamp_sec=timestamp_sec,
            motion_detected=motion,
            motion_energy=m_energy,
            target_count=len(detections),
            targets=display_targets,
            respiration_bpm=resp_bpm,
            heartbeat_bpm=hr_bpm,
            respiration_waveform=vitals["respiration_waveform"],
            heartbeat_waveform=vitals["heartbeat_waveform"],
            delay_doppler_map=ddm,
            events=list(self.tracker.events),
        )

    def process_session(
        self,
        csi: np.ndarray,
        timestamps_ms: np.ndarray,
        video_duration_sec: float | None = None,
    ) -> list[SensingResult]:
        """Slide window over CSI recording (trimmed to video duration)."""
        self.reset()
        results = []
        n = len(csi)
        if n < self.window_samples:
            self.window_samples = max(16, n)

        hop = max(self.window_samples // 4, 1)
        t0 = float(timestamps_ms[0]) if len(timestamps_ms) else 0.0

        for start in range(0, n - self.window_samples + 1, hop):
            end = start + self.window_samples
            t_sec = (float(timestamps_ms[start]) - t0) / 1000.0 if len(timestamps_ms) > start else start / self.fs_hz
            if video_duration_sec and t_sec > video_duration_sec:
                break
            res = self.process_window(csi[start:end], t_sec)
            results.append(res)

        if not results and n > 0:
            results.append(self.process_window(csi, 0.0))

        return results
