"""Autonomous mobile SAR mission controller."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from .coverage import CoveragePlanner, Waypoint
from .fake_csi import FakeCsiGenerator
from .robots import AerialDrone, GroundRover
from .world import DisasterWorld, load_world_config


@dataclass
class MissionStats:
    start_time: float = 0.0
    end_time: float = 0.0
    coverage_pct: float = 0.0
    confirmed_detections: int = 0
    completed: bool = False


@dataclass
class MobileMissionController:
    world: DisasterWorld
    rover_node_id: int = 1
    drone_node_id: int = 2
    rover: GroundRover = field(default_factory=GroundRover)
    drone: AerialDrone = field(default_factory=AerialDrone)
    planner: CoveragePlanner | None = None
    fake_csi: FakeCsiGenerator | None = None
    rover_waypoints: list[Waypoint] = field(default_factory=list)
    drone_waypoints: list[Waypoint] = field(default_factory=list)
    stats: MissionStats = field(default_factory=MissionStats)
    _zone_config_path: str | None = None
    _detected_victims: set[int] = field(default_factory=set)
    _visited_cells: set[tuple[int, int]] = field(default_factory=set)
    _hold_target_sec: float = 6.0

    def __post_init__(self) -> None:
        if self.planner is None:
            self.planner = CoveragePlanner(self.world)
        if self.fake_csi is None:
            import yaml
            zone_path = Path(
                self._zone_config_path or Path(__file__).resolve().parents[1] / "config" / "disaster_zone.yaml"
            )
            mission_cfg = {}
            if zone_path.exists():
                with zone_path.open() as f:
                    mission_cfg = (yaml.safe_load(f) or {}).get("mission", {})
            vitals_sec = float(mission_cfg.get("vitals_stationary_sec", 3.0))
            presence = float(mission_cfg.get("presence_radius_m", 4.5))
            self.fake_csi = FakeCsiGenerator(
                self.world,
                vitals_stationary_sec=vitals_sec,
                presence_radius_m=presence,
            )
        self.rover_waypoints = self.planner.ground_nav2_style()
        alt = 6.0
        self.drone_waypoints = self.planner.drone_lawnmower(altitude_m=alt)
        self.stats.start_time = time.time()
        self._hold_target_sec = random.uniform(5.0, 8.0)

    @classmethod
    def from_config(cls, config_path: str | None = None, **kwargs) -> MobileMissionController:
        world = load_world_config(config_path)
        return cls(world=world, _zone_config_path=config_path, **kwargs)

    def tick(self, dt: float, now: float | None = None) -> dict:
        now = now or time.time()
        self._step_rover(dt, now)
        self._step_drone(dt)
        self._record_coverage()
        phase = "complete" if self.stats.completed else ("holding" if self.rover.state.holding else "patrol")
        if self.rover.state.finished and self.drone.state.finished:
            self.stats.completed = True
            self.stats.end_time = now
        return {
            "phase": phase,
            "elapsed_sec": round(now - self.stats.start_time, 1),
            "coverage_pct": round(self.stats.coverage_pct, 1),
            "confirmed_detections": self.stats.confirmed_detections,
            "rover": {
                "x": round(self.rover.state.x, 2),
                "y": round(self.rover.state.y, 2),
                "holding": self.rover.state.holding,
                "finished": self.rover.state.finished,
            },
            "drone": {
                "x": round(self.drone.state.x, 2),
                "y": round(self.drone.state.y, 2),
                "z": round(self.drone.state.z, 2),
                "waypoint_idx": self.drone.state.waypoint_idx,
                "finished": self.drone.state.finished,
            },
        }

    def inject_csi(self, rx, packets: int = 24) -> None:
        """Feed synthetic CSI into SyntheticReceiver for aura_processor."""
        for _ in range(packets):
            row, ts, rssi = self.fake_csi.generate_packet(
                self.rover_node_id,
                self.rover.state.x,
                self.rover.state.y,
                self.rover.state.linear_mps,
                self.rover.state.angular_rps,
                vitals_capable=True,
            )
            rx.inject(self.rover_node_id, row, ts, rssi)

    def node_positions(self) -> dict[int, tuple[float, float]]:
        return {
            self.rover_node_id: (self.rover.state.x, self.rover.state.y),
            self.drone_node_id: (self.drone.state.x, self.drone.state.y),
        }

    def _step_rover(self, dt: float, now: float) -> None:
        if self.rover.state.finished:
            return
        if self.rover.state.holding:
            if now >= self.rover.state.hold_until:
                self.rover.state.holding = False
                self.rover.state.waypoint_idx += 1
                self._hold_target_sec = random.uniform(5.0, 8.0)
            return
        if self.rover.state.waypoint_idx >= len(self.rover_waypoints):
            self.rover.state.finished = True
            return
        target = self.rover_waypoints[self.rover.state.waypoint_idx]
        self.rover.step_toward(target, dt)
        if math.hypot(target.x - self.rover.state.x, target.y - self.rover.state.y) < 0.3:
            if self.fake_csi.presence_only(self.rover.state.x, self.rover.state.y):
                self.rover.state.holding = True
                self.rover.state.hold_until = now + self._hold_target_sec
                victim, _ = self.world.nearest_victim(self.rover.state.x, self.rover.state.y)
                if victim:
                    self._detected_victims.add(victim.id)
                    self.stats.confirmed_detections = len(self._detected_victims)
            else:
                self.rover.state.waypoint_idx += 1

    def _step_drone(self, dt: float) -> None:
        if self.drone.state.finished or not self.drone_waypoints:
            self.drone.state.finished = True
            return
        if self.drone.state.waypoint_idx >= len(self.drone_waypoints):
            self.drone.state.finished = True
            return
        target = self.drone_waypoints[self.drone.state.waypoint_idx]
        self.drone.step_toward(target, dt)
        ddx = target.x - self.drone.state.x
        ddy = target.y - self.drone.state.y
        ddz = target.z - self.drone.state.z
        if math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz) < 0.4:
            self.drone.state.waypoint_idx += 1

    def _record_coverage(self) -> None:
        cell = (int(self.rover.state.x // 2), int(self.rover.state.y // 2))
        self._visited_cells.add(cell)
        for i in range(self.drone.state.waypoint_idx + 1):
            if i < len(self.drone_waypoints):
                wp = self.drone_waypoints[i]
                self._visited_cells.add((int(wp.x // 2), int(wp.y // 2)))
        xmin, ymin, xmax, ymax = self.planner._bbox(self.world.zone_polygon)
        total = max(int((xmax - xmin) / 2) * int((ymax - ymin) / 2), 1)
        self.stats.coverage_pct = min(100.0, 100.0 * len(self._visited_cells) / total)
