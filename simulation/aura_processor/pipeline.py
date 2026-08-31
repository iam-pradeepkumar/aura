"""AURA full sensing pipeline — CSI-only (simulation + live hardware)."""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from .srcc import srcc, motion_energy
from .doppler import delay_doppler_map
from .vitals import extract_vitals, extract_vitals_for_detections
from .csi_quality import assess_session, detection_confidence
from .multitarget import (
    detect_multinode_targets,
    detect_session_targets,
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
    confidence: float = 0.0


class AURAPipeline:
    def __init__(
        self,
        fs_hz: float = 20.0,
        area_size_m: float = 10.0,
        motion_threshold: float = 0.02,
        window_sec: float = 2.0,
        max_targets: int = 8,
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
        self._wimans_meta: dict = {}
        self.estimated_person_count: int = 0
        self.session_confidence: float = 0.0
        self.session_assessment: dict = {}

    def reset(self) -> None:
        self.tracker.reset()
        self._session_targets = []
        self._wimans_meta = {}
        self.estimated_person_count = 0
        self.session_confidence = 0.0
        self.session_assessment = {}

    def _sensor_xy(self, node_id: int) -> tuple[float, float]:
        return self.node_positions.get(node_id, self.sensor_xy)

    def set_session_targets(
        self,
        csi: np.ndarray,
        sensor_xy: tuple[float, float] | None = None,
        amplitude_count: int | None = None,
        wimans_amp: np.ndarray | None = None,
        wimans_label: str | None = None,
    ) -> None:
        """Pre-compute survivor positions from WiMANS-trained model + CSI."""
        xy = sensor_xy or self.sensor_xy
        prepared = np.nan_to_num(srcc(preprocess_csi(csi)))
        raw_motion = float(np.mean(motion_energy(prepared)))

        csi_dets = detect_session_targets(
            csi,
            self.fs_hz,
            self.area_size_m,
            self.max_targets,
            xy,
            motion_threshold=self.motion_threshold,
            node_positions=self.node_positions,
            amplitude_count=amplitude_count,
        )

        self._session_targets = csi_dets
        self._wimans_meta: dict = {}

        try:
            from wimans.infer import merge_with_csi_detections, model_available, predict_from_amplitude

            if wimans_amp is not None and model_available():
                wimans = predict_from_amplitude(
                    wimans_amp,
                    label_hint=wimans_label,
                    area_size_m=self.area_size_m,
                    fs_hz=self.fs_hz,
                )
                self._wimans_meta = wimans
                merged = merge_with_csi_detections(wimans, csi_dets, self.area_size_m)
                if wimans["count"] >= len(merged):
                    self._session_targets = wimans["targets"][: self.max_targets]
                else:
                    self._session_targets = merged[: self.max_targets]
                self.estimated_person_count = int(wimans["count"])
                self.session_confidence = max(
                    detection_confidence(self._session_targets, raw_motion, self.motion_threshold),
                    0.55,
                )
                return
        except ImportError:
            pass

        if not self._session_targets and raw_motion >= self.motion_threshold * 0.65:
            from .loader import amplitude_to_complex

            amp = np.abs(csi) if not np.iscomplexobj(csi) else np.abs(csi)
            if amp.ndim == 2 and amp.shape[1] >= 10:
                pseudo = amplitude_to_complex(amp)
                self._session_targets = detect_session_targets(
                    pseudo,
                    self.fs_hz,
                    self.area_size_m,
                    self.max_targets,
                    xy,
                    motion_threshold=self.motion_threshold,
                    node_positions=self.node_positions,
                    amplitude_count=amplitude_count,
                )
        self.estimated_person_count = len(self._session_targets)
        self.session_confidence = detection_confidence(
            self._session_targets, raw_motion, self.motion_threshold
        )

    def process_window(
        self,
        csi_window: np.ndarray,
        timestamp_sec: float,
        node_id: int = 1,
    ) -> SensingResult:
        prepared = preprocess_csi(csi_window)
        cleaned = np.nan_to_num(srcc(prepared))
        m_energy = float(np.mean(motion_energy(cleaned)))
        motion = m_energy > self.motion_threshold

        vitals = extract_vitals(cleaned, self.fs_hz)
        _, _, ddm = delay_doppler_map(cleaned, self.fs_hz)

        if not motion and not self._session_targets:
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
                confidence=0.0,
            )

        window_dets = detect_multinode_targets(
            cleaned,
            self.fs_hz,
            self.area_size_m,
            self.node_positions,
            self.max_targets,
            skip_srcc=True,
            motion_level=m_energy,
            motion_threshold=self.motion_threshold,
            count_limit=len(self._session_targets) if self._session_targets else None,
        )

        detections = self._merge_session_and_window(window_dets)
        conf = detection_confidence(detections, m_energy, self.motion_threshold)

        if conf < 0.12 and not self._session_targets and m_energy < self.motion_threshold * 0.8:
            detections = []

        per_vitals = extract_vitals_for_detections(cleaned, self.fs_hz, detections)
        for i, det in enumerate(detections):
            tv = per_vitals[i] if i < len(per_vitals) else {}
            if det.get("respiration_bpm", 0) <= 0:
                det["respiration_bpm"] = tv.get("respiration_bpm", 0.0)
            if det.get("heartbeat_bpm", 0) <= 0:
                det["heartbeat_bpm"] = tv.get("heartbeat_bpm", 0.0)
            det["respiration_waveform"] = tv.get("respiration_waveform")
            det["heartbeat_waveform"] = tv.get("heartbeat_waveform")
            if det.get("velocity_mps", 0) < 0.15:
                det["velocity_mps"] = 0.0

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
                best.respiration_waveform = det.get("respiration_waveform", best.respiration_waveform)
                best.heartbeat_waveform = det.get("heartbeat_waveform", best.heartbeat_waveform)
                display_targets.append(best)
            else:
                display_targets.append(Target(
                    id=len(display_targets) + 1,
                    x_m=det["x_m"],
                    y_m=det["y_m"],
                    velocity_mps=det.get("velocity_mps", 0),
                    respiration_bpm=det.get("respiration_bpm", 0),
                    heartbeat_bpm=det.get("heartbeat_bpm", 0),
                    respiration_waveform=det.get("respiration_waveform"),
                    heartbeat_waveform=det.get("heartbeat_waveform"),
                    is_moving=det.get("velocity_mps", 0) > 0.12,
                ))

        r_vals = [t.respiration_bpm for t in display_targets if t.respiration_bpm > 0]
        h_vals = [t.heartbeat_bpm for t in display_targets if t.heartbeat_bpm > 0]

        return SensingResult(
            timestamp_sec=timestamp_sec,
            motion_detected=motion,
            motion_energy=m_energy,
            target_count=len(self._session_targets) if self._session_targets else len(detections),
            targets=display_targets,
            respiration_bpm=float(np.median(r_vals)) if r_vals else 0.0,
            heartbeat_bpm=float(np.median(h_vals)) if h_vals else 0.0,
            respiration_waveform=None,
            heartbeat_waveform=None,
            delay_doppler_map=ddm,
            events=list(self.tracker.events),
            confidence=conf,
        )

    @property
    def person_count_estimate(self) -> int:
        return len(self._session_targets)

    def _merge_session_and_window(self, window_dets: list[dict]) -> list[dict]:
        """Use session-level CSI targets for count/position; window updates velocity only."""
        if not self._session_targets:
            return window_dets[: self.max_targets] if window_dets else []

        merged: list[dict] = []
        for s in self._session_targets[: self.max_targets]:
            d = dict(s)
            if window_dets:
                best = min(
                    window_dets,
                    key=lambda w: np.hypot(w["x_m"] - s["x_m"], w["y_m"] - s["y_m"]),
                )
                if np.hypot(best["x_m"] - s["x_m"], best["y_m"] - s["y_m"]) < 2.8:
                    d["velocity_mps"] = best.get("velocity_mps", 0.0)
            merged.append(d)
        return merged

    def process_session(
        self,
        csi: np.ndarray,
        timestamps_ms: np.ndarray,
        video_duration_sec: float | None = None,
        video_path: str | None = None,
        wimans_amp: np.ndarray | None = None,
        wimans_label: str | None = None,
    ) -> list[SensingResult]:
        self.reset()
        self.set_session_targets(
            csi,
            amplitude_count=amplitude_count,
            wimans_amp=wimans_amp,
            wimans_label=wimans_label,
        )

        prepared = np.nan_to_num(srcc(preprocess_csi(csi)))
        raw_motion = float(np.mean(motion_energy(prepared)))
        self.session_assessment = assess_session(
            csi,
            video_path,
            video_duration_sec or 1.0,
            self._session_targets,
            raw_motion,
            self.motion_threshold,
        )

        if (
            not self.session_assessment.get("reliable", True)
            and raw_motion < self.motion_threshold * 0.85
            and not self._session_targets
        ):
            self._session_targets = []
            self.estimated_person_count = 0
            self.session_confidence = 0.0
        elif self._session_targets:
            self.estimated_person_count = len(self._session_targets)
            self.session_confidence = max(
                self.session_confidence,
                detection_confidence(self._session_targets, raw_motion, self.motion_threshold),
            )

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

        return results

    def _result_from_detections(self, detections: list[dict], base: SensingResult) -> SensingResult:
        display = [
            Target(
                id=i + 1,
                x_m=d["x_m"],
                y_m=d["y_m"],
                velocity_mps=d.get("velocity_mps", 0),
                respiration_bpm=d.get("respiration_bpm", 0),
                heartbeat_bpm=d.get("heartbeat_bpm", 0),
                respiration_waveform=d.get("respiration_waveform"),
                heartbeat_waveform=d.get("heartbeat_waveform"),
                is_moving=d.get("velocity_mps", 0) > 0.12,
            )
            for i, d in enumerate(detections)
        ]
        r_vals = [t.respiration_bpm for t in display if t.respiration_bpm > 0]
        h_vals = [t.heartbeat_bpm for t in display if t.heartbeat_bpm > 0]
        return SensingResult(
            timestamp_sec=base.timestamp_sec,
            motion_detected=base.motion_detected or bool(detections),
            motion_energy=base.motion_energy,
            target_count=len(detections),
            targets=display,
            respiration_bpm=float(np.median(r_vals)) if r_vals else 0.0,
            heartbeat_bpm=float(np.median(h_vals)) if h_vals else 0.0,
            respiration_waveform=None,
            heartbeat_waveform=None,
            delay_doppler_map=base.delay_doppler_map,
            events=base.events,
            confidence=base.confidence,
        )
