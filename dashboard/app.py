"""AURA Web Dashboard — FastAPI server."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
SIM_DIR = ROOT / "simulation"
sys.path.insert(0, str(SIM_DIR))

from aura_processor import AURAPipeline, load_csi  # noqa: E402
from aura_processor.serialize import result_to_dict, target_to_dict  # noqa: E402
from aura_processor.wireless import WirelessReceiver, DEFAULT_UDP_PORT  # noqa: E402


STATIC_DIR = Path(__file__).resolve().parent / "static"
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="AURA Dashboard", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
    csi_path: Path
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
pipeline_cfg = load_config()


def build_pipeline(fs_hz: float = 20.0) -> AURAPipeline:
    node_pos = {int(k): tuple(v) for k, v in pipeline_cfg.get("node_positions", {}).items()}
    return AURAPipeline(
        fs_hz=fs_hz,
        area_size_m=pipeline_cfg.get("area_size_m", 10.0),
        motion_threshold=pipeline_cfg.get("motion_threshold", 0.02),
        node_positions=node_pos,
    )


def align_results(results, video_duration_sec: float, n_frames: int) -> list[dict]:
    if not results:
        return [result_to_dict(r) for r in []] or [{}] * n_frames
    t_max = max(r.timestamp_sec for r in results)
    t_scale = video_duration_sec / max(t_max, 1e-3)
    aligned = []
    for fi in range(n_frames):
        t_video = (fi / max(n_frames - 1, 1)) * video_duration_sec
        t_csi = t_video / t_scale if t_scale > 0 else t_video
        best = min(results, key=lambda r: abs(r.timestamp_sec - t_csi))
        aligned.append(result_to_dict(best))
    return aligned


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text()


@app.get("/api/config")
async def get_config():
    cfg = load_config()
    return {
        "area_size_m": cfg.get("area_size_m", 10.0),
        "node_positions": cfg.get("node_positions", {}),
        "udp_port": DEFAULT_UDP_PORT,
        "hub_ssid": "AURA_HUB",
    }


@app.post("/api/simulation/upload")
async def upload_simulation(
    video: UploadFile = File(...),
    csi: UploadFile = File(...),
    sample_rate: float | None = Form(None),
):
    session_id = str(uuid.uuid4())[:8]
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    video_ext = Path(video.filename or "video.mp4").suffix or ".mp4"
    csi_ext = Path(csi.filename or "csi.npy").suffix or ".npy"
    video_path = session_dir / f"video{video_ext}"
    csi_path = session_dir / f"csi{csi_ext}"

    with video_path.open("wb") as f:
        shutil.copyfileobj(video.file, f)
    with csi_path.open("wb") as f:
        shutil.copyfileobj(csi.file, f)

    import cv2

    data = load_csi(csi_path, sample_rate_hz=sample_rate)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        shutil.rmtree(session_dir, ignore_errors=True)
        return {"error": "Cannot open video file"}
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    duration = n_frames / fps
    cap.release()

    pipe = build_pipeline(fs_hz=data["sample_rate_hz"])
    results = pipe.process_session(data["csi"], data["timestamps_ms"])
    aligned = align_results(results, duration, n_frames)

    cfg = load_config()
    session = SimulationSession(
        session_id=session_id,
        video_path=video_path,
        csi_path=csi_path,
        fps=fps,
        duration_sec=duration,
        n_frames=n_frames,
        sample_rate_hz=data["sample_rate_hz"],
        frames=aligned,
        events=pipe.tracker.events,
        node_positions=cfg.get("node_positions", {}),
        area_size_m=cfg.get("area_size_m", 10.0),
    )
    sessions[session_id] = session

    return {
        "session_id": session_id,
        "fps": fps,
        "duration_sec": round(duration, 3),
        "n_frames": n_frames,
        "csi_frames": len(data["csi"]),
        "subcarriers": int(data["csi"].shape[1]),
        "sample_rate_hz": round(data["sample_rate_hz"], 2),
        "events": session.events,
    }


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
    node_pos = {int(k): tuple(v) for k, v in cfg.get("node_positions", {}).items()}
    pipe = build_pipeline()
    pipe.node_positions = node_pos
    pipe.area_size_m = area

    active = wireless.active_nodes()
    all_targets = []
    total_count = 0
    resp_bpm = 0.0
    hr_bpm = 0.0
    motion = False
    resp_wave: list[float] = []
    hr_wave: list[float] = []
    node_status = []

    for nid in active:
        win = wireless.get_node_window(nid, n=40)
        rssi = wireless.node_rssi(nid)
        if win is None:
            node_status.append({"id": nid, "status": "buffering", "rssi": rssi})
            continue
        csi, ts = win
        fs = 20.0
        if len(ts) > 1:
            import numpy as np
            fs = float(1000.0 / max(np.median(np.diff(ts)), 1.0))
        pipe.fs_hz = fs
        res = pipe.process_window(csi, ts[-1] / 1000.0, node_id=nid)
        total_count = max(total_count, res.target_count)
        motion = motion or res.motion_detected
        all_targets.extend(res.targets)
        resp_bpm = max(resp_bpm, res.respiration_bpm)
        hr_bpm = max(hr_bpm, res.heartbeat_bpm)
        if res.respiration_waveform is not None and len(resp_wave) == 0:
            from aura_processor.serialize import _downsample
            resp_wave = _downsample(res.respiration_waveform)
            hr_wave = _downsample(res.heartbeat_waveform) if res.heartbeat_waveform is not None else []
        node_status.append({
            "id": nid,
            "status": "active",
            "rssi": rssi,
            "motion": res.motion_detected,
            "count": res.target_count,
            "respiration_bpm": round(res.respiration_bpm, 1),
            "heartbeat_bpm": round(res.heartbeat_bpm, 1),
        })

    return {
        "mode": "hardware",
        "active_nodes": len(active),
        "motion_detected": motion,
        "target_count": total_count,
        "respiration_bpm": round(resp_bpm, 1),
        "heartbeat_bpm": round(hr_bpm, 1),
        "respiration_waveform": resp_wave,
        "heartbeat_waveform": hr_wave,
        "targets": [target_to_dict(t) for t in all_targets],
        "node_status": node_status,
        "node_positions": cfg.get("node_positions", {}),
        "area_size_m": area,
        "events": pipe.tracker.events[-5:],
    }


async def hardware_broadcast_loop():
    while hardware_clients:
        if wireless.running:
            snap = process_hardware_snapshot()
            dead = []
            for ws in list(hardware_clients):
                try:
                    await ws.send_json({"type": "sensing", "data": snap})
                except Exception:
                    dead.append(ws)
            for ws in dead:
                hardware_clients.discard(ws)
        await asyncio.sleep(0.2)


@app.post("/api/hardware/start")
async def start_hardware():
    global hardware_task
    if not wireless.running:
        wireless.start()
    if hardware_task is None or hardware_task.done():
        hardware_task = asyncio.create_task(hardware_broadcast_loop())
    return {"status": "listening", "udp_port": DEFAULT_UDP_PORT, "hub_ssid": "AURA_HUB"}


@app.post("/api/hardware/stop")
async def stop_hardware():
    wireless.stop()
    return {"status": "stopped"}


@app.websocket("/ws/hardware")
async def ws_hardware(websocket: WebSocket):
    await websocket.accept()
    if not wireless.running:
        wireless.start()
    global hardware_task
    if hardware_task is None or hardware_task.done():
        hardware_task = asyncio.create_task(hardware_broadcast_loop())
    hardware_clients.add(websocket)
    try:
        await websocket.send_json({
            "type": "status",
            "message": "Connected. Power on ESP32 nodes on AURA_HUB hotspot.",
            "udp_port": DEFAULT_UDP_PORT,
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hardware_clients.discard(websocket)
