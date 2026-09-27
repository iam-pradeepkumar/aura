"""Mobile CSI field engine — synthetic ingest + runtime node positions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .hardware_confirm import OccupancyConfirmFilter
from .hardware_live import LiveFieldEngine, load_field_config
from .hardware_state import NodePipelineState
from .mobile_positions import NodePositionStore
from .synthetic_receiver import SyntheticReceiver


@dataclass
class MobileFieldEngine(LiveFieldEngine):
    """LiveFieldEngine variant for Gazebo/mobile sim (no UDP)."""

    position_store: NodePositionStore = field(default_factory=NodePositionStore)
    _mobile_mode: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        hw = self.config.get("hardware", {})
        self._mobile_mode = str(hw.get("mode", "static")) == "mobile"
        if self._mobile_mode:
            hw.setdefault("min_node_votes", 1)
            hw.setdefault("motion_nodes_required", 1)
            hw.setdefault("confirm_frames", 1)
            hw.setdefault("min_confidence", 0.30)
        super().__post_init__()
        if self._mobile_mode:
            self._occupancy = OccupancyConfirmFilter(
                confirm_frames=int(hw.get("confirm_frames", 1)),
                clear_frames=int(hw.get("clear_frames", 2)),
                min_node_votes=int(hw.get("min_node_votes", 1)),
                min_confidence=float(hw.get("min_confidence", 0.30)),
                consensus_extra_frames=int(hw.get("consensus_extra_frames", 0)),
            )
        self.rx = SyntheticReceiver()
        self._started = True
        mobile_cfg = hw.get("mobile", {})
        roster_ids = mobile_cfg.get("node_ids")
        if roster_ids:
            self.expected_ids = [int(n) for n in roster_ids]
        else:
            self.expected_ids = [int(mobile_cfg.get("rover_node_id", 1))]
            if mobile_cfg.get("drone_relay_enabled", False):
                self.expected_ids.append(int(mobile_cfg.get("drone_node_id", 2)))
        for nid in self.expected_ids:
            self.rx.link_node(nid)
        self.node_pos = self.position_store.as_dict()

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False
        if self._v2_enricher is not None:
            self._v2_enricher.close()

    def update_node_positions(self, positions: dict[int, tuple[float, float]]) -> None:
        self.position_store.update(positions)
        self.node_pos = self.position_store.as_dict()
        for nid, state in self.node_states.items():
            state.pipeline.node_positions = self.node_pos

    def _node_state(self, nid: int) -> NodePipelineState:
        if nid not in self.node_states:
            hw = self.config.get("hardware", {})
            pipe_node_pos = self.position_store.as_dict()
            from .pipeline import AURAPipeline

            pipe = AURAPipeline(
                area_size_m=float(self.config.get("area_size_m", 10.0)),
                motion_threshold=float(self.config.get("motion_threshold", 0.02)),
                max_targets=int(self.config.get("max_people", 4)),
                node_positions=pipe_node_pos,
            )
            pipe._hw_allow_sector_fallback = True
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
                indoor_mode=bool(hw.get("indoor_mode", False)),
                sensing_engine=self._sensing_engine,
                v2_config=hw.get("sensing_v2", {}),
                position_store=self.position_store,
                mobile_mode=self._mobile_mode,
            )
            pipe._hw_motion_min = float(hw.get("motion_score_min", 0.58))
            pipe._hw_indoor_mode = bool(hw.get("indoor_mode", False))
        return self.node_states[nid]

    def process_frame(self) -> dict:
        self.node_pos = self.position_store.as_dict()
        frame = super().process_frame()
        frame["mode"] = "mobile"
        frame["node_positions"] = {int(k): [float(v[0]), float(v[1])] for k, v in self.node_pos.items()}
        return frame


def create_mobile_engine(config_path: str | None = None, zone_path: str | None = None) -> MobileFieldEngine:
    from pathlib import Path
    import yaml

    cfg = load_field_config(config_path)
    hw = cfg.setdefault("hardware", {})
    hw["mode"] = "mobile"
    hw.setdefault("min_node_votes", 1)
    hw.setdefault("motion_nodes_required", 1)
    hw.setdefault("confirm_frames", 1)
    mobile_cfg = hw.setdefault("mobile", {})
    zone_file = Path(zone_path or mobile_cfg.get("zone_config", "gazebo_sim/config/disaster_zone.yaml"))
    if not zone_file.is_absolute():
        zone_file = Path(__file__).resolve().parents[2] / zone_file
    if zone_file.exists():
        with zone_file.open() as f:
            zone = yaml.safe_load(f) or {}
        cfg["area_size_m"] = float(zone.get("area_size_m", cfg.get("area_size_m", 40.0)))
    store = NodePositionStore()
    rover_id = int(mobile_cfg.get("rover_node_id", 1))
    store.update({rover_id: (4.0, 4.0)})
    return MobileFieldEngine(config=cfg, position_store=store)
