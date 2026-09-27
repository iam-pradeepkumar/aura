"""AURA Command Center — mission orchestration for simulation + hardware."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gazebo_sim" / "standalone"))
sys.path.insert(0, str(ROOT / "gazebo_sim"))
sys.path.insert(0, str(ROOT / "simulation"))

from bootstrap import bootstrap

bootstrap()

from aura_processor.mobile_field import create_mobile_engine
from aura_sim_core.bridge import frame_to_bridge_message
from aura_sim_core.mission import MobileMissionController
from aura_sim_core.units import DEFAULT_UNIT_ROSTER, parse_units
from aura_sim_core.world import load_world_config, world_from_dict

_lock = threading.Lock()
_latest: dict = {}
_running = False
_thread: threading.Thread | None = None
_mission_config: dict = {}
_mission_status: str = "idle"  # idle | running | complete | error


def get_roster() -> list[dict]:
    return [dict(u) for u in DEFAULT_UNIT_ROSTER]


def get_zone_defaults() -> dict:
    zone_path = ROOT / "gazebo_sim" / "config" / "disaster_zone.yaml"
    with zone_path.open() as f:
        cfg = yaml.safe_load(f) or {}
    return {
        "area_size_m": cfg.get("area_size_m", 40.0),
        "zone_polygon": cfg.get("zone_polygon", []),
        "ground_subcell": cfg.get("ground_subcell", []),
        "obstacles": cfg.get("obstacles", []),
        "victims": [{"id": v["id"], "x": v["x"], "y": v["y"]} for v in cfg.get("victims", [])],
    }


def get_status() -> dict:
    with _lock:
        return {
            "mission_status": _mission_status,
            "running": _running,
            "config": dict(_mission_config),
            "latest": dict(_latest),
        }


def stop_mission() -> None:
    global _running, _mission_status
    _running = False
    _mission_status = "idle"


def start_mission(payload: dict) -> dict:
    """Start rescue mission from command center payload."""
    global _running, _thread, _mission_config, _mission_status

    if _running:
        return {"status": "already_running", "ws": "/ws/command"}

    mode = str(payload.get("mode", "simulation"))
    units = payload.get("units") or get_roster()
    zone_polygon = payload.get("zone_polygon")
    if not zone_polygon or len(zone_polygon) < 3:
        defaults = get_zone_defaults()
        zone_polygon = defaults["zone_polygon"]

    zone_cfg = {
        "area_size_m": float(payload.get("area_size_m", 40.0)),
        "zone_polygon": zone_polygon,
        "ground_subcell": payload.get("ground_subcell") or zone_polygon,
        "obstacles": payload.get("obstacles") or get_zone_defaults().get("obstacles", []),
        "victims": get_zone_defaults().get("victims", []),
        "units": units,
    }

    _mission_config = {
        "mode": mode,
        "units": units,
        "zone_polygon": zone_polygon,
        "area_size_m": zone_cfg["area_size_m"],
    }
    _running = True
    _mission_status = "running"

    def loop() -> None:
        global _running, _mission_status
        try:
            if mode == "hardware":
                _hardware_loop(zone_cfg, units)
            else:
                _simulation_loop(zone_cfg, units)
        except Exception as exc:
            with _lock:
                _mission_status = "error"
                _latest.clear()
                _latest.update({"type": "error", "message": str(exc)})
        finally:
            _running = False
            if _mission_status == "running":
                _mission_status = "complete"

    _thread = threading.Thread(target=loop, daemon=True)
    _thread.start()
    return {"status": "started", "ws": "/ws/command", "mode": mode}


def _simulation_loop(zone_cfg: dict, units: list[dict]) -> None:
    global _mission_status
    mission = MobileMissionController.from_mission_dict(zone_cfg)
    polygon = [(float(p[0]), float(p[1])) for p in zone_cfg["zone_polygon"]]
    ground = zone_cfg.get("ground_subcell")
    if ground:
        ground = [(float(p[0]), float(p[1])) for p in ground]
    mission.apply_zone(polygon, ground)

    cfg_path = str(ROOT / "simulation" / "config.yaml")
    engine = create_mobile_engine(cfg_path)
    engine.config["area_size_m"] = mission.world.area_size_m
    enabled_nodes = [int(u["node_id"]) for u in units if u.get("enabled")]
    engine.expected_ids = [nid for nid in enabled_nodes if any(
        u.get("type") == "spiderbot" and int(u.get("node_id")) == nid for u in units
    )] or [1]
    for nid in engine.expected_ids:
        engine.rx.link_node(nid)

    dt = 0.1
    while _running and not mission.stats.completed:
        status = mission.tick(dt)
        engine.update_node_positions(mission.node_positions())
        mission.inject_csi(engine.rx, 24)
        frame = engine.process_frame()
        msg = frame_to_bridge_message(
            frame,
            status,
            mode="simulation",
            zone_polygon=zone_cfg["zone_polygon"],
            obstacles=mission.world.obstacles,
            units_roster=status.get("units", []),
        )
        with _lock:
            _latest.clear()
            _latest.update(msg)
        time.sleep(dt)

    if mission.stats.completed:
        _mission_status = "complete"


def _hardware_loop(zone_cfg: dict, units: list[dict]) -> None:
    """Live ESP32 mobile hardware — UDP CSI ingest with runtime positions."""
    from aura_processor.hardware_live import LiveFieldEngine, load_field_config

    cfg = load_field_config(str(ROOT / "simulation" / "config.yaml"))
    cfg.setdefault("hardware", {})["mode"] = "mobile"
    cfg["area_size_m"] = float(zone_cfg.get("area_size_m", 40.0))
    engine = LiveFieldEngine(config=cfg)
    engine.start()
    dt = 0.1
    while _running:
        frame = engine.process_frame()
        status = {
            "phase": "live",
            "elapsed_sec": 0,
            "coverage_pct": 0,
            "confirmed_detections": frame.get("target_count", 0),
            "units": [
                {
                    "id": u["id"],
                    "name": u.get("name", u["id"]),
                    "type": u.get("type"),
                    "node_id": u.get("node_id"),
                    "status": "LIVE",
                    "x": engine.node_pos.get(int(u["node_id"]), (0, 0))[0],
                    "y": engine.node_pos.get(int(u["node_id"]), (0, 0))[1],
                }
                for u in units if u.get("enabled")
            ],
        }
        msg = frame_to_bridge_message(
            frame,
            status,
            mode="hardware",
            zone_polygon=zone_cfg["zone_polygon"],
            obstacles=zone_cfg.get("obstacles", []),
            units_roster=status.get("units", []),
        )
        with _lock:
            _latest.clear()
            _latest.update(msg)
        time.sleep(dt)
    engine.stop()


def get_latest_frame() -> dict:
    with _lock:
        return dict(_latest)
