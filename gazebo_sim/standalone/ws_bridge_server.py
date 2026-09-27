#!/usr/bin/env python3
"""WebSocket server bridging mobile mission JSON to dashboard (/ws/mobile)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
from pathlib import Path

from bootstrap import bootstrap

ROOT = bootstrap()

try:
    import websockets
except ImportError:
    websockets = None

_clients: set = set()
_latest: dict = {}
_lock = threading.Lock()


def _mission_loop(zone: str, cfg: str, hz: float) -> None:
    from aura_processor.mobile_field import create_mobile_engine
    from aura_sim_core.mission import MobileMissionController
    from aura_sim_core.bridge import frame_to_bridge_message

    mission = MobileMissionController.from_config(zone)
    engine = create_mobile_engine(cfg)
    engine.config["area_size_m"] = mission.world.area_size_m
    dt = 1.0 / hz
    while not mission.stats.completed:
        status = mission.tick(dt)
        engine.update_node_positions(mission.node_positions())
        mission.inject_csi(engine.rx, 24)
        frame = engine.process_frame()
        msg = frame_to_bridge_message(frame, status)
        with _lock:
            _latest.clear()
            _latest.update(msg)
        time.sleep(dt)


def _ros_topic_loop(hz: float) -> None:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    class Relay(Node):
        def __init__(self):
            super().__init__("aura_ws_relay")
            self.create_subscription(String, "/aura/sensing/json", self._cb, 10)

        def _cb(self, msg: String):
            try:
                payload = json.loads(msg.data)
                with _lock:
                    _latest.clear()
                    _latest.update(payload)
            except Exception:
                pass

    rclpy.init()
    node = Relay()
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=1.0 / hz)
    finally:
        node.destroy_node()
        rclpy.shutdown()


async def _handler(ws):
    _clients.add(ws)
    try:
        async for _ in ws:
            pass
    finally:
        _clients.discard(ws)


async def _broadcast_loop():
    while True:
        await asyncio.sleep(0.2)
        with _lock:
            payload = json.dumps(_latest) if _latest else "{}"
        dead = []
        for ws in list(_clients):
            try:
                await ws.send(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _clients.discard(ws)


async def _main(port: int):
    if websockets is None:
        raise RuntimeError("pip install websockets")
    async with websockets.serve(_handler, "0.0.0.0", port):
        await _broadcast_loop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--zone", default=str(ROOT / "gazebo_sim" / "config" / "disaster_zone.yaml"))
    parser.add_argument("--config", default=str(ROOT / "simulation" / "config.yaml"))
    parser.add_argument("--hz", type=float, default=5.0)
    parser.add_argument("--ros-topic", action="store_true", help="Relay /aura/sensing/json instead of running mission")
    args = parser.parse_args()

    if args.ros_topic:
        t = threading.Thread(target=_ros_topic_loop, args=(args.hz,), daemon=True)
    else:
        t = threading.Thread(target=_mission_loop, args=(args.zone, args.config, args.hz), daemon=True)
    t.start()
    print(f"Mobile WS bridge on ws://0.0.0.0:{args.port}")
    asyncio.run(_main(args.port))


if __name__ == "__main__":
    main()
