"""Dashboard kinematic simulation tuning — faster patrol for visible map UX."""

from __future__ import annotations

from .mission import MobileMissionController

# Wall-clock loop runs TICK_HZ; each frame advances TICK_HZ * TIME_SCALE sim-seconds.
TICK_HZ: float = 20.0
TIME_SCALE: float = 6.0          # 6× faster than real time on the map
ROVER_SPEED_MPS: float = 5.5
DRONE_SPEED_MPS: float = 16.0
HOLD_SEC_MIN: float = 1.2
HOLD_SEC_MAX: float = 2.0
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
        mission.detector.confirm_threshold = 0.58
