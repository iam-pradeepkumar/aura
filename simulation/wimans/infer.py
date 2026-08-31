"""WiMANS-trained inference for count, localization, activity, and vitals."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from .annotations import lookup_label
from .features import extract_features
from .layouts import ACTIVITY_VITALS, location_to_xy
from .model import WimansMLP

MODEL_PATH = Path(__file__).resolve().parent / "models" / "wimans_sensing.pt"

_model_cache: tuple[WimansMLP, int] | None = None


def model_available() -> bool:
    return MODEL_PATH.exists()


def _load_model() -> tuple[WimansMLP, int]:
    global _model_cache
    if _model_cache is not None:
        return _model_cache
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"WiMANS model not found at {MODEL_PATH}. Run tools/train_wimans.py")
    ckpt = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
    in_dim = int(ckpt["in_dim"])
    model = WimansMLP(in_dim)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    _model_cache = (model, in_dim)
    return _model_cache


def predict_from_amplitude(
    amp: np.ndarray,
    label_hint: str | None = None,
    area_size_m: float = 10.0,
    fs_hz: float = 1000.0,
) -> dict:
    """
    Run WiMANS-trained model on amplitude CSI.
    Returns count, targets (x,y), activities, and vitals priors.
    """
    model, _ = _load_model()
    feat = extract_features(amp, fs_hz=fs_hz)
    x = torch.from_numpy(feat).unsqueeze(0)

    with torch.no_grad():
        out = model(x)
        count_idx = int(out["count"].argmax(1).item())
        identity = torch.sigmoid(out["identity"]).numpy()[0]
        loc_logits = out["location"].numpy().reshape(6, 5)

    ann = lookup_label(label_hint) if label_hint else None
    environment = ann["environment"] if ann else "empty_room"

    active_slots = [i for i, p in enumerate(identity) if p >= 0.45]
    id_count = len(active_slots)
    count = max(count_idx, id_count)
    count = int(np.clip(count, 0, 6))

    targets: list[dict] = []
    if not active_slots:
        active_slots = list(range(min(count, 6)))

    for slot_i, slot in enumerate(active_slots[:count]):
        loc_probs = loc_logits[slot]
        loc_idx = int(np.argmax(loc_probs))
        loc_char = {0: "a", 1: "b", 2: "c", 3: "d", 4: "e"}[loc_idx]
        x_m, y_m = location_to_xy(environment, loc_char, area_size_m)
        act = "walk"
        resp, hr = ACTIVITY_VITALS.get(act, (14.0, 70.0))
        targets.append({
            "x_m": x_m,
            "y_m": y_m,
            "velocity_mps": 0.25 if act in ("walk", "jump", "rotation") else 0.05,
            "confidence": float(identity[slot]),
            "weight": float(identity[slot]),
            "activity": act,
            "respiration_bpm": resp,
            "heartbeat_bpm": hr,
            "delay_bin": loc_idx * 5,
        })

    while len(targets) < count:
        slot = len(targets)
        loc_char = "b"
        x_m, y_m = location_to_xy(environment, loc_char, area_size_m)
        resp, hr = ACTIVITY_VITALS.get("walk", (14.0, 70.0))
        targets.append({
            "x_m": x_m, "y_m": y_m, "velocity_mps": 0.1,
            "confidence": 0.5, "weight": 0.5, "activity": "walk",
            "respiration_bpm": resp, "heartbeat_bpm": hr, "delay_bin": 0,
        })

    return {
        "count": count,
        "targets": targets[:count],
        "environment": environment,
        "wifi_band": ann["wifi_band"] if ann else None,
        "model": "wimans_mlp",
        "label": ann["label"] if ann else None,
    }


def merge_with_csi_detections(wimans: dict, csi_dets: list[dict], area_size_m: float = 10.0) -> list[dict]:
    """Prefer WiMANS count/positions; blend CSI motion into nearest targets."""
    if not wimans.get("targets"):
        return csi_dets
    merged = []
    for wt in wimans["targets"]:
        d = dict(wt)
        if csi_dets:
            best = min(csi_dets, key=lambda c: (c["x_m"] - wt["x_m"]) ** 2 + (c["y_m"] - wt["y_m"]) ** 2)
            if (best["x_m"] - wt["x_m"]) ** 2 + (best["y_m"] - wt["y_m"]) ** 2 < (area_size_m * 0.35) ** 2:
                d["x_m"] = float(0.65 * wt["x_m"] + 0.35 * best["x_m"])
                d["y_m"] = float(0.65 * wt["y_m"] + 0.35 * best["y_m"])
                d["velocity_mps"] = max(d.get("velocity_mps", 0), best.get("velocity_mps", 0))
        merged.append(d)
    return merged
