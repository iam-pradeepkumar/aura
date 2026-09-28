"""Dashboard kinematic simulation tuning — faster patrol for visible map UX."""

from __future__ import annotations

import os

from .mission import MobileMissionController

_CLOUD = bool(os.environ.get("RENDER") or os.environ.get("AURA_CLOUD_MODE"))

# Wall-clock loop runs TICK_HZ; each frame advances TICK_HZ * TIME_SCALE sim-seconds.
if _CLOUD:
    TICK_HZ: float = 10.0
    TIME_SCALE: float = 6.0
    ROVER_SPEED_MPS: float = 7.0
    DRONE_SPEED_MPS: float = 22.0
    HOLD_SEC_MIN: float = 0.6
    HOLD_SEC_MAX: float = 1.0
    CSI_PACKETS_PER_TICK: int = 8
    ENGINE_FRAME_EVERY: int = 4
    WS_PUSH_HZ: float = 6.0
else:
    TICK_HZ: float = 20.0
    TIME_SCALE: float = 8.0
    ROVER_SPEED_MPS: float = 8.0
    DRONE_SPEED_MPS: float = 26.0
    HOLD_SEC_MIN: float = 0.8
    HOLD_SEC_MAX: float = 1.4
    CSI_PACKETS_PER_TICK: int = 32
    ENGINE_FRAME_EVERY: int = 1
    WS_PUSH_HZ: float = 10.0

CLOUD_MODE: bool = _CLOUD
MAX_PLANNING_AREA_M: float = 120.0
USE_FAST_PATH_PLANNING: bool = _CLOUD


def apply_dashboard_tuning(mission: MobileMissionController) -> None:
    """Speed up patrol + shorten holds for dashboard simulation only."""
    import random

    for sb in mission.spiderbots:
        sb.rover.speed_mps = ROVER_SPEED_MPS
    for dr in mission.drones:
        dr.drone.speed_mps = DRONE_SPEED_MPS
    mission._hold_target_sec = random.uniform(HOLD_SEC_MIN, HOLD_SEC_MAX)
    if mission.fake_csi is not None:
        mission.fake_csi.vitals_stationary_sec = 1.2
    if mission.detector is not None:
        mission.detector.confirm_threshold = 0.52
    mission._wifi_homing_threshold = 0.07
