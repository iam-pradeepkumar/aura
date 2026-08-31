"""Train WiMANS sensing models on amplitude CSI + annotations (scikit-learn only)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import accuracy_score

from .amp_index import index_amp_files, resolve_amp_dir
from .annotations import ANNOTATION_PATH, encode_count, encode_identity, encode_location, load_annotations
from .features import extract_features
from .model import WimansBundle, make_count_model, make_identity_model, make_location_model
from .synthetic import synth_amplitude

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(exist_ok=True)
MODEL_FILE = MODEL_DIR / "wimans_sensing.joblib"


def _load_amp(path: Path) -> np.ndarray | None:
    try:
        arr = np.load(path, allow_pickle=True)
        if isinstance(arr, np.lib.npyio.NpzFile):
            arr = arr[list(arr.files)[0]]
        return np.asarray(arr, dtype=np.float32)
    except Exception:
        return None


def build_dataset(
    amp_dir: Path | None = None,
    amp_index: dict[str, Path] | None = None,
    max_samples: int | None = None,
    use_synthetic: bool = True,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build feature matrix and labels from real amp files and/or synthetic CSI."""
    df = load_annotations()
    if max_samples:
        df = df.iloc[:max_samples]

    if amp_dir is not None and amp_index is None:
        amp_index = index_amp_files(amp_dir)

    rng = np.random.default_rng(seed)
    xs, y_count, y_id, y_loc = [], [], [], []
    real_count = 0

    for _, row in df.iterrows():
        label = str(row["label"]).lower()
        amp = None
        if amp_index:
            p = amp_index.get(label)
            if p is not None:
                amp = _load_amp(p)
                if amp is not None:
                    real_count += 1

        if amp is None and use_synthetic:
            locs = [
                str(row[c]) for c in [f"user_{i}_location" for i in range(1, 7)]
                if str(row[c]).strip() and str(row[c]).lower() != "nan"
            ]
            acts = [
                str(row[c]) for c in [f"user_{i}_activity" for i in range(1, 7)]
                if str(row[c]).strip() and str(row[c]).lower() != "nan"
            ]
            amp = synth_amplitude(
                int(row["number_of_users"]), locs, acts, seed=int(rng.integers(0, 1_000_000))
            )

        if amp is None:
            continue

        xs.append(extract_features(amp))
        y_count.append(encode_count(row))
        y_id.append(encode_identity(row))
        loc = encode_location(row)
        y_loc.append([max(0, v) for v in loc])

    if not xs:
        raise ValueError(
            "No training samples could be built. "
            "Run: python tools/train_wimans.py --synthetic-only"
        )

    if amp_index and real_count == 0:
        print(
            "WARNING: No act_*.npy files matched annotation labels in that folder. "
            "Training on synthetic CSI only. Fix --amp-dir or run:\n"
            "  find ~ -name 'act_100_5.npy' 2>/dev/null"
        )
    elif real_count > 0:
        print(f"Loaded {real_count} real .npy files")

    return (
        np.stack(xs),
        np.asarray(y_count, dtype=np.int64),
        np.asarray(y_id, dtype=np.int64),
        np.asarray(y_loc, dtype=np.int64),
    )


def train_models(
    amp_dir: str | Path | None = None,
    epochs: int = 40,
    batch_size: int = 128,
    max_samples: int | None = None,
    use_synthetic: bool = True,
    out_dir: str | Path | None = None,
) -> dict:
    del epochs, batch_size  # kept for CLI compatibility

    out = Path(out_dir or MODEL_DIR)
    out.mkdir(parents=True, exist_ok=True)

    amp_path = Path(amp_dir) if amp_dir else None
    amp_index = index_amp_files(amp_path) if amp_path else None
    x, y_count, y_id, y_loc = build_dataset(
        amp_path, amp_index=amp_index, max_samples=max_samples, use_synthetic=use_synthetic
    )

    n = len(x)
    split = int(n * 0.85)
    perm = np.random.default_rng(39).permutation(n)
    tr, te = perm[:split], perm[split:]

    count_clf = make_count_model()
    identity_clf = make_identity_model()
    location_clf = make_location_model()

    print(f"Training on {len(tr)} samples (test {len(te)})...")
    count_clf.fit(x[tr], y_count[tr])
    identity_clf.fit(x[tr], y_id[tr])
    location_clf.fit(x[tr], y_loc[tr])

    count_acc = float(accuracy_score(y_count[te], count_clf.predict(x[te])))
    id_pred = identity_clf.predict(x[te])
    loc_pred = location_clf.predict(x[te])
    id_acc = float(np.mean(id_pred == y_id[te]))
    loc_acc = float(np.mean(loc_pred == y_loc[te]))

    bundle = WimansBundle(
        count=count_clf,
        identity=identity_clf,
        location=location_clf,
        in_dim=int(x.shape[1]),
        backend="sklearn",
    )
    joblib.dump(bundle, out / "wimans_sensing.joblib")

    meta = {
        "backend": "sklearn",
        "in_dim": int(x.shape[1]),
        "annotation": str(ANNOTATION_PATH),
        "trained_samples": int(n),
        "real_amp_dir": str(amp_path) if amp_path else None,
        "use_synthetic": use_synthetic,
        "test_count_acc": count_acc,
        "test_identity_acc": id_acc,
        "test_location_acc": loc_acc,
    }
    (out / "wimans_sensing.json").write_text(json.dumps(meta, indent=2))
    print(
        f"Saved {out / 'wimans_sensing.joblib'} "
        f"(count={count_acc:.4f} identity={id_acc:.4f} location={loc_acc:.4f})"
    )
    return meta
