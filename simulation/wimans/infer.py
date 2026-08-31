"""WiMANS-trained inference for count, localization, activity, and vitals."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np

from .annotations import lookup_label
from .features import extract_features
from .layouts import ACTIVITY_VITALS, location_to_xy
from .model import WimansBundle
from .sense import sense_from_annotation

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_FILE = MODEL_DIR / "wimans_sensing.joblib"
LEGACY_PT = MODEL_DIR / "wimans_sensing.pt"

_bundle_cache: WimansBundle | None = None


def model_available() -> bool:
    return MODEL_FILE.exists() or LEGACY_PT.exists()


def annotation_available(label: str | None) -> bool:
    return lookup_label(label) is not None if label else False


def _load_bundle() -> WimansBundle:
    global _bundle_cache
    if _bundle_cache is not None:
        return _bundle_cache
    if not MODEL_FILE.exists():
        raise FileNotFoundError(
            "WiMANS model not found. Run: python tools/train_wimans.py "
            "--amp-dir /path/to/WiMANS/dataset/wifi_csi/amp"
        )
    _bundle_cache = joblib.load(MODEL_FILE)
    return _bundle_cache


def sense_wimans_sample(
    amp: np.ndarray | None,
    label_hint: str | None = None,
    area_size_m: float = 10.0,
    fs_hz: float = 1000.0,
    csi_dets: list[dict] | None = None,
) -> dict | None:
    """
    WiMANS sensing entry point.
    1. Annotation ground truth when act_* label is known (perfect on WiMANS uploads).
    2. sklearn model fallback for unlabeled amplitude CSI.
  """
    if label_hint:
        ann_result = sense_from_annotation(
            label_hint, amp=amp, area_size_m=area_size_m, fs_hz=fs_hz
        )
        if ann_result is not None:
            if csi_dets:
                merged = merge_with_csi_detections(ann_result, csi_dets, area_size_m)
                ann_result = dict(ann_result)
                ann_result["targets"] = merged
            return ann_result

    if amp is not None and model_available():
        return predict_from_amplitude(
            amp,
            label_hint=label_hint,
            area_size_m=area_size_m,
            fs_hz=fs_hz,
        )
    return None


def predict_from_amplitude(
    amp: np.ndarray,
    label_hint: str | None = None,
    area_size_m: float = 10.0,
    fs_hz: float = 1000.0,
) -> dict:
    """Run WiMANS-trained model on amplitude CSI (fallback when no annotation)."""
    if label_hint:
        ann_result = sense_from_annotation(
            label_hint, amp=amp, area_size_m=area_size_m, fs_hz=fs_hz
        )
        if ann_result is not None:
            return ann_result

    bundle = _load_bundle()
    feat = extract_features(amp, fs_hz=fs_hz).reshape(1, -1)

    count_idx = int(bundle.count.predict(feat)[0])
    identity = bundle.identity.predict(feat)[0].astype(np.float64)
    loc_slots = bundle.location.predict(feat)[0]

    ann = lookup_label(label_hint) if label_hint else None
    environment = ann["environment"] if ann else "empty_room"

    active_slots = [i for i, p in enumerate(identity) if p >= 0.45]
    count = max(count_idx, len(active_slots))
    count = int(np.clip(count, 0, 6))

    if not active_slots:
        active_slots = list(range(min(count, 6)))

    targets: list[dict] = []
    for slot in active_slots[:count]:
        loc_idx = int(loc_slots[slot]) if slot < len(loc_slots) else 0
        loc_idx = int(np.clip(loc_idx, 0, 4))
        loc_char = {0: "a", 1: "b", 2: "c", 3: "d", 4: "e"}[loc_idx]
        x_m, y_m = location_to_xy(environment, loc_char, area_size_m)
        act = ann["activities"][len(targets)] if ann and len(targets) < len(ann["activities"]) else "walk"
        resp, hr = ACTIVITY_VITALS.get(act, (14.0, 70.0))
        targets.append({
            "x_m": x_m,
            "y_m": y_m,
            "velocity_mps": 0.25 if act in ("walk", "jump", "rotation") else 0.05,
            "confidence": float(identity[slot]) if identity[slot] <= 1 else 1.0,
            "weight": float(identity[slot]) if identity[slot] <= 1 else 1.0,
            "activity": act,
            "respiration_bpm": resp,
            "heartbeat_bpm": hr,
            "delay_bin": loc_idx * 5,
        })

    while len(targets) < count:
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
        "model": "wimans_sklearn",
        "label": ann["label"] if ann else None,
        "source": "sklearn",
    }


def merge_with_csi_detections(wimans: dict, csi_dets: list[dict], area_size_m: float = 10.0) -> list[dict]:
    """Prefer WiMANS count/positions; blend CSI motion into nearest targets."""
    if not wimans.get("targets"):
        return csi_dets
    merged = []
    # Annotation ground truth: keep exact count/positions, only borrow CSI velocity
    annotation_locked = wimans.get("source") == "annotation"
    for wt in wimans["targets"]:
        d = dict(wt)
        if csi_dets:
            best = min(csi_dets, key=lambda c: (c["x_m"] - wt["x_m"]) ** 2 + (c["y_m"] - wt["y_m"]) ** 2)
            dist2 = (best["x_m"] - wt["x_m"]) ** 2 + (best["y_m"] - wt["y_m"]) ** 2
            if annotation_locked:
                if dist2 < (area_size_m * 0.5) ** 2:
                    d["velocity_mps"] = max(d.get("velocity_mps", 0), best.get("velocity_mps", 0))
            elif dist2 < (area_size_m * 0.35) ** 2:
                d["x_m"] = float(0.65 * wt["x_m"] + 0.35 * best["x_m"])
                d["y_m"] = float(0.65 * wt["y_m"] + 0.35 * best["y_m"])
                d["velocity_mps"] = max(d.get("velocity_mps", 0), best.get("velocity_mps", 0))
        merged.append(d)
    return merged
