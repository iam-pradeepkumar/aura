#!/usr/bin/env python3
"""Mission behavior — patrol, hold-for-vitals, publish robot poses."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT.parent.parent / "gazebo_sim" / "standalone"))
sys.path.insert(0, str(ROOT.parent.parent / "gazebo_sim"))

from bootstrap import bootstrap

bootstrap()

from aura_sim_core.mission import MobileMissionController


class BehaviorNode(Node):
    def __init__(self) -> None:
        super().__init__("aura_robot_behavior")
        zone = self.declare_parameter(
            "zone_config",
            str(ROOT.parent.parent / "gazebo_sim" / "config" / "disaster_zone.yaml"),
        ).value
        self.mission = MobileMissionController.from_config(zone)
        self.pose_pub = self.create_publisher(PoseStamped, "/aura/rover/pose", 10)
        self.drone_pub = self.create_publisher(PoseStamped, "/aura/drone/pose", 10)
        self.status_pub = self.create_publisher(String, "/aura/mission/status", 10)
        self.create_subscription(String, "/aura/mission/waypoints", self._on_waypoints, 10)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _on_waypoints(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
            from aura_sim_core.coverage import Waypoint

            if data.get("ground"):
                self.mission.rover_waypoints = [
                    Waypoint(w["x"], w["y"], w.get("z", 0.0)) for w in data["ground"]
                ]
            if data.get("drone"):
                self.mission.drone_waypoints = [
                    Waypoint(w["x"], w["y"], w.get("z", 6.0)) for w in data["drone"]
                ]
            self.mission.rover.state.waypoint_idx = 0
            self.mission.drone.state.waypoint_idx = 0
            self.get_logger().info("Waypoints loaded from planner")
        except Exception as exc:
            self.get_logger().warn(f"Waypoint parse failed: {exc}")

    def _loop(self) -> None:
        dt = 0.1
        while self._running and rclpy.ok():
            status = self.mission.tick(dt)
            rover = PoseStamped()
            rover.header.frame_id = "world"
            rover.pose.position.x = self.mission.rover.state.x
            rover.pose.position.y = self.mission.rover.state.y
            self.pose_pub.publish(rover)
            drone = PoseStamped()
            drone.header.frame_id = "world"
            drone.pose.position.x = self.mission.drone.state.x
            drone.pose.position.y = self.mission.drone.state.y
            drone.pose.position.z = self.mission.drone.state.z
            self.drone_pub.publish(drone)
            out = String()
            out.data = json.dumps(status)
            self.status_pub.publish(out)
            if self.mission.stats.completed:
                break
            time.sleep(dt)

    def destroy_node(self) -> None:
        self._running = False
        super().destroy_node()


def main() -> None:
    rclpy.init()
    node = BehaviorNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
