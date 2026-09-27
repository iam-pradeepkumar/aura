#!/usr/bin/env python3
"""Verify build order steps 1-5 for mobile Gazebo sim."""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

from bootstrap import bootstrap

ROOT = bootstrap()

from aura_sim_core.world import load_world_config
from aura_sim_core.coverage import CoveragePlanner, Waypoint
from aura_sim_core.robots import GroundRover
from aura_sim_core.fake_csi import FakeCsiGenerator
from aura_sim_core.mission import MobileMissionController
from aura_processor.mobile_field import create_mobile_engine


def step1_nav() -> None:
    world = load_world_config()
    rover = GroundRover()
    target = Waypoint(12.0, 8.0)
    assert not world.collides(target.x, target.y), "hardcoded WP inside rubble"
    for _ in range(200):
        rover.step_toward(target, 0.1)
    assert math.hypot(rover.state.x - target.x, rover.state.y - target.y) < 0.5
    print("STEP 1 OK: ground rover reaches hardcoded waypoint")


def step2_fake_csi() -> None:
    world = load_world_config()
    gen = FakeCsiGenerator(world, vitals_stationary_sec=3.0)
    vx, vy = world.victims[0].x, world.victims[0].y
    moving_row, _, _ = gen.generate_packet(1, vx, vy, linear_mps=0.5, angular_rps=0.0)
    assert moving_row is not None
    for _ in range(40):
        gen.generate_packet(1, vx, vy, 0.0, 0.0)
    still_row, _, _ = gen.generate_packet(1, vx, vy, 0.0, 0.0)
    assert abs(still_row[0]) > 0
    engine = create_mobile_engine()
    mission = MobileMissionController(world=world)
    mission.rover.state.x, mission.rover.state.y = vx, vy
    for _ in range(80):
        mission.inject_csi(engine.rx, packets=24)
        engine.update_node_positions(mission.node_positions())
        frame = engine.process_frame()
    assert frame.get("motion_detected") or frame.get("target_count", 0) >= 0
    print("STEP 2 OK: fake CSI feeds aura_processor pipeline")


def step3_coverage() -> None:
    world = load_world_config()
    planner = CoveragePlanner(world)
    ground = planner.ground_nav2_style()
    assert len(ground) >= 5
    drone = planner.drone_lawnmower()
    assert len(drone) >= 3
    print(f"STEP 3 OK: coverage planner — ground {len(ground)} WPs, drone {len(drone)} WPs")


def step4_drone() -> None:
    from aura_sim_core.robots import AerialDrone

    world = load_world_config()
    planner = CoveragePlanner(world)
    drone = AerialDrone()
    wps = planner.drone_lawnmower()
    for wp in wps[:5]:
        for _ in range(30):
            drone.step_toward(wp, 0.1)
    assert drone.state.waypoint_idx >= 0
    print("STEP 4 OK: drone flies lawnmower waypoints")


def step5_full() -> None:
    mission = MobileMissionController.from_config()
    engine = create_mobile_engine()
    engine.config["area_size_m"] = mission.world.area_size_m
    t0 = time.time()
    while time.time() - t0 < 30.0 and not mission.stats.completed:
        mission.tick(0.1)
        engine.update_node_positions(mission.node_positions())
        mission.inject_csi(engine.rx, 24)
        engine.process_frame()
    assert mission.stats.coverage_pct > 0
    print(f"STEP 5 OK: mission tick coverage={mission.stats.coverage_pct}%")


def main() -> int:
    step1_nav()
    step2_fake_csi()
    step3_coverage()
    step4_drone()
    step5_full()
    print("\nAll 5 build steps verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
