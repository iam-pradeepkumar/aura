"""Shared live ESP32 field processing — used by tools/field_live.py."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import yaml

from . import AURAPipeline
from .hardware_confirm import OccupancyConfirmFilter
from .hardware_fusion import fuse_hardware_targets, fuse_motion_consensus
from .hardware_localize import refine_fused_targets
from .hardware_state import NodePipelineState
from .hardware_tracker import FieldTracker
from .serialize import _downsample, target_to_dict
from .wireless import DEFAULT_UDP_PORT, WirelessReceiver

PROCESSOR_VERSION = "2026.09.03-40"


def load_field_config(path: str | None = None) -> dict:
    from pathlib import Path

    cfg_path = Path(path or "simulation/config.yaml")
    if cfg_path.exists():
        with cfg_path.open() as f:
            return yaml.safe_load(f) or {}
    return {"area_size_m": 10.0, "motion_threshold": 0.02, "node_positions": {}, "hardware": {}}


@dataclass
class LiveFieldEngine:
    """UDP receiver + CSI pipelines for local matplotlib live view."""

    config: dict
    port: int = DEFAULT_UDP_PORT
    rx: WirelessReceiver = field(init=False)
    tracker: FieldTracker = field(init=False)
    node_states: dict[int, NodePipelineState] = field(default_factory=dict)
    _started: bool = field(default=False, init=False)
    _link_hold_until: dict[int, float] = field(default_factory=dict, init=False)
    _occupancy: OccupancyConfirmFilter = field(init=False)

    def __post_init__(self) -> None:
        hw = self.config.get("hardware", {})
        area = float(self.config.get("area_size_m", 10.0))
        self._occupancy = OccupancyConfirmFilter(
            confirm_frames=int(hw.get("confirm_frames", 3)),
            clear_frames=int(hw.get("clear_frames", 2)),
            min_node_votes=int(hw.get("min_node_votes", 2)),
            min_confidence=float(hw.get("min_confidence", 0.38)),
            consensus_extra_frames=int(hw.get("consensus_extra_frames", 1)),
        )
        self.rx = WirelessReceiver(port=self.port)
        self.tracker = FieldTracker(
            area_size_m=area,
            gate_m=float(hw.get("fusion_gate_m", 3.0)),
            max_targets=int(hw.get("max_people", self.config.get("max_people", 4))),
            trail_len=int(hw.get("trail_length", 40)),
            position_alpha=float(hw.get("tracker_alpha", 0.75)),
            max_miss_frames=int(hw.get("tracker_miss_frames", 4)),
            min_spawn_confidence=float(hw.get("min_confidence", 0.38)) * 0.9,
            min_trail_step_m=float(hw.get("min_trail_step_m", 0.18)),
        )
        self.expected_ids = sorted(int(k) for k in self.config.get("node_positions", {}).keys()) or list(
            range(1, int(hw.get("expected_nodes", 4)) + 1)
        )
        self.node_pos = {int(k): tuple(v) for k, v in self.config.get("node_positions", {}).items()}

    def start(self) -> None:
        if not self._started:
            self.rx.start()
            self._started = True

    def stop(self) -> None:
        if self._started:
            self.rx.stop()
            self._started = False

    def _node_state(self, nid: int) -> NodePipelineState:
        if nid not in self.node_states:
            hw = self.config.get("hardware", {})
            pipe = AURAPipeline(
                area_size_m=float(self.config.get("area_size_m", 10.0)),
                motion_threshold=float(self.config.get("motion_threshold", 0.02)),
                max_targets=int(self.config.get("max_people", 4)),
                node_positions=self.node_pos,
            )
            self.node_states[nid] = NodePipelineState(
                nid,
                pipe,
                min_packets=int(hw.get("min_packets", 12)),
                refresh_every=int(hw.get("refresh_every", 1)),
                motion_threshold_scale=float(hw.get("motion_threshold_scale", 1.0)),
                vitals_packets=int(hw.get("vitals_window_packets", 48)),
                motion_packets=int(hw.get("motion_packets", 24)),
                area_margin_m=float(hw.get("area_margin_m", 0.35)),
                max_per_node=int(hw.get("max_per_node", 1)),
                min_confidence=float(hw.get("min_confidence", 0.42)),
                motion_min=float(hw.get("motion_score_min", 0.58)),
            )
            pipe._hw_motion_min = float(hw.get("motion_score_min", 0.58))
            pipe._hw_allow_sector_fallback = bool(hw.get("allow_sector_fallback", False))
        return self.node_states[nid]

    def process_frame(self) -> dict:
        cfg = self.config
        hw_cfg = cfg.get("hardware", {})
        area = float(cfg.get("area_size_m", 10.0))
        min_pkts = int(hw_cfg.get("min_packets", 12))
        window_pkts = int(hw_cfg.get("window_packets", 24))
        motion_pkts = int(hw_cfg.get("motion_packets", 24))
        vitals_pkts = int(hw_cfg.get("vitals_window_packets", 48))
        link_timeout = float(hw_cfg.get("link_timeout_sec", 20.0))
        max_people = int(cfg.get("max_people", 4))
        fetch_n = max(window_pkts, vitals_pkts, motion_pkts)

        now = time.time()
        hold_grace = link_timeout * 1.25

        all_target_dicts: list[dict] = []
        per_node_counts: list[int] = []
        motion_active_nodes = 0
        max_motion_energy = 0.0
        rssi_by_node: dict[int, float] = {}
        resp_bpm = 0.0
        hr_bpm = 0.0
        resp_wave: list[float] = []
        hr_wave: list[float] = []
        best_vitals_score = 0.0
        node_status: list[dict] = []
        motion_nodes_required = int(hw_cfg.get("motion_nodes_required", 2))
        motion_score_min = float(hw_cfg.get("motion_score_min", 0.58))
        node_scores: dict[int, float] = {}
        strong_motion_nodes = 0
        motion = False

        for nid in self.expected_ids:
            link = self.rx.link_health(nid)
            rssi_val = self.rx.node_rssi(nid)
            ip = self.rx.node_source_ip(nid)
            rate = link.get("packet_rate_hz", 0)
            last = self.rx.node_last_seen.get(nid)
            age = now - last if last else 999.0
            if age < link_timeout:
                self._link_hold_until[nid] = now + hold_grace
            linked = now <= self._link_hold_until.get(nid, 0.0)
            buf_len = self.rx.buffer_length(nid)

            if not linked:
                node_status.append({
                    "id": nid,
                    "status": "offline" if age > link_timeout else "waiting",
                    "ip": ip,
                    "rssi": rssi_val,
                    "packet_rate_hz": rate,
                    "buffer": buf_len,
                    "age_sec": round(age, 1),
                })
                continue

            win = self.rx.get_node_window(nid, n=fetch_n, min_packets=min_pkts)
            if win is None:
                node_status.append({
                    "id": nid,
                    "status": f"buffering ({buf_len}/{min_pkts})",
                    "ip": ip,
                    "rssi": rssi_val,
                    "packet_rate_hz": rate,
                    "buffer": buf_len,
                })
                continue

            csi, ts, rssi_arr = win
            if rssi_arr is not None and len(rssi_arr):
                rssi_by_node[nid] = float(np.median(rssi_arr[-8:]))

            try:
                res = self._node_state(nid).process(csi, ts, rssi_arr)
            except Exception as exc:
                node_status.append({
                    "id": nid,
                    "status": f"error: {exc}",
                    "ip": ip,
                    "rssi": rssi_val,
                    "packet_rate_hz": rate,
                })
                continue

            if res is None:
                node_status.append({
                    "id": nid,
                    "status": "warming up",
                    "ip": ip,
                    "rssi": rssi_val,
                    "packet_rate_hz": rate,
                    "buffer": buf_len,
                })
                continue

            st = self.node_states[nid]
            node_score = float(st.last_motion_score)
            node_scores[nid] = node_score
            has_localized = res.target_count > 0
            node_has_motion = node_score >= motion_score_min * 0.88 or (
                bool(res.motion_detected) and node_score >= motion_score_min * 0.75
            )
            if node_has_motion:
                strong_motion_nodes += 1
                motion_active_nodes += 1
                motion = True
            node_motion = node_has_motion or has_localized
            max_motion_energy = max(max_motion_energy, float(res.motion_energy))
            if res.respiration_bpm > resp_bpm:
                resp_bpm = res.respiration_bpm
            if res.heartbeat_bpm > hr_bpm:
                hr_bpm = res.heartbeat_bpm
            if has_localized:
                per_node_counts.append(res.target_count)

            min_conf = float(hw_cfg.get("min_confidence", 0.38))
            for t in res.targets:
                td = target_to_dict(t)
                td["source_node"] = nid
                conf = round(max(float(td.get("confidence", 0)), res.confidence), 2)
                td["confidence"] = conf
                if conf >= min_conf * 0.82 and node_score >= motion_score_min * 0.75:
                    all_target_dicts.append(td)

            if res.respiration_waveform is not None and len(res.respiration_waveform):
                score = float(res.respiration_bpm) * float(res.confidence)
                if score >= best_vitals_score:
                    best_vitals_score = score
                    resp_wave = _downsample(res.respiration_waveform)
                    hr_wave = (
                        _downsample(res.heartbeat_waveform)
                        if res.heartbeat_waveform is not None
                        else []
                    )

            node_status.append({
                "id": nid,
                "status": "active",
                "ip": ip,
                "rssi": rssi_val,
                "packet_rate_hz": rate,
                "motion": node_motion,
                "motion_score": round(float(st.last_motion_score), 3),
                "count": res.target_count,
                "respiration_bpm": round(res.respiration_bpm, 1),
                "heartbeat_bpm": round(res.heartbeat_bpm, 1),
                "buffer": buf_len,
            })

        fused = fuse_hardware_targets(
            all_target_dicts,
            area_size_m=area,
            gate_m=float(hw_cfg.get("fusion_gate_m", 3.0)),
            area_margin_m=float(hw_cfg.get("area_margin_m", 0.35)),
            min_node_votes=int(hw_cfg.get("min_node_votes", 2)),
            min_confidence=float(hw_cfg.get("min_confidence", 0.38)),
            max_people=int(hw_cfg.get("max_people", max_people)),
            motion_active_nodes=motion_active_nodes,
        )

        if not fused and bool(hw_cfg.get("allow_motion_consensus", True)):
            fused = fuse_motion_consensus(
                node_scores,
                self.node_pos,
                area,
                margin_m=float(hw_cfg.get("area_margin_m", 0.35)),
                motion_min=motion_score_min,
                min_nodes=int(hw_cfg.get("motion_nodes_required", 2)),
            )

        fused = refine_fused_targets(
            fused,
            rssi_by_node,
            self.node_pos,
            area,
            margin_m=float(hw_cfg.get("area_margin_m", 0.35)),
        )

        confirmed = self._occupancy.apply(fused)
        if self._occupancy.should_reset_tracker():
            self.tracker.reset()

        tracked = self.tracker.update(confirmed, now) if confirmed else []
        target_count = len(tracked) if confirmed else 0

        motion_confirmed = target_count > 0 and (
            strong_motion_nodes >= motion_nodes_required or any(
                t.get("node_votes", 0) >= 2 for t in tracked
            )
        )

        if target_count <= 0:
            resp_bpm = 0.0
            hr_bpm = 0.0
            resp_wave = []
            hr_wave = []
        else:
            for t in tracked:
                if not t.get("respiration_bpm") and resp_bpm > 0:
                    t["respiration_bpm"] = round(resp_bpm, 1)
                if not t.get("heartbeat_bpm") and hr_bpm > 0:
                    t["heartbeat_bpm"] = round(hr_bpm, 1)
                if not t.get("respiration_waveform") and resp_wave:
                    t["respiration_waveform"] = resp_wave
                if not t.get("heartbeat_waveform") and hr_wave:
                    t["heartbeat_waveform"] = hr_wave

        linked_count = sum(
            1 for nid in self.expected_ids
            if now <= self._link_hold_until.get(nid, 0.0)
        )
        sensing_count = sum(1 for n in node_status if n["status"] == "active")
        packets = sum(self.rx.node_packet_count.values())

        return {
            "processor_version": PROCESSOR_VERSION,
            "timestamp": now,
            "active_nodes": linked_count,
            "linked_nodes": linked_count,
            "sensing_nodes": sensing_count,
            "expected_nodes": len(self.expected_ids),
            "total_packets": packets,
            "motion_detected": motion_confirmed,
            "motion_energy": round(max_motion_energy, 5),
            "motion_nodes": motion_active_nodes,
            "target_count": target_count,
            "respiration_bpm": round(resp_bpm, 1),
            "heartbeat_bpm": round(hr_bpm, 1),
            "respiration_waveform": resp_wave,
            "heartbeat_waveform": hr_wave,
            "targets": tracked,
            "node_status": node_status,
            "node_positions": self.node_pos,
            "area_size_m": area,
            "events": self.tracker.events[-8:],
            "warnings": self.rx.system_warnings(self.expected_ids, timeout_sec=link_timeout),
        }
