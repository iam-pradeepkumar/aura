#!/usr/bin/env python3
"""Fake CSI node — distance-to-victim model into aura_processor (no duplicate mission)."""

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
sys.path.insert(0, str(ROOT.parent.parent / "gazebo_sim"))

from bootstrap import bootstrap

bootstrap()

from aura_processor.mobile_field import create_mobile_engine
from aura_sim_core.bridge import frame_to_bridge_message
from aura_sim_core.fake_csi import FakeCsiGenerator
from aura_sim_core.world import load_world_config


class FakeCsiNode(Node):
    def __init__(self) -> None:
        super().__init__("aura_fake_csi")
        zone = self.declare_parameter(
            "zone_config",
            str(ROOT.parent.parent / "gazebo_sim" / "config" / "disaster_zone.yaml"),
        ).value
        cfg = self.declare_parameter(
            "aura_config",
            str(ROOT.parent.parent / "simulation" / "config.yaml"),
        ).value
        world = load_world_config(zone)
        mobile_cfg = {}
        try:
            import yaml
            with open(cfg) as f:
                mobile_cfg = (yaml.safe_load(f) or {}).get("hardware", {}).get("mobile", {})
        except Exception:
            pass
        vitals_sec = float(mobile_cfg.get("vitals_stationary_sec", 3.0))
        self.rover_id = int(mobile_cfg.get("rover_node_id", 1))
        self.drone_id = int(mobile_cfg.get("drone_node_id", 2))
        self.generator = FakeCsiGenerator(world, vitals_stationary_sec=vitals_sec)
        self.engine = create_mobile_engine(cfg)
        self.engine.config["area_size_m"] = world.area_size_m
        self.sensing_pub = self.create_publisher(String, "/aura/sensing/json", 10)
        self.create_subscription(String, "/aura/mission/status", self._on_status, 10)
        self._status: dict = {}
        self._running = True
        self._thread = threading.Thread(target=self._csi_loop, daemon=True)
        self._thread.start()

    def _on_status(self, msg: String) -> None:
        try:
            self._status = json.loads(msg.data)
        except Exception:
            pass

    def _csi_loop(self) -> None:
        dt = 0.1
        packets = 24
        while self._running and rclpy.ok():
            rover = self._status.get("rover", {})
            drone = self._status.get("drone", {})
            rx, ry = float(rover.get("x", 4.0)), float(rover.get("y", 4.0))
            holding = bool(rover.get("holding", False))
            lin = 0.0 if holding else 0.4
            ang = 0.0
            positions = {
                self.rover_id: (rx, ry),
                self.drone_id: (float(drone.get("x", 4.0)), float(drone.get("y", 4.0))),
            }
            self.engine.update_node_positions(positions)
            for _ in range(packets):
                row, ts, rssi = self.generator.generate_packet(
                    self.rover_id, rx, ry, lin, ang, vitals_capable=True,
                )
                self.engine.rx.inject(self.rover_id, row, ts, rssi)
            frame = self.engine.process_frame()
            out = String()
            out.data = json.dumps(frame_to_bridge_message(frame, self._status))
            self.sensing_pub.publish(out)
            time.sleep(dt)

    def destroy_node(self) -> None:
        self._running = False
        super().destroy_node()


def main() -> None:
    rclpy.init()
    node = FakeCsiNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
