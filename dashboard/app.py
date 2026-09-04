"""AURA Web Dashboard — WiMANS / dataset simulation only. Live ESP32: tools/field_live.py"""

from __future__ import annotations

import asyncio
import sys
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
from aura_processor.serialize import result_to_dict  # noqa: E402


STATIC_DIR = Path(__file__).resolve().parent / "static"
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    yield


app = FastAPI(title="AURA Dashboard", version="2.0.0", lifespan=_app_lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

PROCESSOR_VERSION = "2026.09.04-41"


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
pipeline_cfg = load_config()


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
        "processor_version": PROCESSOR_VERSION,
        "live_hardware": "python3 tools/field_live.py",
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
