"""AURA Web Dashboard — FastAPI server (CSI-only sensing)."""

from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
SIM_DIR = ROOT / "simulation"
sys.path.insert(0, str(SIM_DIR))

from aura_processor import AURAPipeline, load_csi  # noqa: E402
from aura_processor.multitarget import trim_csi_to_video  # noqa: E402
from aura_processor.serialize import result_to_dict, target_to_dict  # noqa: E402
from aura_processor.hardware_state import NodePipelineState, fuse_multinode_targets  # noqa: E402
from aura_processor.wireless import WirelessReceiver, DEFAULT_UDP_PORT  # noqa: E402


STATIC_DIR = Path(__file__).resolve().parent / "static"
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="AURA Dashboard", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

PROCESSOR_VERSION = "2026.08.31-6"


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
hardware_nodes: dict[int, NodePipelineState] = {}
pipeline_cfg = load_config()


def build_pipeline(fs_hz: float = 20.0, max_targets: int = 3) -> AURAPipeline:
    node_pos = {int(k): tuple(v) for k, v in pipeline_cfg.get("node_positions", {}).items()}
    area = pipeline_cfg.get("area_size_m", 10.0)
    return AURAPipeline(
        fs_hz=fs_hz,
        area_size_m=area,
        motion_threshold=pipeline_cfg.get("motion_threshold", 0.02),
        max_targets=max_targets,
        window_sec=2.5,
        node_positions=node_pos,
    )


def align_results(results, video_duration_sec: float, n_frames: int) -> list[dict]:
    if not results:
        return [{}] * n_frames
    best = max(results, key=lambda r: (r.target_count, r.motion_energy))
    t_max = max(r.timestamp_sec for r in results)
    t_scale = video_duration_sec / max(t_max, 1e-3)
    aligned = []
    for fi in range(n_frames):
        t_video = (fi / max(n_frames - 1, 1)) * video_duration_sec
        t_csi = t_video / t_scale if t_scale > 0 else t_video
        nearest = min(results, key=lambda r: abs(r.timestamp_sec - t_csi))
        chosen = nearest if nearest.target_count >= best.target_count else best
        aligned.append(result_to_dict(chosen))
    return aligned


def _get_hardware_node(node_id: int) -> NodePipelineState:
    if node_id not in hardware_nodes:
        pipe = build_pipeline()
        pipe.node_positions = {int(k): tuple(v) for k, v in pipeline_cfg.get("node_positions", {}).items()}
        pipe.area_size_m = pipeline_cfg.get("area_size_m", 10.0)
        hw_cfg = pipeline_cfg.get("hardware", {})
        hardware_nodes[node_id] = NodePipelineState(
            node_id,
            pipe,
            min_packets=int(hw_cfg.get("min_packets", 64)),
            refresh_every=int(hw_cfg.get("refresh_every", 32)),
        )
    return hardware_nodes[node_id]


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
    csi: UploadFile = File(...),
    sample_rate: float | None = Form(None),
):
    import shutil
    import cv2

    session_id = str(uuid.uuid4())[:8]
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    video_ext = Path(video.filename or "video.mp4").suffix or ".mp4"
    csi_ext = Path(csi.filename or "csi.npy").suffix or ".npy"
    video_path = session_dir / f"video{video_ext}"
    csi_path = session_dir / f"csi{csi_ext}"

    try:
        with video_path.open("wb") as f:
            shutil.copyfileobj(video.file, f)
        with csi_path.open("wb") as f:
            shutil.copyfileobj(csi.file, f)

        data = load_csi(csi_path, sample_rate_hz=sample_rate)
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

        pipe = build_pipeline(fs_hz=fs_hz, max_targets=3)
        results = pipe.process_session(csi, timestamps_ms, video_duration_sec=duration)
        aligned = align_results(results, duration, n_frames)
        events = [e for e in pipe.tracker.events if _event_in_duration(e, duration)]
        best = max(results, key=lambda r: (r.target_count, r.motion_energy)) if results else None
    except Exception as exc:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cfg = load_config()
    session = SimulationSession(
        session_id=session_id,
        video_path=video_path,
        csi_path=csi_path,
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

    preview = aligned[0] if aligned else {}
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
        "target_count": preview.get("target_count", 0),
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
    min_pkts = int(hw_cfg.get("min_packets", 64))
    window_pkts = int(hw_cfg.get("window_packets", 128))

    active = wireless.active_nodes()
    all_target_dicts: list[dict] = []
    total_count = 0
    resp_bpm = 0.0
    hr_bpm = 0.0
    motion = False
    resp_wave: list[float] = []
    hr_wave: list[float] = []
    node_status = []
    events: list[str] = []
    primary_pipe = None

    for nid in active:
        win = wireless.get_node_window(nid, n=window_pkts)
        rssi = wireless.node_rssi(nid)
        if win is None:
            buf_len = wireless.buffer_length(nid)
            node_status.append({
                "id": nid,
                "status": f"buffering ({buf_len}/{min_pkts})",
                "rssi": rssi,
            })
            continue

        csi, ts = win
        state = _get_hardware_node(nid)
        res = state.process(csi, ts)
        primary_pipe = state.pipeline

        if res is None:
            node_status.append({"id": nid, "status": "warming up", "rssi": rssi})
            continue

        motion = motion or res.motion_detected
        resp_bpm = max(resp_bpm, res.respiration_bpm)
        hr_bpm = max(hr_bpm, res.heartbeat_bpm)
        all_target_dicts.extend(target_to_dict(t) for t in res.targets)
        events.extend(res.events[-2:])

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

    fused = fuse_multinode_targets(all_target_dicts)
    total_count = len(fused)

    return {
        "mode": "hardware",
        "processor_version": PROCESSOR_VERSION,
        "active_nodes": len(active),
        "motion_detected": motion,
        "target_count": total_count,
        "respiration_bpm": round(resp_bpm, 1),
        "heartbeat_bpm": round(hr_bpm, 1),
        "respiration_waveform": resp_wave,
        "heartbeat_waveform": hr_wave,
        "targets": fused,
        "node_status": node_status,
        "node_positions": cfg.get("node_positions", {}),
        "area_size_m": area,
        "events": (primary_pipe.tracker.events[-5:] if primary_pipe else events[-5:]),
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
        await asyncio.sleep(0.25)


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
    hardware_nodes.clear()
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
            "processor_version": PROCESSOR_VERSION,
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hardware_clients.discard(websocket)
