"""Background mobile Gazebo/standalone mission for dashboard WebSocket."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gazebo_sim" / "standalone"))

from bootstrap import bootstrap

bootstrap()

from aura_processor.mobile_field import create_mobile_engine
from aura_sim_core.mission import MobileMissionController
from aura_sim_core.bridge import frame_to_bridge_message

_lock = threading.Lock()
_latest: dict = {}
_running = False
_thread: threading.Thread | None = None


def start_mobile_mission(zone_path: str | None = None, config_path: str | None = None) -> None:
    global _running, _thread
    if _running:
        return
    zone = zone_path or str(ROOT / "gazebo_sim" / "config" / "disaster_zone.yaml")
    cfg = config_path or str(ROOT / "simulation" / "config.yaml")
    _running = True

    def loop() -> None:
        mission = MobileMissionController.from_config(zone)
        engine = create_mobile_engine(cfg)
        engine.config["area_size_m"] = mission.world.area_size_m
        dt = 0.1
        while _running and not mission.stats.completed:
            status = mission.tick(dt)
            engine.update_node_positions(mission.node_positions())
            mission.inject_csi(engine.rx, 24)
            frame = engine.process_frame()
            msg = frame_to_bridge_message(frame, status)
            with _lock:
                _latest.clear()
                _latest.update(msg)
            time.sleep(dt)

    _thread = threading.Thread(target=loop, daemon=True)
    _thread.start()


def stop_mobile_mission() -> None:
    global _running
    _running = False


def get_latest_mobile_frame() -> dict:
    with _lock:
        return dict(_latest)
