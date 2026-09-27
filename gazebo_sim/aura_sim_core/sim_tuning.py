"""Dashboard kinematic simulation tuning — faster patrol for visible map UX."""

from __future__ import annotations

from .mission import MobileMissionController

# Wall-clock loop runs TICK_HZ; each frame advances TICK_HZ * TIME_SCALE sim-seconds.
TICK_HZ: float = 20.0
TIME_SCALE: float = 8.0          # 8× sim speed on the map
ROVER_SPEED_MPS: float = 8.0
DRONE_SPEED_MPS: float = 26.0
HOLD_SEC_MIN: float = 0.8
HOLD_SEC_MAX: float = 1.4
CSI_PACKETS_PER_TICK: int = 32


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
