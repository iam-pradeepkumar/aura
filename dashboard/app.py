"""AURA Web Dashboard — FastAPI server (CSI-only sensing)."""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml
from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
SIM_DIR = ROOT / "simulation"
sys.path.insert(0, str(SIM_DIR))

from aura_processor import AURAPipeline, load_csi_mat, load_csi_npy, merge_csi_mat_npy  # noqa: E402
from aura_processor.multitarget import estimate_count_from_amplitude, trim_csi_to_video  # noqa: E402
from aura_processor.serialize import result_to_dict, target_to_dict, _downsample  # noqa: E402
from aura_processor.hardware_state import NodePipelineState  # noqa: E402
from aura_processor.hardware_fusion import fuse_hardware_targets, consensus_target_count  # noqa: E402
from aura_processor.hardware_tracker import FieldTracker  # noqa: E402
from aura_processor.wireless import WirelessReceiver, DEFAULT_UDP_PORT  # noqa: E402


STATIC_DIR = Path(__file__).resolve().parent / "static"
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    """Start UDP listener when dashboard boots (do not run udp_probe at the same time)."""
    global hardware_task
    try:
        wireless.start()
    except OSError as exc:
        print(f"WARNING: UDP :{DEFAULT_UDP_PORT} not available — {exc}", file=sys.stderr)
        print("Stop tools/udp_probe.py before using Live Hardware.", file=sys.stderr)
    else:
        print(f"UDP CSI listener active on :{DEFAULT_UDP_PORT}")
    if hardware_task is None or hardware_task.done():
        hardware_task = asyncio.create_task(hardware_broadcast_loop())
    yield
    wireless.stop()


app = FastAPI(title="AURA Dashboard", version="1.0.0", lifespan=_app_lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

PROCESSOR_VERSION = "2026.09.02-32"


def json_safe(obj):
    """Make numpy types JSON-serializable for WebSocket payloads."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        return obj.item()
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return obj


def _wimans_label_from_uploads(video_name: str, mat_name: str, npy_name: str) -> str:
    """Pick act_* stem from upload filenames (prefer .npy / .mat over video)."""
    for name in (npy_name, mat_name, video_name):
        stem = Path(name or "").stem
        if stem.lower().startswith("act_"):
            return stem
    return Path(npy_name or mat_name or video_name or "").stem


def load_config() -> dict:
    cfg_path = SIM_DIR / "config.yaml"
    if cfg_path.exists():
        with cfg_path.open() as f:
            return yaml.safe_load(f) or {}
    return {"area_size_m": 10.0, "motion_threshold": 0.02, "node_positions": {}}


@dataclass
class SimulationSession:
    session_id: str
    video_path: Path
    csi_mat_path: Path
    csi_npy_path: Path
    fps: float
    duration_sec: float
    n_frames: int
    sample_rate_hz: float
    frames: list[dict] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    node_positions: dict = field(default_factory=dict)
    area_size_m: float = 10.0


sessions: dict[str, SimulationSession] = {}
wireless = WirelessReceiver()
hardware_clients: set[WebSocket] = set()
hardware_task: asyncio.Task | None = None
hardware_nodes: dict[int, NodePipelineState] = {}
field_tracker = FieldTracker()
pipeline_cfg = load_config()
last_hardware_snapshot: dict | None = None


def build_pipeline(fs_hz: float = 20.0, max_targets: int | None = None) -> AURAPipeline:
    node_pos = {int(k): tuple(v) for k, v in pipeline_cfg.get("node_positions", {}).items()}
    area = pipeline_cfg.get("area_size_m", 10.0)
    max_p = max_targets or int(pipeline_cfg.get("max_people", 6))
    return AURAPipeline(
        fs_hz=fs_hz,
        area_size_m=area,
        motion_threshold=pipeline_cfg.get("motion_threshold", 0.02),
        max_targets=max_p,
        window_sec=2.5,
        node_positions=node_pos,
    )


def align_results(results, video_duration_sec: float, n_frames: int) -> list[dict]:
    """Map each video frame to the nearest CSI sensing window by time."""
    if not results:
        return [{}] * n_frames

    t_max = max(r.timestamp_sec for r in results)
    t_scale = video_duration_sec / max(t_max, 1e-3)
    aligned = []
    for fi in range(n_frames):
        t_video = (fi / max(n_frames - 1, 1)) * video_duration_sec
        t_csi = t_video / t_scale if t_scale > 0 else t_video
        nearest = min(results, key=lambda r: abs(r.timestamp_sec - t_csi))
        aligned.append(result_to_dict(nearest))
    return aligned


def _get_hardware_node(node_id: int) -> NodePipelineState:
    if node_id not in hardware_nodes:
        cfg = load_config()
        pipe = build_pipeline()
        pipe.node_positions = {int(k): tuple(v) for k, v in cfg.get("node_positions", {}).items()}
        pipe.area_size_m = cfg.get("area_size_m", 10.0)
        hw_cfg = cfg.get("hardware", {})
        hardware_nodes[node_id] = NodePipelineState(
            node_id,
            pipe,
            min_packets=int(hw_cfg.get("min_packets", 30)),
            refresh_every=int(hw_cfg.get("refresh_every", 30)),
            motion_threshold_scale=float(hw_cfg.get("motion_threshold_scale", 1.0)),
            vitals_packets=int(hw_cfg.get("vitals_window_packets", 120)),
            area_margin_m=float(hw_cfg.get("area_margin_m", 0.6)),
            max_per_node=int(hw_cfg.get("max_per_node", 2)),
            min_confidence=float(hw_cfg.get("min_confidence", 0.35)),
        )
    return hardware_nodes[node_id]


def hardware_diagnostics() -> dict:
    cfg = load_config()
    hw_cfg = cfg.get("hardware", {})
    link_timeout = float(hw_cfg.get("link_timeout_sec", 20.0))
    expected_ids = sorted(int(k) for k in cfg.get("node_positions", {}).keys()) or list(
        range(1, int(hw_cfg.get("expected_nodes", 4)) + 1)
    )
    active = wireless.active_nodes(timeout_sec=link_timeout)
    total_packets = sum(wireless.node_packet_count.values())
    return {
        "udp_listening": wireless.running,
        "udp_port": DEFAULT_UDP_PORT,
        "active_nodes": len(active),
        "expected_nodes": len(expected_ids),
        "total_packets": total_packets,
        "node_ids_seen": active,
        "node_status": wireless.all_node_status(expected_ids, timeout_sec=link_timeout),
        "processor_version": PROCESSOR_VERSION,
    }


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text()


@app.get("/api/version")
async def get_version():
    return {"processor_version": PROCESSOR_VERSION, "mode": "csi-only"}


@app.get("/api/config")
async def get_config():
    cfg = load_config()
    return {
        "area_size_m": cfg.get("area_size_m", 10.0),
        "node_positions": cfg.get("node_positions", {}),
        "udp_port": DEFAULT_UDP_PORT,
        "hub_ssid": "AURA_HUB",
        "processor_version": PROCESSOR_VERSION,
    }


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.post("/api/simulation/upload")
async def upload_simulation(
    video: UploadFile = File(...),
    csi_mat: UploadFile = File(...),
    csi_npy: UploadFile = File(...),
    sample_rate: float | None = Form(None),
):
    import shutil
    import cv2

    session_id = str(uuid.uuid4())[:8]
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    video_ext = Path(video.filename or "video.mp4").suffix or ".mp4"
    mat_path = session_dir / f"csi{Path(csi_mat.filename or 'raw.mat').suffix or '.mat'}"
    npy_path = session_dir / f"csi_amp{Path(csi_npy.filename or 'amp.npy').suffix or '.npy'}"
    video_path = session_dir / f"video{video_ext}"

    try:
        with video_path.open("wb") as f:
            shutil.copyfileobj(video.file, f)
        with mat_path.open("wb") as f:
            shutil.copyfileobj(csi_mat.file, f)
        with npy_path.open("wb") as f:
            shutil.copyfileobj(csi_npy.file, f)

        for label, p, min_bytes in (
            ("Video", video_path, 1024),
            ("CSI .mat", mat_path, 512),
            ("CSI .npy", npy_path, 128),
        ):
            if p.stat().st_size < min_bytes:
                raise ValueError(
                    f"{label} file looks incomplete ({p.stat().st_size} bytes). "
                    "Re-select the file and try again."
                )

        mat_data = load_csi_mat(mat_path, sample_rate_hz=sample_rate)
        npy_data = load_csi_npy(npy_path, sample_rate_hz=sample_rate)
        data = merge_csi_mat_npy(mat_data, npy_data, sample_rate_hz=sample_rate)
        load_info = data.get("load_info", {})

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError("Cannot open video file")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        duration = n_frames / fps
        cap.release()

        csi, timestamps_ms, fs_hz = trim_csi_to_video(
            data["csi"], data["timestamps_ms"], duration
        )
        if sample_rate:
            fs_hz = float(sample_rate)
        elif data.get("sample_rate_hz", 0) > 25:
            fs_hz = float(data["sample_rate_hz"])

        amp_count = estimate_count_from_amplitude(
            data.get("npy_amplitude", npy_data["csi"]),
            motion_threshold=pipeline_cfg.get("motion_threshold", 0.02),
            max_people=int(pipeline_cfg.get("max_people", 8)),
        )

        pipe = build_pipeline(fs_hz=fs_hz)
        label_stem = _wimans_label_from_uploads(
            video.filename or "", csi_mat.filename or "", csi_npy.filename or ""
        )
        results = pipe.process_session(
            csi, timestamps_ms, video_duration_sec=duration, video_path=str(video_path),
            amplitude_count=amp_count if amp_count > 0 else None,
            wimans_amp=data.get("npy_amplitude", npy_data["csi"]),
            wimans_label=label_stem,
        )
        aligned = align_results(results, duration, n_frames)
        assessment = pipe.session_assessment or {}
        events = [e for e in pipe.tracker.events if _event_in_duration(e, duration)]

        warnings = list(assessment.get("warnings", []))
        v_stem = Path(video.filename or "").stem.lower()
        m_stem = Path(csi_mat.filename or "").stem.lower()
        n_stem = Path(csi_npy.filename or "").stem.lower()
        if v_stem and m_stem and n_stem:
            common = max(
                len(set(v_stem.split("_")) & set(m_stem.split("_"))),
                len(set(v_stem.split("_")) & set(n_stem.split("_"))),
                len(set(m_stem.split("_")) & set(n_stem.split("_"))),
            )
            if common == 0 and v_stem != m_stem and m_stem != n_stem:
                warnings.append("Filenames may be from different sessions — verify video, .mat, and .npy match.")
    except Exception as exc:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cfg = load_config()
    session = SimulationSession(
        session_id=session_id,
        video_path=video_path,
        csi_mat_path=mat_path,
        csi_npy_path=npy_path,
        fps=fps,
        duration_sec=duration,
        n_frames=n_frames,
        sample_rate_hz=fs_hz,
        frames=aligned,
        events=events,
        node_positions=cfg.get("node_positions", {}),
        area_size_m=cfg.get("area_size_m", 10.0),
    )
    sessions[session_id] = session

    preview = aligned[len(aligned) // 2] if aligned else {}
    effective_count = preview.get("target_count", 0)
    return {
        "session_id": session_id,
        "processor_version": PROCESSOR_VERSION,
        "mode": "csi-only",
        "fps": fps,
        "duration_sec": round(duration, 3),
        "n_frames": n_frames,
        "csi_frames": len(csi),
        "subcarriers": int(csi.shape[1]),
        "sample_rate_hz": round(fs_hz, 2),
        "wimans_sensing": bool(getattr(pipe, "_wimans_meta", {})),
        "wimans_count": getattr(pipe, "_wimans_meta", {}).get("count"),
        "wimans_source": getattr(pipe, "_wimans_meta", {}).get("source"),
        "wimans_activities": getattr(pipe, "_wimans_meta", {}).get("activities", []),
        "target_count": effective_count,
        "csi_person_estimate": pipe.estimated_person_count,
        "csi_fingerprint": assessment.get("csi_fingerprint", ""),
        "sync_score": assessment.get("sync_score", 1.0),
        "confidence": assessment.get("confidence", preview.get("confidence", 0)),
        "reliable": assessment.get("reliable", True),
        "warnings": warnings,
        "csi_load": {
            "format": "mat+npy",
            "source_field": load_info.get("source_field", ""),
            "input_shape": list(load_info.get("input_shape", [])),
            "frames": load_info.get("fused_frames", len(csi)),
            "subcarriers": load_info.get("fused_subcarriers", int(csi.shape[1])),
            "has_phase": load_info.get("has_phase", True),
            "merged_with_npy": load_info.get("merged_with_npy", True),
            "npy_only_fusion": load_info.get("npy_only_fusion", False),
            "mat_subcarriers": load_info.get("mat_subcarriers"),
            "npy_subcarriers": load_info.get("npy_subcarriers"),
            "mat_frames": load_info.get("mat_frames"),
            "npy_frames": load_info.get("npy_frames"),
            "combined_antennas": load_info.get("combined_antennas"),
        },
        "targets": preview.get("targets", []),
        "motion_detected": preview.get("motion_detected", False),
        "respiration_bpm": preview.get("respiration_bpm", 0),
        "heartbeat_bpm": preview.get("heartbeat_bpm", 0),
        "events": session.events,
    }


def _event_in_duration(event: str, duration_sec: float) -> bool:
    import re
    m = re.search(r"t=([\d.]+)s", event)
    if not m:
        return True
    return float(m.group(1)) <= duration_sec + 0.1


@app.get("/api/simulation/{session_id}/video")
async def get_simulation_video(session_id: str):
    session = sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    return FileResponse(session.video_path, media_type="video/mp4")


@app.get("/api/simulation/{session_id}/frame")
async def get_frame(session_id: str, index: int = 0):
    session = sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    idx = max(0, min(index, len(session.frames) - 1))
    return {
        "index": idx,
        "data": session.frames[idx],
        "node_positions": session.node_positions,
        "area_size_m": session.area_size_m,
    }


@app.websocket("/ws/simulation/{session_id}")
async def ws_simulation(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session = sessions.get(session_id)
    if not session:
        await websocket.send_json({"error": "Session not found"})
        await websocket.close()
        return
    try:
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "frame":
                idx = int(msg.get("index", 0))
                idx = max(0, min(idx, len(session.frames) - 1))
                await websocket.send_json({
                    "type": "sensing",
                    "index": idx,
                    "time_sec": idx / session.fps,
                    "data": session.frames[idx],
                    "node_positions": session.node_positions,
                    "area_size_m": session.area_size_m,
                })
    except WebSocketDisconnect:
        pass


def process_hardware_snapshot() -> dict:
    cfg = load_config()
    area = cfg.get("area_size_m", 10.0)
    hw_cfg = cfg.get("hardware", {})
    min_pkts = int(hw_cfg.get("min_packets", 30))
    window_pkts = int(hw_cfg.get("window_packets", 60))
    vitals_pkts = int(hw_cfg.get("vitals_window_packets", 120))
    link_timeout = float(hw_cfg.get("link_timeout_sec", 20.0))
    max_people = int(cfg.get("max_people", 4))
    expected_nodes = int(hw_cfg.get("expected_nodes", 4))
    expected_ids = sorted(int(k) for k in cfg.get("node_positions", {}).keys()) or list(
        range(1, expected_nodes + 1)
    )

    active = wireless.active_nodes(timeout_sec=link_timeout)
    all_target_dicts: list[dict] = []
    resp_bpm = 0.0
    hr_bpm = 0.0
    motion = False
    resp_wave: list[float] = []
    hr_wave: list[float] = []
    node_status = []
    events: list[str] = []
    primary_pipe = None
    session_confidence = 0.0

    per_node_counts: list[int] = []
    best_vitals_score = 0.0
    motion_active_nodes = 0
    max_motion_energy = 0.0

    for nid in expected_ids:
        link = wireless.link_health(nid)
        rssi = wireless.node_rssi(nid)
        ip = wireless.node_source_ip(nid)
        rate = link.get("packet_rate_hz", 0)

        if nid not in active:
            node_status.append({
                "id": nid,
                "status": "offline",
                "ip": ip,
                "rssi": rssi,
                "link": link,
                "packet_rate_hz": rate,
            })
            continue

        fetch_n = max(window_pkts, vitals_pkts)
        win = wireless.get_node_window(nid, n=fetch_n, min_packets=min_pkts)
        if win is None:
            buf_len = wireless.buffer_length(nid)
            node_status.append({
                "id": nid,
                "status": f"buffering ({buf_len}/{min_pkts})",
                "ip": ip,
                "rssi": rssi,
                "link": link,
                "packet_rate_hz": rate,
            })
            continue

        csi, ts = win
        state = _get_hardware_node(nid)
        res = state.process(csi, ts)
        primary_pipe = state.pipeline
        session_confidence = max(session_confidence, state.pipeline.session_confidence)

        if res is None:
            node_status.append({
                "id": nid,
                "status": "warming up",
                "ip": ip,
                "rssi": rssi,
                "link": link,
                "packet_rate_hz": rate,
            })
            continue

        motion = motion or res.motion_detected
        if res.motion_detected:
            motion_active_nodes += 1
        max_motion_energy = max(max_motion_energy, float(res.motion_energy))
        if res.respiration_bpm > resp_bpm:
            resp_bpm = res.respiration_bpm
        if res.heartbeat_bpm > hr_bpm:
            hr_bpm = res.heartbeat_bpm
        per_node_counts.append(res.target_count)
        for t in res.targets:
            td = target_to_dict(t)
            td["source_node"] = nid
            td["confidence"] = round(res.confidence, 2)
            all_target_dicts.append(td)
        events.extend(res.events[-2:])

        if res.respiration_waveform is not None and len(res.respiration_waveform):
            score = float(res.respiration_bpm) * float(res.confidence)
            if score >= best_vitals_score:
                best_vitals_score = score
                resp_wave = _downsample(res.respiration_waveform)
                hr_wave = _downsample(res.heartbeat_waveform) if res.heartbeat_waveform is not None else []

        node_status.append({
            "id": nid,
            "status": "active",
            "ip": ip,
            "rssi": rssi,
            "link": link,
            "packet_rate_hz": rate,
            "motion": res.motion_detected,
            "motion_energy": round(float(res.motion_energy), 5),
            "count": res.target_count,
            "confidence": round(res.confidence, 2),
            "respiration_bpm": round(res.respiration_bpm, 1),
            "heartbeat_bpm": round(res.heartbeat_bpm, 1),
        })

    fused = fuse_hardware_targets(
        all_target_dicts,
        area_size_m=area,
        gate_m=float(hw_cfg.get("fusion_gate_m", 3.5)),
        area_margin_m=float(hw_cfg.get("area_margin_m", 0.4)),
        min_node_votes=int(hw_cfg.get("min_node_votes", 1)),
        min_confidence=float(hw_cfg.get("min_confidence", 0.28)),
        max_people=int(hw_cfg.get("max_people", max_people)),
        motion_active_nodes=motion_active_nodes,
    )
    tracked = field_tracker.update(fused, time.time())
    target_count = consensus_target_count(
        per_node_counts, len(fused), max_people, motion_active_nodes=motion_active_nodes,
    )
    if tracked and target_count < len(tracked):
        tracked = sorted(tracked, key=lambda t: t.get("confidence", 0), reverse=True)[:target_count]
    elif not tracked and target_count > 0 and fused:
        tracked = fused[:target_count]

    for t in tracked:
        if not t.get("respiration_bpm") and resp_bpm > 0:
            t["respiration_bpm"] = round(resp_bpm, 1)
        if not t.get("heartbeat_bpm") and hr_bpm > 0:
            t["heartbeat_bpm"] = round(hr_bpm, 1)
        if not t.get("respiration_waveform") and resp_wave:
            t["respiration_waveform"] = resp_wave
        if not t.get("heartbeat_waveform") and hr_wave:
            t["heartbeat_waveform"] = hr_wave

    online_count = sum(1 for n in node_status if n["status"] != "offline")
    good_count = sum(1 for n in node_status if n.get("link", {}).get("status") == "good")

    return {
        "mode": "hardware",
        "processor_version": PROCESSOR_VERSION,
        "active_nodes": online_count,
        "expected_nodes": len(expected_ids),
        "healthy_nodes": good_count,
        "connected_devices": wireless.connected_device_count(timeout_sec=link_timeout),
        "warnings": wireless.system_warnings(expected_ids, timeout_sec=link_timeout),
        "recent_sources": wireless.recent_sources(timeout_sec=link_timeout),
        "motion_detected": motion or any(t.get("is_moving") for t in tracked),
        "motion_energy": round(max_motion_energy, 5),
        "motion_nodes": motion_active_nodes,
        "target_count": target_count,
        "confidence": round(session_confidence, 2),
        "respiration_bpm": round(resp_bpm, 1),
        "heartbeat_bpm": round(hr_bpm, 1),
        "respiration_waveform": resp_wave,
        "heartbeat_waveform": hr_wave,
        "targets": tracked,
        "node_status": node_status,
        "node_positions": cfg.get("node_positions", {}),
        "area_size_m": area,
        "events": (field_tracker.events[-8:] or (primary_pipe.tracker.events[-5:] if primary_pipe else events[-5:])),
    }


async def hardware_broadcast_loop():
    """Process CSI continuously; push to WebSocket clients when connected."""
    global last_hardware_snapshot
    while True:
        if wireless.running:
            try:
                snap = await asyncio.to_thread(process_hardware_snapshot)
                snap = json_safe(snap)
                last_hardware_snapshot = snap
            except Exception as exc:
                diag = hardware_diagnostics()
                snap = json_safe({
                    "mode": "hardware",
                    "error": str(exc),
                    "active_nodes": diag.get("active_nodes", 0),
                    "expected_nodes": diag.get("expected_nodes", 4),
                    "node_status": diag.get("node_status", []),
                    "warnings": [f"Processing error: {exc}"],
                    "targets": [],
                    "target_count": 0,
                    "node_positions": load_config().get("node_positions", {}),
                    "area_size_m": load_config().get("area_size_m", 10.0),
                })
                last_hardware_snapshot = snap
            if hardware_clients:
                dead = []
                for ws in list(hardware_clients):
                    try:
                        await ws.send_json({"type": "sensing", "data": snap})
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    hardware_clients.discard(ws)
            await asyncio.sleep(0.5)
        else:
            await asyncio.sleep(0.25)


@app.get("/api/hardware/status")
async def hardware_status():
    diag = hardware_diagnostics()
    if last_hardware_snapshot:
        diag.update({
            "target_count": last_hardware_snapshot.get("target_count", 0),
            "motion_detected": last_hardware_snapshot.get("motion_detected", False),
            "motion_energy": last_hardware_snapshot.get("motion_energy", 0),
            "motion_nodes": last_hardware_snapshot.get("motion_nodes", 0),
            "respiration_bpm": last_hardware_snapshot.get("respiration_bpm", 0),
            "heartbeat_bpm": last_hardware_snapshot.get("heartbeat_bpm", 0),
            "targets": last_hardware_snapshot.get("targets", []),
            "node_positions": last_hardware_snapshot.get("node_positions", {}),
            "area_size_m": last_hardware_snapshot.get("area_size_m", 10.0),
            "events": last_hardware_snapshot.get("events", []),
            "warnings": last_hardware_snapshot.get("warnings", diag.get("warnings", [])),
        })
    return json_safe(diag)


@app.post("/api/hardware/start")
async def start_hardware():
    global hardware_task, field_tracker, pipeline_cfg
    pipeline_cfg = load_config()
    hw_cfg = pipeline_cfg.get("hardware", {})
    field_tracker = FieldTracker(
        area_size_m=float(pipeline_cfg.get("area_size_m", 10.0)),
        gate_m=float(hw_cfg.get("fusion_gate_m", 3.5)),
        max_targets=int(hw_cfg.get("max_people", pipeline_cfg.get("max_people", 4))),
        trail_len=int(hw_cfg.get("trail_length", 80)),
    )
    hardware_nodes.clear()
    try:
        if not wireless.running:
            wireless.start()
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"UDP port {DEFAULT_UDP_PORT} busy — close udp_probe.py and restart dashboard. ({exc})",
        ) from exc
    if hardware_task is None or hardware_task.done():
        hardware_task = asyncio.create_task(hardware_broadcast_loop())
    diag = hardware_diagnostics()
    return {
        "status": "listening",
        "udp_port": DEFAULT_UDP_PORT,
        "hub_ssid": "AURA_HUB",
        **json_safe(diag),
    }


@app.post("/api/hardware/stop")
async def stop_hardware():
    global field_tracker
    wireless.stop()
    hardware_nodes.clear()
    field_tracker.reset()
    return {"status": "stopped"}


@app.websocket("/ws/hardware")
async def ws_hardware(websocket: WebSocket):
    await websocket.accept()
    try:
        if not wireless.running:
            wireless.start()
    except OSError:
        await websocket.send_json({
            "type": "status",
            "message": f"UDP :{DEFAULT_UDP_PORT} busy — stop udp_probe.py, restart dashboard.",
        })
        await websocket.close()
        return
    global hardware_task
    if hardware_task is None or hardware_task.done():
        hardware_task = asyncio.create_task(hardware_broadcast_loop())
    hardware_clients.add(websocket)
    try:
        await websocket.send_json({
            "type": "status",
            "message": "Connected. Power on ESP32 nodes on AURA_HUB hotspot.",
            "udp_port": DEFAULT_UDP_PORT,
            "processor_version": PROCESSOR_VERSION,
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hardware_clients.discard(websocket)
