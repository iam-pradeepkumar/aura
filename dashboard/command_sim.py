"""AURA Command Center — geo-aware mission orchestration (sim + hardware + Gazebo)."""

from __future__ import annotations

import random
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gazebo_sim" / "standalone"))
sys.path.insert(0, str(ROOT / "gazebo_sim"))
sys.path.insert(0, str(ROOT / "simulation"))

from bootstrap import bootstrap

bootstrap()

from aura_processor.mobile_field import create_mobile_engine
from aura_sim_core.bridge import frame_to_bridge_message
from aura_sim_core.geo import (
    GeoAnchor,
    area_size_from_polygon,
    bbox_from_polygon,
    polygon_geo_to_local,
    survivors_geo_to_local,
)
from aura_sim_core.mission import MobileMissionController
from aura_sim_core.sim_tuning import (
    CLOUD_MODE,
    CSI_PACKETS_PER_TICK,
    ENGINE_FRAME_EVERY,
    TICK_HZ,
    TIME_SCALE,
    apply_dashboard_tuning,
)
from aura_sim_core.units import DEFAULT_UNIT_ROSTER, parse_units
from aura_sim_core.world import DisasterWorld, world_from_dict

SESSION_IDLE_SEC = 600.0


@dataclass
class MissionSession:
    session_id: str
    lock: threading.Lock = field(default_factory=threading.Lock)
    latest: dict = field(default_factory=dict)
    running: bool = False
    thread: threading.Thread | None = None
    mission_config: dict = field(default_factory=dict)
    mission_status: str = "idle"
    last_active: float = field(default_factory=time.time)
    ws_clients: int = 0

    def touch(self) -> None:
        self.last_active = time.time()

    def status_dict(self) -> dict:
        with self.lock:
            return {
                "session_id": self.session_id,
                "mission_status": self.mission_status,
                "running": self.running,
                "config": dict(self.mission_config),
                "latest": dict(self.latest),
            }


class MissionManager:
    _sessions: dict[str, MissionSession] = {}
    _lock = threading.Lock()

    @classmethod
    def get(cls, session_id: str) -> MissionSession | None:
        with cls._lock:
            return cls._sessions.get(session_id)

    @classmethod
    def get_or_create(cls, session_id: str) -> MissionSession:
        with cls._lock:
            session = cls._sessions.get(session_id)
            if session is None:
                session = MissionSession(session_id=session_id)
                cls._sessions[session_id] = session
            session.touch()
            cls._cleanup_idle()
            return session

    @classmethod
    def remove(cls, session_id: str) -> None:
        with cls._lock:
            cls._sessions.pop(session_id, None)

    @classmethod
    def register_ws(cls, session_id: str) -> MissionSession:
        session = cls.get_or_create(session_id)
        with session.lock:
            session.ws_clients += 1
            session.touch()
        return session

    @classmethod
    def unregister_ws(cls, session_id: str) -> None:
        session = cls.get(session_id)
        if session is None:
            return
        with session.lock:
            session.ws_clients = max(0, session.ws_clients - 1)
            session.touch()

    @classmethod
    def _cleanup_idle(cls) -> None:
        now = time.time()
        stale = [
            sid
            for sid, s in cls._sessions.items()
            if not s.running and s.ws_clients <= 0 and (now - s.last_active) > SESSION_IDLE_SEC
        ]
        for sid in stale:
            cls._sessions.pop(sid, None)


def get_roster() -> list[dict]:
    return [dict(u) for u in DEFAULT_UNIT_ROSTER]


def get_zone_defaults() -> dict:
    active = ROOT / "gazebo_sim" / "config" / "active_mission.yaml"
    zone_path = active if active.exists() else ROOT / "gazebo_sim" / "config" / "disaster_zone.yaml"
    with zone_path.open() as f:
        cfg = yaml.safe_load(f) or {}
    base_path = ROOT / "gazebo_sim" / "config" / "disaster_zone.yaml"
    with base_path.open() as f:
        base = yaml.safe_load(f) or {}
    return {
        "area_size_m": cfg.get("area_size_m", 40.0),
        "zone_polygon": cfg.get("zone_polygon", []),
        "ground_subcell": cfg.get("ground_subcell", []),
        "obstacles": cfg.get("obstacles", []),
        "victims": [{"id": v["id"], "x": v["x"], "y": v["y"]} for v in cfg.get("victims", [])],
        "default_geo": base.get("default_geo", {"lat": 37.4241, "lon": -122.1661, "label": "Stanford, CA"}),
        "geo_anchor": cfg.get("geo_anchor"),
        "zone_polygon_geo": cfg.get("zone_polygon_geo", []),
    }


def get_status(session_id: str) -> dict:
    session = MissionManager.get(session_id)
    if session is None:
        return {
            "session_id": session_id,
            "mission_status": "idle",
            "running": False,
            "config": {},
            "latest": {},
        }
    return session.status_dict()


def stop_mission(session_id: str) -> None:
    session = MissionManager.get(session_id)
    if session is None:
        return
    session.running = False
    session.mission_status = "idle"
    session.touch()


def get_latest_frame(session_id: str) -> dict:
    session = MissionManager.get(session_id)
    if session is None:
        return {}
    session.touch()
    with session.lock:
        return dict(session.latest)


def _point_in_polygon(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    w = DisasterWorld(40, poly, poly)
    return w.point_in_polygon(x, y, poly)


def _place_victims(local_poly: list[tuple[float, float]], n: int = 3) -> list[dict]:
    xmin, ymin, xmax, ymax = bbox_from_polygon(local_poly)
    victims = []
    rng = random.Random(42)
    for i in range(n):
        for _ in range(80):
            x = rng.uniform(xmin + 2, xmax - 2)
            y = rng.uniform(ymin + 2, ymax - 2)
            if _point_in_polygon(x, y, local_poly):
                victims.append({"id": i + 1, "x": x, "y": y, "resp_bpm": float(rng.randint(11, 18))})
                break
    return victims


def _scale_obstacles(template: list, local_poly: list[tuple[float, float]], ref_size: float) -> list:
    xmin, ymin, xmax, ymax = bbox_from_polygon(local_poly)
    w, h = max(xmax - xmin, 1), max(ymax - ymin, 1)
    out = []
    for o in template:
        ox = xmin + (float(o[0]) / ref_size) * w * 0.85 + w * 0.05
        oy = ymin + (float(o[1]) / ref_size) * h * 0.45 + h * 0.05
        if _point_in_polygon(ox, oy, local_poly):
            out.append([ox, oy, float(o[2])])
    return out


def _build_zone_cfg(payload: dict) -> dict:
    units = payload.get("units") or get_roster()
    defaults = get_zone_defaults()
    geo_anchor = payload.get("geo_anchor")
    zone_polygon_geo = payload.get("zone_polygon_geo")
    anchor_obj: GeoAnchor | None = None

    if zone_polygon_geo and len(zone_polygon_geo) >= 3:
        ring_geo = [[float(p[0]), float(p[1])] for p in zone_polygon_geo]
        lngs = [p[0] for p in ring_geo]
        lats = [p[1] for p in ring_geo]
        clat = sum(lats) / len(lats)
        clon = sum(lngs) / len(lngs)
        label = str((geo_anchor or {}).get("label", ""))
        anchor_obj = GeoAnchor(clat, clon, label)
        if geo_anchor is None:
            geo_anchor = {"lat": clat, "lon": clon, "label": label}
        local_poly = polygon_geo_to_local(anchor_obj, ring_geo)
        area = area_size_from_polygon(local_poly)
        ref = float(defaults["area_size_m"])
        obstacles = _scale_obstacles(defaults["obstacles"], local_poly, ref)
        survivors_geo = payload.get("survivors_geo") or []
        if survivors_geo:
            victims = survivors_geo_to_local(anchor_obj, survivors_geo, local_poly)
        else:
            victims = _place_victims(local_poly)
        ground_subcell = list(local_poly)
        return {
            "area_size_m": area,
            "zone_polygon": [[x, y] for x, y in local_poly],
            "zone_polygon_geo": ring_geo,
            "ground_subcell": [[x, y] for x, y in ground_subcell],
            "obstacles": obstacles,
            "victims": victims,
            "survivors_geo": survivors_geo,
            "units": units,
            "geo_anchor": geo_anchor,
            "_anchor": anchor_obj,
            "gazebo": bool(payload.get("gazebo", False)),
        }

    zone_polygon = payload.get("zone_polygon")
    if not zone_polygon or len(zone_polygon) < 3:
        zone_polygon = defaults["zone_polygon"]
    return {
        "area_size_m": float(payload.get("area_size_m", defaults["area_size_m"])),
        "zone_polygon": zone_polygon,
        "ground_subcell": payload.get("ground_subcell") or zone_polygon,
        "obstacles": payload.get("obstacles") or defaults["obstacles"],
        "victims": defaults["victims"],
        "units": units,
        "geo_anchor": geo_anchor,
        "zone_polygon_geo": zone_polygon_geo or [],
        "_anchor": anchor_obj,
        "gazebo": bool(payload.get("gazebo", False)),
    }


def _json_num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _victim_geo_lookup(victims: list[dict] | None) -> dict[int, tuple[float, float]]:
    out: dict[int, tuple[float, float]] = {}
    for v in victims or []:
        vid = int(v.get("id", 0))
        lat, lon = v.get("lat"), v.get("lon")
        if vid and lat is not None and lon is not None:
            out[vid] = (float(lat), float(lon))
    return out


def _victim_local_lookup(victims: list[dict] | None) -> dict[int, tuple[float, float]]:
    out: dict[int, tuple[float, float]] = {}
    for v in victims or []:
        vid = int(v.get("id", 0))
        if vid:
            out[vid] = (float(v.get("x", 0)), float(v.get("y", 0)))
    return out


def _pin_target_to_victim(
    target: dict,
    tid: int,
    victim_local: dict[int, tuple[float, float]],
    victim_geo: dict[int, tuple[float, float]] | None,
) -> dict:
    t = dict(target)
    if tid in victim_local:
        t["x_m"] = victim_local[tid][0]
        t["y_m"] = victim_local[tid][1]
    if victim_geo and tid in victim_geo:
        t["lat"] = victim_geo[tid][0]
        t["lon"] = victim_geo[tid][1]
    return t


def _merge_sim_targets(
    frame: dict,
    sim_targets: list[dict],
    victim_geo: dict[int, tuple[float, float]] | None = None,
    victim_local: dict[int, tuple[float, float]] | None = None,
) -> dict:
    if not sim_targets and not frame.get("targets"):
        return frame
    victim_local = victim_local or {}
    sim_by_id = {int(t.get("id", 0)): dict(t) for t in sim_targets if int(t.get("id", 0))}
    by_id: dict[int, dict] = {}
    for t in frame.get("targets", []):
        tid = int(t.get("id", 0))
        if tid:
            by_id[tid] = dict(t)
    for tid, sim in sim_by_id.items():
        prev = by_id.get(tid)
        merged = dict(sim)
        if prev is not None:
            merged["confidence"] = max(float(prev.get("confidence", 0)), float(sim.get("confidence", 0)))
            merged["confirmed"] = bool(prev.get("confirmed") or sim.get("confirmed"))
        merged = _pin_target_to_victim(merged, tid, victim_local, victim_geo)
        by_id[tid] = merged
    merged = []
    for tid, t in by_id.items():
        conf = float(t.get("confidence", 0))
        t["probability_pct"] = round(conf * 100, 1)
        t["vitals_confidence_pct"] = round(float(t.get("resp_confidence", conf)) * 100, 1)
        t = _pin_target_to_victim(t, tid, victim_local, victim_geo)
        merged.append(t)
    confirmed = [t for t in merged if t.get("confirmed")]
    frame["targets"] = merged
    frame["target_count"] = len(confirmed) if confirmed else len(
        [t for t in merged if float(t.get("confidence", 0)) >= 0.45]
    )
    frame["survivors_detected"] = len(confirmed) if confirmed else frame["target_count"]
    frame["motion_detected"] = frame.get("motion_detected", False) or frame["target_count"] > 0
    if merged:
        best = max(merged, key=lambda t: float(t.get("confidence", 0)))
        frame["sensing_confidence"] = max(float(frame.get("sensing_confidence", 0)), float(best.get("confidence", 0)))
    return frame


def _enrich_geo(
    msg: dict,
    anchor: GeoAnchor | None,
    victim_geo: dict[int, tuple[float, float]] | None = None,
) -> dict:
    if anchor is None:
        return msg
    for u in msg.get("units_roster", []):
        lat, lon = anchor.to_geo(_json_num(u.get("x", 0)), _json_num(u.get("y", 0)))
        u["lat"] = round(lat, 6)
        u["lon"] = round(lon, 6)
        u["x"] = round(_json_num(u.get("x", 0)), 3)
        u["y"] = round(_json_num(u.get("y", 0)), 3)
        if u.get("type") == "drone":
            u["alt_m"] = _json_num(u.get("z", 6))
        if u.get("wifi_signal") is not None:
            u["wifi_signal"] = round(_json_num(u.get("wifi_signal", 0)), 3)
    for u in msg.get("mission", {}).get("units", []):
        lat, lon = anchor.to_geo(_json_num(u.get("x", 0)), _json_num(u.get("y", 0)))
        u["lat"] = round(lat, 6)
        u["lon"] = round(lon, 6)
    for t in msg.get("data", {}).get("targets", []):
        tid = int(t.get("id", 0))
        if victim_geo and tid in victim_geo:
            t["lat"] = round(victim_geo[tid][0], 6)
            t["lon"] = round(victim_geo[tid][1], 6)
        else:
            lat, lon = anchor.to_geo(_json_num(t.get("x_m", 0)), _json_num(t.get("y_m", 0)))
            t["lat"] = round(lat, 6)
            t["lon"] = round(lon, 6)
    for sig in msg.get("wifi", {}).get("signals", []):
        lat, lon = anchor.to_geo(_json_num(sig.get("x", 0)), _json_num(sig.get("y", 0)))
        sig["lat"] = round(lat, 6)
        sig["lon"] = round(lon, 6)
    return msg


def _write_mission_yaml(zone_cfg: dict) -> Path:
    out = ROOT / "gazebo_sim" / "config" / "active_mission.yaml"
    doc = {
        "area_size_m": zone_cfg["area_size_m"],
        "zone_polygon": zone_cfg["zone_polygon"],
        "ground_subcell": zone_cfg.get("ground_subcell", zone_cfg["zone_polygon"]),
        "obstacles": zone_cfg.get("obstacles", []),
        "victims": zone_cfg.get("victims", []),
        "geo_anchor": zone_cfg.get("geo_anchor"),
        "zone_polygon_geo": zone_cfg.get("zone_polygon_geo", []),
    }
    with out.open("w") as f:
        yaml.safe_dump(doc, f)
    return out


def _light_frame_from_sim(mission: MobileMissionController) -> dict:
    sim_targets = mission.get_sim_targets()
    confirmed = [t for t in sim_targets if t.get("confirmed")]
    node_positions = {
        int(k): [float(v[0]), float(v[1])]
        for k, v in mission.node_positions().items()
    }
    best_conf = max((float(t.get("confidence", 0)) for t in sim_targets), default=0.0)
    return {
        "timestamp": time.time(),
        "area_size_m": mission.world.area_size_m,
        "targets": sim_targets,
        "target_count": len(confirmed) if confirmed else len(sim_targets),
        "survivors_detected": len(confirmed),
        "motion_detected": bool(sim_targets),
        "sensing_confidence": best_conf,
        "node_positions": node_positions,
        "mode": "mobile",
    }


def start_mission(session_id: str, payload: dict) -> dict:
    if not session_id:
        return {"status": "error", "message": "session_id required"}

    session = MissionManager.get_or_create(session_id)
    if session.running:
        return {
            "status": "already_running",
            "session_id": session_id,
            "ws": f"/ws/command?session_id={session_id}",
        }

    mode = str(payload.get("mode", "simulation"))
    zone_cfg = _build_zone_cfg(payload)
    if mode == "gazebo":
        mode = "simulation"
        zone_cfg["gazebo"] = True

    session.mission_config = {
        "mode": mode,
        "units": zone_cfg["units"],
        "geo_anchor": zone_cfg.get("geo_anchor"),
        "zone_polygon_geo": zone_cfg.get("zone_polygon_geo"),
        "gazebo": zone_cfg.get("gazebo", False),
    }
    if not CLOUD_MODE:
        _write_mission_yaml(zone_cfg)
    session.running = True
    session.mission_status = "running"
    session.touch()

    def loop() -> None:
        try:
            if mode == "hardware":
                _hardware_loop(session, zone_cfg, zone_cfg["units"])
            else:
                _simulation_loop(session, zone_cfg, zone_cfg["units"])
        except Exception as exc:
            with session.lock:
                session.mission_status = "error"
                session.latest.clear()
                session.latest.update({"type": "error", "message": str(exc)})
        finally:
            session.running = False
            if session.mission_status == "running":
                session.mission_status = "complete"
            session.touch()

    session.thread = threading.Thread(target=loop, daemon=True, name=f"mission-{session_id[:8]}")
    session.thread.start()
    return {
        "status": "started",
        "session_id": session_id,
        "ws": f"/ws/command?session_id={session_id}",
        "mode": mode,
        "gazebo": zone_cfg.get("gazebo"),
        "cloud_mode": CLOUD_MODE,
    }


def _simulation_loop(session: MissionSession, zone_cfg: dict, units: list[dict]) -> None:
    anchor = zone_cfg.get("_anchor")
    victims = zone_cfg.get("victims") or []
    victim_geo = _victim_geo_lookup(victims)
    victim_local = _victim_local_lookup(victims)
    mission = MobileMissionController.from_mission_dict(zone_cfg)
    polygon = [(float(p[0]), float(p[1])) for p in zone_cfg["zone_polygon"]]
    ground = zone_cfg.get("ground_subcell")
    if ground:
        ground = [(float(p[0]), float(p[1])) for p in ground]
    mission.apply_zone(polygon, ground)
    apply_dashboard_tuning(mission)

    cfg_path = str(ROOT / "simulation" / "config.yaml")
    engine = create_mobile_engine(cfg_path)
    engine.config["area_size_m"] = mission.world.area_size_m
    spider_ids = [
        int(u["node_id"]) for u in units
        if u.get("enabled") and u.get("type") == "spiderbot"
    ]
    engine.expected_ids = spider_ids or [1]
    for nid in engine.expected_ids:
        engine.rx.link_node(nid)

    dt = 1.0 / TICK_HZ
    sim_dt = dt * TIME_SCALE
    tick_num = 0
    while session.running and not mission.stats.completed:
        status = mission.tick(sim_dt)
        engine.update_node_positions(mission.node_positions())

        if ENGINE_FRAME_EVERY > 1 and tick_num % ENGINE_FRAME_EVERY != 0:
            frame = _light_frame_from_sim(mission)
        else:
            mission.inject_csi(engine.rx, CSI_PACKETS_PER_TICK)
            frame = engine.process_frame()

        frame = _merge_sim_targets(frame, mission.get_sim_targets(), victim_geo, victim_local)
        msg = frame_to_bridge_message(
            frame,
            status,
            mode="simulation",
            zone_polygon=zone_cfg["zone_polygon"],
            zone_polygon_geo=zone_cfg.get("zone_polygon_geo"),
            geo_anchor=zone_cfg.get("geo_anchor"),
            obstacles=mission.world.obstacles,
            units_roster=status.get("units", []),
        )
        msg = _enrich_geo(msg, anchor, victim_geo)
        msg["sim"] = {"time_scale": TIME_SCALE, "tick_hz": TICK_HZ, "cloud_mode": CLOUD_MODE}
        msg["wifi"] = {"signals": mission.get_wifi_signals()}
        msg = _enrich_geo(msg, anchor, victim_geo)
        msg["session_id"] = session.session_id
        if zone_cfg.get("survivors_geo"):
            msg["geo"]["survivors_placed"] = zone_cfg["survivors_geo"]
        with session.lock:
            session.latest.clear()
            session.latest.update(msg)
        tick_num += 1
        time.sleep(dt)

    if mission.stats.completed:
        session.mission_status = "complete"


def _hardware_loop(session: MissionSession, zone_cfg: dict, units: list[dict]) -> None:
    from aura_processor.hardware_live import LiveFieldEngine, load_field_config

    anchor = zone_cfg.get("_anchor")
    cfg = load_field_config(str(ROOT / "simulation" / "config.yaml"))
    cfg.setdefault("hardware", {})["mode"] = "mobile"
    cfg["area_size_m"] = float(zone_cfg.get("area_size_m", 40.0))
    engine = LiveFieldEngine(config=cfg)
    engine.start()
    dt = 0.1
    while session.running:
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
            zone_polygon_geo=zone_cfg.get("zone_polygon_geo"),
            geo_anchor=zone_cfg.get("geo_anchor"),
            obstacles=zone_cfg.get("obstacles", []),
            units_roster=status.get("units", []),
        )
        msg = _enrich_geo(msg, anchor)
        msg["session_id"] = session.session_id
        with session.lock:
            session.latest.clear()
            session.latest.update(msg)
        time.sleep(dt)
    engine.stop()
