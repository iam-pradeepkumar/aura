"""Mobile SAR unit definitions — spiderbots (CSI) and drones (coverage/relay)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .robots import AerialDrone, GroundRover, RobotState


@dataclass
class UnitSpec:
    id: str
    name: str
    type: str  # spiderbot | drone
    node_id: int
    enabled: bool = True

    @property
    def is_spider(self) -> bool:
        return self.type == "spiderbot"

    @property
    def is_drone(self) -> bool:
        return self.type == "drone"


DEFAULT_UNIT_ROSTER: list[dict] = [
    {"id": "spider-01", "name": "Spider-01", "type": "spiderbot", "node_id": 1, "enabled": True},
    {"id": "spider-02", "name": "Spider-02", "type": "spiderbot", "node_id": 3, "enabled": False},
    {"id": "spider-03", "name": "Spider-03", "type": "spiderbot", "node_id": 5, "enabled": False},
    {"id": "drone-alpha", "name": "Drone-Alpha", "type": "drone", "node_id": 2, "enabled": True},
    {"id": "drone-bravo", "name": "Drone-Bravo", "type": "drone", "node_id": 4, "enabled": False},
]


def parse_units(raw: list[dict] | None) -> list[UnitSpec]:
    if not raw:
        return [UnitSpec(**u) for u in DEFAULT_UNIT_ROSTER]
    out: list[UnitSpec] = []
    for u in raw:
        out.append(UnitSpec(
            id=str(u["id"]),
            name=str(u.get("name", u["id"])),
            type=str(u.get("type", "spiderbot")),
            node_id=int(u.get("node_id", 1)),
            enabled=bool(u.get("enabled", True)),
        ))
    return out


@dataclass
class SpiderbotUnit:
    spec: UnitSpec
    rover: GroundRover = field(default_factory=GroundRover)
    waypoints: list = field(default_factory=list)
    patrol_mode: str = "patrol"
    homing_victim_id: int | None = None
    wifi_signal: float = 0.0
    wifi_bearing: float = 0.0

    def status_dict(self) -> dict:
        s = self.rover.state
        if s.holding:
            phase = "HOLDING"
        elif self.patrol_mode == "homing":
            phase = "HOMING"
        elif s.finished:
            phase = "COMPLETE"
        else:
            phase = "PATROL"
        return {
            "id": self.spec.id,
            "name": self.spec.name,
            "type": "spiderbot",
            "node_id": self.spec.node_id,
            "status": phase,
            "patrol_mode": self.patrol_mode,
            "x": round(s.x, 3),
            "y": round(s.y, 3),
            "z": 0.0,
            "yaw": round(s.yaw, 3),
            "holding": s.holding,
            "finished": s.finished,
            "wifi_signal": round(self.wifi_signal, 3),
            "wifi_bearing": round(self.wifi_bearing, 3),
            "homing_victim_id": self.homing_victim_id,
            "sensors": ["CSI", "Motion", "Vitals"],
        }


@dataclass
class DroneUnit:
    spec: UnitSpec
    drone: AerialDrone = field(default_factory=AerialDrone)
    waypoints: list = field(default_factory=list)
    patrol_mode: str = "patrol"
    homing_victim_id: int | None = None
    wifi_signal: float = 0.0
    wifi_bearing: float = 0.0

    def status_dict(self) -> dict:
        s = self.drone.state
        if s.finished:
            phase = "COMPLETE"
        elif self.patrol_mode == "homing":
            phase = "HOMING"
        else:
            phase = "PATROL"
        return {
            "id": self.spec.id,
            "name": self.spec.name,
            "type": "drone",
            "node_id": self.spec.node_id,
            "status": phase,
            "patrol_mode": self.patrol_mode,
            "x": round(s.x, 3),
            "y": round(s.y, 3),
            "z": round(s.z, 2),
            "yaw": round(s.yaw, 3),
            "finished": s.finished,
            "wifi_signal": round(self.wifi_signal, 3),
            "wifi_bearing": round(self.wifi_bearing, 3),
            "homing_victim_id": self.homing_victim_id,
            "sensors": ["Relay", "Coverage"],
        }
