"""AURA full sensing pipeline — CSI-only (simulation + live hardware)."""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from .srcc import srcc, motion_energy
from .doppler import delay_doppler_map
from .vitals import extract_vitals, extract_vitals_for_target
from .multitarget import (
    detect_and_localize,
    detect_session_targets,
    estimate_person_count,
    force_csi_targets,
    preprocess_csi,
)
from .localization import TargetTracker, Target


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
        self.node_positions = node_positions or {
            1: (0.0, 0.0), 2: (10.0, 0.0), 3: (10.0, 10.0), 4: (0.0, 10.0)
        }
        self.sensor_xy = (area_size_m / 2.0, 0.0)
        self._session_targets: list[dict] = []
        self.estimated_person_count: int = 0

    def reset(self) -> None:
        self.tracker.reset()
        self._session_targets = []

    def _sensor_xy(self, node_id: int) -> tuple[float, float]:
        return self.node_positions.get(node_id, self.sensor_xy)

    def set_session_targets(
        self,
        csi: np.ndarray,
        sensor_xy: tuple[float, float] | None = None,
    ) -> None:
        """Pre-compute stable CSI-only survivor positions from buffered packets."""
        xy = sensor_xy or self.sensor_xy
        prepared = np.nan_to_num(srcc(preprocess_csi(csi)))
        raw_motion = float(np.mean(motion_energy(np.nan_to_num(srcc(csi)))))
        self.estimated_person_count = estimate_person_count(
            prepared, raw_motion, self.motion_threshold, max_people=self.max_targets
        )
        if self.estimated_person_count == 0 and raw_motion >= self.motion_threshold:
            self.estimated_person_count = max(1, min(self.max_targets, 2))
        active_max = self.estimated_person_count if self.estimated_person_count > 0 else self.max_targets
        self._session_targets = detect_session_targets(
            csi,
            self.fs_hz,
            self.area_size_m,
            active_max,
            xy,
            motion_threshold=self.motion_threshold,
            expected_count=self.estimated_person_count,
        )
        if not self._session_targets and raw_motion >= self.motion_threshold:
            self._session_targets = force_csi_targets(
                prepared, self.fs_hz, self.area_size_m, active_max, xy, raw_motion, self.motion_threshold
            )

    def process_window(
        self,
        csi_window: np.ndarray,
        timestamp_sec: float,
        node_id: int = 1,
    ) -> SensingResult:
        sensor_xy = self._sensor_xy(node_id)
        prepared = preprocess_csi(csi_window)
        cleaned = np.nan_to_num(srcc(prepared))
        m_energy = float(np.mean(motion_energy(np.nan_to_num(srcc(csi_window)))))
        motion = m_energy > self.motion_threshold

        vitals = extract_vitals(cleaned, self.fs_hz)
        _, _, ddm = delay_doppler_map(cleaned, self.fs_hz)

        if not motion and self.estimated_person_count == 0:
            return SensingResult(
                timestamp_sec=timestamp_sec,
                motion_detected=False,
                motion_energy=m_energy,
                target_count=0,
                targets=[],
                respiration_bpm=vitals["respiration_bpm"],
                heartbeat_bpm=vitals["heartbeat_bpm"],
                respiration_waveform=vitals["respiration_waveform"],
                heartbeat_waveform=vitals["heartbeat_waveform"],
                delay_doppler_map=ddm,
                events=list(self.tracker.events),
            )

        active_max = self.estimated_person_count if self.estimated_person_count > 0 else self.max_targets
        window_dets = detect_and_localize(
            cleaned,
            self.fs_hz,
            self.area_size_m,
            active_max,
            sensor_xy,
            skip_srcc=True,
            require_motion=True,
            motion_level=m_energy,
            motion_threshold=self.motion_threshold,
        )

        detections = self._merge_session_and_window(window_dets)

        if not detections and self._session_targets:
            detections = [dict(s) for s in self._session_targets[: self.max_targets]]

        if self.estimated_person_count > 0 and len(detections) > self.estimated_person_count:
            detections = sorted(
                detections,
                key=lambda d: -float(d.get("confidence", d.get("weight", 0))),
            )[: self.estimated_person_count]

        # Motion confirmed but no peaks yet — retry with relaxed gates
        if motion and not detections:
            detections = detect_and_localize(
                cleaned,
                self.fs_hz,
                self.area_size_m,
                active_max,
                sensor_xy,
                skip_srcc=True,
                require_motion=True,
                motion_level=m_energy * 1.1,
                motion_threshold=self.motion_threshold * 0.75,
            )

        if motion and not detections:
            detections = force_csi_targets(
                cleaned, self.fs_hz, self.area_size_m, active_max, sensor_xy, m_energy, self.motion_threshold
            )

        if motion and not detections and self._session_targets:
            detections = [dict(s) for s in self._session_targets[:active_max]]

        for det in detections:
            delay_bin = int(det.get("delay_bin", 0))
            tv = extract_vitals_for_target(cleaned, self.fs_hz, delay_bin)
            if det.get("velocity_mps", 0) < 0.15:
                det["respiration_bpm"] = tv["respiration_bpm"] or vitals["respiration_bpm"]
                det["heartbeat_bpm"] = tv["heartbeat_bpm"] or vitals["heartbeat_bpm"]
                det["velocity_mps"] = 0.0
            else:
                det["respiration_bpm"] = tv["respiration_bpm"]
                det["heartbeat_bpm"] = tv["heartbeat_bpm"] or vitals["heartbeat_bpm"]

        targets = self.tracker.update(detections, timestamp_sec)

        display_targets: list[Target] = []
        for det in detections:
            best = None
            best_d = 2.0
            for t in targets:
                d = np.hypot(t.x_m - det["x_m"], t.y_m - det["y_m"])
                if d < best_d:
                    best_d = d
                    best = t
            if best and best not in display_targets:
                best.is_moving = det.get("velocity_mps", 0) > 0.12
                best.respiration_bpm = det.get("respiration_bpm", best.respiration_bpm)
                best.heartbeat_bpm = det.get("heartbeat_bpm", best.heartbeat_bpm)
                display_targets.append(best)
            else:
                display_targets.append(Target(
                    id=len(display_targets) + 1,
                    x_m=det["x_m"],
                    y_m=det["y_m"],
                    velocity_mps=det.get("velocity_mps", 0),
                    respiration_bpm=det.get("respiration_bpm", 0),
                    heartbeat_bpm=det.get("heartbeat_bpm", 0),
                    is_moving=det.get("velocity_mps", 0) > 0.12,
                ))

        resp_bpm = vitals["respiration_bpm"]
        hr_bpm = vitals["heartbeat_bpm"]
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

    @property
    def person_count_estimate(self) -> int:
        return self.estimated_person_count or len(self._session_targets)

    def _merge_session_and_window(self, window_dets: list[dict]) -> list[dict]:
        if not self._session_targets:
            return window_dets[: self.max_targets]

        merged: list[dict] = []
        used_window: set[int] = set()

        for sess in self._session_targets:
            best = None
            best_d = 2.5
            for i, wd in enumerate(window_dets):
                if i in used_window:
                    continue
                d = (wd["x_m"] - sess["x_m"]) ** 2 + (wd["y_m"] - sess["y_m"]) ** 2
                if d < best_d:
                    best_d = d
                    best = (i, wd)

            if best:
                i, wd = best
                used_window.add(i)
                merged.append({
                    **sess,
                    "x_m": wd["x_m"],
                    "y_m": wd["y_m"],
                    "velocity_mps": wd.get("velocity_mps", sess.get("velocity_mps", 0)),
                })
            else:
                merged.append(dict(sess))

        for i, wd in enumerate(window_dets):
            if i not in used_window and len(merged) < self.max_targets:
                merged.append(wd)

        return merged[: self.max_targets]

    def process_session(
        self,
        csi: np.ndarray,
        timestamps_ms: np.ndarray,
        video_duration_sec: float | None = None,
    ) -> list[SensingResult]:
        self.reset()
        self.set_session_targets(csi)

        results = []
        n = len(csi)
        desired_window = max(int(2.5 * self.fs_hz), 48)
        self.window_samples = min(desired_window, max(48, n // 2))
        if n < self.window_samples:
            self.window_samples = max(48, n // 2)

        hop = max(self.window_samples // 4, 1)
        t0 = float(timestamps_ms[0]) if len(timestamps_ms) else 0.0

        for start in range(0, n - self.window_samples + 1, hop):
            end = start + self.window_samples
            t_sec = (float(timestamps_ms[start]) - t0) / 1000.0 if len(timestamps_ms) > start else start / self.fs_hz
            if video_duration_sec and t_sec > video_duration_sec:
                break
            results.append(self.process_window(csi[start:end], t_sec))

        if not results and n > 0:
            results.append(self.process_window(csi, 0.0))

        # Ensure every frame carries session targets when motion was detected
        if self._session_targets and results:
            session_dets = [dict(s) for s in self._session_targets]
            for i, res in enumerate(results):
                if res.target_count == 0:
                    results[i] = self._result_from_detections(session_dets, res)
            if all(r.target_count == 0 for r in results):
                full = self.process_window(csi, 0.0)
                if full.target_count == 0:
                    full = self._result_from_detections(session_dets, full)
                results[0] = full

        return results

    def _result_from_detections(self, detections: list[dict], base: SensingResult) -> SensingResult:
        display = [
            Target(
                id=i + 1,
                x_m=d["x_m"],
                y_m=d["y_m"],
                velocity_mps=d.get("velocity_mps", 0),
                respiration_bpm=d.get("respiration_bpm", base.respiration_bpm),
                heartbeat_bpm=d.get("heartbeat_bpm", base.heartbeat_bpm),
                is_moving=d.get("velocity_mps", 0) > 0.12,
            )
            for i, d in enumerate(detections)
        ]
        return SensingResult(
            timestamp_sec=base.timestamp_sec,
            motion_detected=base.motion_detected or bool(detections),
            motion_energy=base.motion_energy,
            target_count=len(detections),
            targets=display,
            respiration_bpm=base.respiration_bpm,
            heartbeat_bpm=base.heartbeat_bpm,
            respiration_waveform=base.respiration_waveform,
            heartbeat_waveform=base.heartbeat_waveform,
            delay_doppler_map=base.delay_doppler_map,
            events=base.events,
        )
