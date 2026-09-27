#!/usr/bin/env python3
"""Publish ground + drone waypoint paths from disaster zone polygon."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT.parent.parent / "gazebo_sim" / "standalone"))
sys.path.insert(0, str(ROOT.parent.parent / "gazebo_sim"))

from bootstrap import bootstrap

bootstrap()

from aura_sim_core.coverage import CoveragePlanner
from aura_sim_core.world import load_world_config


class CoveragePlannerNode(Node):
    def __init__(self) -> None:
        super().__init__("aura_coverage_planner")
        active = ROOT.parent.parent / "gazebo_sim" / "config" / "active_mission.yaml"
        default_zone = active if active.exists() else ROOT.parent.parent / "gazebo_sim" / "config" / "disaster_zone.yaml"
        zone = self.declare_parameter("zone_config", str(default_zone)).value
        self.pub = self.create_publisher(String, "/aura/mission/waypoints", 10, latch=True)
        world = load_world_config(zone)
        planner = CoveragePlanner(world)
        payload = {
            "ground": [{"x": w.x, "y": w.y, "z": w.z} for w in planner.ground_nav2_style()],
            "drone": [{"x": w.x, "y": w.y, "z": w.z} for w in planner.drone_lawnmower(altitude_m=6.0)],
            "zone_polygon": world.zone_polygon,
            "ground_subcell": world.ground_subcell,
        }
        msg = String()
        msg.data = json.dumps(payload)
        self.pub.publish(msg)
        self.get_logger().info(
            f"Published {len(payload['ground'])} ground + {len(payload['drone'])} drone waypoints"
        )


def main() -> None:
    rclpy.init()
    node = CoveragePlannerNode()
    rclpy.spin_once(node, timeout_sec=0.5)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
