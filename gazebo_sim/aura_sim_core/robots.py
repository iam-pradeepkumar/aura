"""Kinematic ground rover + drone for standalone and Gazebo bridge."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .coverage import Waypoint


@dataclass
class RobotState:
    x: float
    y: float
    z: float = 0.0
    yaw: float = 0.0
    linear_mps: float = 0.0
    angular_rps: float = 0.0
    waypoint_idx: int = 0
    holding: bool = False
    hold_until: float = 0.0
    finished: bool = False


@dataclass
class GroundRover:
    state: RobotState = field(default_factory=lambda: RobotState(4.0, 4.0))
    speed_mps: float = 0.6

    def step_toward(self, target: Waypoint, dt: float) -> None:
        if self.state.holding:
            self.state.linear_mps = 0.0
            self.state.angular_rps = 0.0
            return
        dx = target.x - self.state.x
        dy = target.y - self.state.y
        dist = math.hypot(dx, dy)
        if dist < 0.25:
            self.state.linear_mps = 0.0
            self.state.angular_rps = 0.0
            return
        step = min(self.speed_mps * dt, dist)
        self.state.x += dx / dist * step
        self.state.y += dy / dist * step
        self.state.yaw = math.atan2(dy, dx)
        self.state.linear_mps = step / max(dt, 1e-6)
        self.state.angular_rps = 0.0


@dataclass
class AerialDrone:
    state: RobotState = field(default_factory=lambda: RobotState(4.0, 4.0, z=6.0))
    speed_mps: float = 2.5

    def step_toward(self, target: Waypoint, dt: float) -> None:
        dx = target.x - self.state.x
        dy = target.y - self.state.y
        dz = target.z - self.state.z
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist < 0.35:
            self.state.linear_mps = 0.0
            return
        step = min(self.speed_mps * dt, dist)
        self.state.x += dx / dist * step
        self.state.y += dy / dist * step
        self.state.z += dz / dist * step
        self.state.linear_mps = step / max(dt, 1e-6)
