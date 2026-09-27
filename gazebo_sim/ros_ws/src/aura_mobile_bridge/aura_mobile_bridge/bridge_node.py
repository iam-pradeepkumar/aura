#!/usr/bin/env python3
"""ROS 2 bridge node — publishes aura_processor-shaped JSON + runs mission loop."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT.parent.parent / "gazebo_sim" / "standalone"))
sys.path.insert(0, str(ROOT.parent.parent / "simulation"))
sys.path.insert(0, str(ROOT.parent.parent))

from bootstrap import bootstrap

bootstrap()

from aura_processor.mobile_field import create_mobile_engine
from aura_sim_core.mission import MobileMissionController
from aura_sim_core.bridge import frame_to_bridge_message


class AuraMobileBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("aura_mobile_bridge")
        self.pub = self.create_publisher(String, "/aura/sensing/json", 10)
        zone = self.declare_parameter("zone_config", str(ROOT.parent.parent / "config" / "disaster_zone.yaml")).value
        cfg = self.declare_parameter("aura_config", str(ROOT.parent.parent.parent / "simulation" / "config.yaml")).value
        self.mission = MobileMissionController.from_config(zone)
        self.engine = create_mobile_engine(cfg)
        self.engine.config["area_size_m"] = self.mission.world.area_size_m
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        dt = 0.1
        while self._running and rclpy.ok():
            status = self.mission.tick(dt)
            self.engine.update_node_positions(self.mission.node_positions())
            self.mission.inject_csi(self.engine.rx, 24)
            frame = self.engine.process_frame()
            msg = frame_to_bridge_message(frame, status)
            out = String()
            out.data = json.dumps(msg)
            self.pub.publish(out)
            if self.mission.stats.completed:
                break
            time.sleep(dt)


def main() -> None:
    rclpy.init()
    node = AuraMobileBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node._running = False
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
