"""Autonomous mobile SAR mission controller — multi spiderbot + multi drone."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from .coverage import CoveragePlanner, Waypoint, reorder_waypoints_nearest
from .detection import SimulationDetector
from .fake_csi import FakeCsiGenerator
from .wifi_sensor import WiFiSensor
from .units import DroneUnit, SpiderbotUnit, UnitSpec, parse_units
from .world import DisasterWorld, load_world_config, world_from_dict


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
    units: list[UnitSpec] = field(default_factory=list)
    spiderbots: list[SpiderbotUnit] = field(default_factory=list)
    drones: list[DroneUnit] = field(default_factory=list)
    planner: CoveragePlanner | None = None
    fake_csi: FakeCsiGenerator | None = None
    stats: MissionStats = field(default_factory=MissionStats)
    _zone_config_path: str | None = None
    _detected_victims: set[int] = field(default_factory=set)
    _visited_cells: set[tuple[int, int]] = field(default_factory=set)
    _hold_target_sec: float = 3.5
    detector: SimulationDetector | None = None
    wifi: WiFiSensor | None = None
    _wifi_homing_threshold: float = 0.10
    _sim_time: float = 0.0

    @property
    def rover(self):
        return self.spiderbots[0].rover if self.spiderbots else None

    @property
    def drone(self):
        return self.drones[0].drone if self.drones else None

    @property
    def rover_node_id(self) -> int:
        return self.spiderbots[0].spec.node_id if self.spiderbots else 1

    @property
    def drone_node_id(self) -> int:
        return self.drones[0].spec.node_id if self.drones else 2

    @property
    def rover_waypoints(self) -> list:
        return self.spiderbots[0].waypoints if self.spiderbots else []

    @rover_waypoints.setter
    def rover_waypoints(self, wps: list) -> None:
        if self.spiderbots:
            self.spiderbots[0].waypoints = wps

    @property
    def drone_waypoints(self) -> list:
        return self.drones[0].waypoints if self.drones else []

    @drone_waypoints.setter
    def drone_waypoints(self, wps: list) -> None:
        if self.drones:
            self.drones[0].waypoints = wps

    def __post_init__(self) -> None:
        if not self.units:
            self.units = parse_units(None)
        if not self.spiderbots:
            self._init_units()
        if self.planner is None:
            self.planner = CoveragePlanner(self.world)
        if self.fake_csi is None:
            self._init_fake_csi()
        self._plan_paths()
        self._sim_time = 0.0
        self.stats.start_time = 0.0
        self._hold_target_sec = random.uniform(2.5, 4.0)
        if self.detector is None:
            self._sync_detection_radius()

    def _sync_detection_radius(self) -> None:
        radius = max(4.0, min(8.0, self.world.area_size_m * 0.16))
        sense = max(12.0, min(28.0, self.world.area_size_m * 0.55))
        self.detector = SimulationDetector(self.world, presence_radius_m=radius, confirm_threshold=0.55)
        self.wifi = WiFiSensor(self.world, sense_range_m=sense)
        if self.fake_csi is not None:
            self.fake_csi.presence_radius_m = radius

    def _polygon_centroid(self) -> tuple[float, float]:
        poly = self.world.zone_polygon
        if not poly:
            return 4.0, 4.0
        return sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)

    def _init_units(self) -> None:
        self.spiderbots = []
        self.drones = []
        cx, cy = self._polygon_centroid()
        offsets = [(0, 0), (3, 0), (-3, 0)]
        si = 0
        for spec in self.units:
            if not spec.enabled:
                continue
            if spec.is_spider:
                ox, oy = offsets[si % len(offsets)]
                rover = SpiderbotUnit(spec=spec)
                rover.rover.state.x = cx + ox
                rover.rover.state.y = cy + oy
                self.spiderbots.append(rover)
                si += 1
            elif spec.is_drone:
                du = DroneUnit(spec=spec)
                du.drone.state.x = cx
                du.drone.state.y = cy
                du.drone.state.z = 6.0
                self.drones.append(du)

    def _init_fake_csi(self) -> None:
        import yaml
        zone_path = Path(
            self._zone_config_path or Path(__file__).resolve().parents[1] / "config" / "disaster_zone.yaml"
        )
        mission_cfg = {}
        if zone_path.exists():
            with zone_path.open() as f:
                mission_cfg = (yaml.safe_load(f) or {}).get("mission", {})
        self.fake_csi = FakeCsiGenerator(
            self.world,
            vitals_stationary_sec=float(mission_cfg.get("vitals_stationary_sec", 3.0)),
            presence_radius_m=float(mission_cfg.get("presence_radius_m", 4.5)),
        )

    def _plan_paths(self) -> None:
        zone = self.world.zone_polygon
        ground_all = self.planner.ground_nav2_style(polygon=zone)
        if not ground_all:
            ground_all = self.planner.ground_patrol(polygon=zone)
        n_spiders = max(len(self.spiderbots), 1)
        n_drones = max(len(self.drones), 1)
        victim_wps = [Waypoint(v.x, v.y, 0.0) for v in self.world.victims]
        for i, sb in enumerate(self.spiderbots):
            chunk = [ground_all[j] for j in range(i, len(ground_all), n_spiders)]
            combined = chunk + victim_wps if victim_wps else chunk
            sb.waypoints = reorder_waypoints_nearest(combined, sb.rover.state.x, sb.rover.state.y)
        for i, dr in enumerate(self.drones):
            full = self.planner.drone_corner_coverage(altitude_m=8.0)
            if n_drones > 1:
                dr.waypoints = [full[j] for j in range(i, len(full), n_drones)]
            else:
                dr.waypoints = full
            dr.patrol_mode = "patrol"
            dr.drone.state.finished = False

    def apply_zone(self, zone_polygon: list[tuple[float, float]], ground_subcell: list[tuple[float, float]] | None = None) -> None:
        self.world.zone_polygon = zone_polygon
        if ground_subcell:
            self.world.ground_subcell = ground_subcell
        else:
            ys = [p[1] for p in zone_polygon]
            mid = (min(ys) + max(ys)) / 2.0
            self.world.ground_subcell = [(x, y) for x, y in zone_polygon if y <= mid + 0.01]
            if len(self.world.ground_subcell) < 3:
                self.world.ground_subcell = list(zone_polygon)
        self.planner = CoveragePlanner(self.world)
        self._sync_detection_radius()
        cx, cy = self._polygon_centroid()
        offsets = [(0, 0), (2.5, 0), (-2.5, 0)]
        si = 0
        for sb in self.spiderbots:
            ox, oy = offsets[si % len(offsets)]
            sb.rover.state.x = cx + ox
            sb.rover.state.y = cy + oy
            sb.rover.state.waypoint_idx = 0
            sb.rover.state.finished = False
            sb.rover.state.holding = False
            si += 1
        for dr in self.drones:
            dr.drone.state.x = cx
            dr.drone.state.y = cy
            dr.drone.state.waypoint_idx = 0
            dr.drone.state.finished = False
        self._plan_paths()

    @classmethod
    def from_config(cls, config_path: str | None = None, **kwargs) -> MobileMissionController:
        world = load_world_config(config_path)
        return cls(world=world, _zone_config_path=config_path, **kwargs)

    @classmethod
    def from_mission_dict(cls, cfg: dict, **kwargs) -> MobileMissionController:
        world = world_from_dict(cfg)
        units = parse_units(cfg.get("units"))
        return cls(world=world, units=units, **kwargs)

    def tick(self, dt: float, now: float | None = None) -> dict:
        self._sim_time += dt
        now = now if now is not None else self._sim_time
        for sb in self.spiderbots:
            self._step_spider(sb, dt, now)
            if self.detector is not None:
                st = sb.rover.state
                self.detector.scan(
                    sb.spec.node_id,
                    st.x,
                    st.y,
                    st.linear_mps,
                    st.holding,
                    dt,
                )
        for dr in self.drones:
            self._step_drone_unit(dr, dt, now)
            if self.detector is not None and not dr.drone.state.finished:
                st = dr.drone.state
                self.detector.scan(
                    dr.spec.node_id,
                    st.x,
                    st.y,
                    st.linear_mps * 0.5,
                    dr.patrol_mode == "hold",
                    dt,
                )
        if self.detector is not None:
            self._detected_victims = self.detector.confirmed_ids()
            self.stats.confirmed_detections = len(self._detected_victims)
        self._record_coverage()
        any_holding = any(sb.rover.state.holding for sb in self.spiderbots)
        all_done = (
            all(sb.rover.state.finished for sb in self.spiderbots)
            and all(dr.drone.state.finished for dr in self.drones)
        )
        if all_done:
            self.stats.completed = True
            self.stats.end_time = now
        phase = "complete" if self.stats.completed else ("holding" if any_holding else "patrol")
        return {
            "phase": phase,
            "elapsed_sec": round(now - self.stats.start_time, 1),
            "coverage_pct": round(self.stats.coverage_pct, 1),
            "confirmed_detections": self.stats.confirmed_detections,
            "units": [u.status_dict() for u in self.spiderbots] + [u.status_dict() for u in self.drones],
            "rover": self.spiderbots[0].status_dict() if self.spiderbots else {},
            "drone": self.drones[0].status_dict() if self.drones else {},
        }

    def inject_csi(self, rx, packets: int = 24) -> None:
        for sb in self.spiderbots:
            for _ in range(packets):
                row, ts, rssi = self.fake_csi.generate_packet(
                    sb.spec.node_id,
                    sb.rover.state.x,
                    sb.rover.state.y,
                    sb.rover.state.linear_mps,
                    sb.rover.state.angular_rps,
                    vitals_capable=True,
                )
                rx.inject(sb.spec.node_id, row, ts, rssi)

    def node_positions(self) -> dict[int, tuple[float, float]]:
        pos: dict[int, tuple[float, float]] = {}
        for sb in self.spiderbots:
            pos[sb.spec.node_id] = (sb.rover.state.x, sb.rover.state.y)
        for dr in self.drones:
            pos[dr.spec.node_id] = (dr.drone.state.x, dr.drone.state.y)
        return pos

    def get_sim_targets(self) -> list[dict]:
        if self.detector is None:
            return []
        return self.detector.targets()

    def get_wifi_signals(self) -> list[dict]:
        out = []
        for sb in self.spiderbots:
            if sb.wifi_signal < 0.05:
                continue
            out.append({
                "unit_id": sb.spec.id,
                "node_id": sb.spec.node_id,
                "type": "spiderbot",
                "x": sb.rover.state.x,
                "y": sb.rover.state.y,
                "strength": round(sb.wifi_signal, 3),
                "bearing_rad": round(sb.wifi_bearing, 4),
                "homing_victim_id": sb.homing_victim_id,
                "mode": sb.patrol_mode,
            })
        for dr in self.drones:
            if dr.drone.state.finished or dr.wifi_signal < 0.05:
                continue
            out.append({
                "unit_id": dr.spec.id,
                "node_id": dr.spec.node_id,
                "type": "drone",
                "x": dr.drone.state.x,
                "y": dr.drone.state.y,
                "strength": round(dr.wifi_signal, 3),
                "bearing_rad": round(dr.wifi_bearing, 4),
                "homing_victim_id": dr.homing_victim_id,
                "mode": dr.patrol_mode,
            })
        return out

    def _wifi_reading_spider(self, sb: SpiderbotUnit) -> None:
        if self.wifi is None:
            sb.wifi_signal = 0.0
            return
        reading = self.wifi.scan(sb.rover.state.x, sb.rover.state.y, self._detected_victims)
        if reading is None:
            sb.wifi_signal = 0.0
            sb.homing_victim_id = None
            return
        sb.wifi_signal = reading.strength
        sb.wifi_bearing = reading.bearing_rad
        sb.homing_victim_id = reading.victim_id

    def _wifi_reading_drone(self, dr: DroneUnit) -> None:
        if self.wifi is None or dr.drone.state.finished:
            dr.wifi_signal = 0.0
            return
        reading = self.wifi.scan(dr.drone.state.x, dr.drone.state.y, self._detected_victims)
        if reading is None:
            dr.wifi_signal = 0.0
            dr.homing_victim_id = None
            return
        dr.wifi_signal = reading.strength
        dr.wifi_bearing = reading.bearing_rad
        dr.homing_victim_id = reading.victim_id

    def _victim_by_id(self, vid: int):
        for v in self.world.victims:
            if v.id == vid:
                return v
        return None

    def _step_spider(self, sb: SpiderbotUnit, dt: float, now: float) -> None:
        rover = sb.rover
        if rover.state.finished:
            return
        self._wifi_reading_spider(sb)

        if rover.state.holding:
            rover.state.linear_mps = 0.0
            sb.patrol_mode = "hold"
            if now >= rover.state.hold_until:
                rover.state.holding = False
                sb.patrol_mode = "patrol"
                if sb.homing_victim_id and sb.homing_victim_id in self._detected_victims:
                    sb.homing_victim_id = None
                else:
                    rover.state.waypoint_idx += 1
                self._hold_target_sec = random.uniform(1.2, 2.0)
            return

        presence_r = self.fake_csi.presence_radius_m if self.fake_csi else 5.0

        if sb.wifi_signal >= self._wifi_homing_threshold and sb.homing_victim_id is not None:
            victim = self._victim_by_id(sb.homing_victim_id)
            if victim is not None:
                sb.patrol_mode = "homing"
                target = Waypoint(victim.x, victim.y, 0.0)
                rover.step_toward(target, dt)
                dist = math.hypot(victim.x - rover.state.x, victim.y - rover.state.y)
                if dist < presence_r * 0.85:
                    rover.state.holding = True
                    rover.state.hold_until = now + self._hold_target_sec
                    sb.patrol_mode = "hold"
                return

        sb.patrol_mode = "patrol"
        if rover.state.waypoint_idx >= len(sb.waypoints):
            rover.state.finished = True
            return
        target = sb.waypoints[rover.state.waypoint_idx]
        rover.step_toward(target, dt)
        arrival = max(1.0, min(2.5, self.world.area_size_m * 0.035))
        if math.hypot(target.x - rover.state.x, target.y - rover.state.y) < arrival:
            if self.fake_csi.presence_only(rover.state.x, rover.state.y):
                rover.state.holding = True
                rover.state.hold_until = now + self._hold_target_sec
                sb.patrol_mode = "hold"
            else:
                rover.state.waypoint_idx += 1

    def _step_drone_unit(self, dr: DroneUnit, dt: float, now: float) -> None:
        drone = dr.drone
        if drone.state.finished:
            dr.patrol_mode = "complete"
            return
        if not dr.waypoints:
            drone.state.finished = True
            dr.patrol_mode = "complete"
            return

        self._wifi_reading_drone(dr)
        presence_r = self.fake_csi.presence_radius_m if self.fake_csi else 5.0

        if (
            dr.wifi_signal >= self._wifi_homing_threshold
            and dr.homing_victim_id is not None
            and drone.state.waypoint_idx < len(dr.waypoints)
        ):
            victim = self._victim_by_id(dr.homing_victim_id)
            if victim is not None:
                dr.patrol_mode = "homing"
                target = Waypoint(victim.x, victim.y, drone.state.z)
                drone.step_toward(target, dt)
                dist = math.hypot(victim.x - drone.state.x, victim.y - drone.state.y)
                if dist < presence_r * 1.1:
                    dr.patrol_mode = "patrol"
                return

        dr.patrol_mode = "patrol"
        if drone.state.waypoint_idx >= len(dr.waypoints):
            drone.state.finished = True
            dr.patrol_mode = "complete"
            drone.state.linear_mps = 0.0
            return

        target = dr.waypoints[drone.state.waypoint_idx]
        drone.step_toward(target, dt)
        ddx = target.x - drone.state.x
        ddy = target.y - drone.state.y
        ddz = target.z - drone.state.z
        arrive = max(1.2, min(3.0, self.world.area_size_m * 0.04))
        if math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz) < arrive:
            drone.state.waypoint_idx += 1
            if drone.state.waypoint_idx >= len(dr.waypoints):
                drone.state.finished = True
                dr.patrol_mode = "complete"
                drone.state.linear_mps = 0.0

    def _record_coverage(self) -> None:
        for sb in self.spiderbots:
            self._visited_cells.add((int(sb.rover.state.x // 2), int(sb.rover.state.y // 2)))
        for dr in self.drones:
            for i in range(dr.drone.state.waypoint_idx + 1):
                if i < len(dr.waypoints):
                    wp = dr.waypoints[i]
                    self._visited_cells.add((int(wp.x // 2), int(wp.y // 2)))
        xmin, ymin, xmax, ymax = self.planner._bbox(self.world.zone_polygon)
        total = max(int((xmax - xmin) / 2) * int((ymax - ymin) / 2), 1)
        self.stats.coverage_pct = min(100.0, 100.0 * len(self._visited_cells) / total)
