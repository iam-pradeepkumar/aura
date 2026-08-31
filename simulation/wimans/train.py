"""Train WiMANS sensing models on amplitude CSI + annotations."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, TensorDataset

from .annotations import ANNOTATION_PATH, encode_count, encode_identity, encode_location, load_annotations
from .features import extract_features
from .model import WimansMLP
from .synthetic import synth_amplitude

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(exist_ok=True)


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
    max_samples: int | None = None,
    use_synthetic: bool = True,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build feature matrix and labels from real amp files and/or synthetic CSI."""
    df = load_annotations()
    if max_samples:
        df = df.iloc[:max_samples]

    rng = np.random.default_rng(seed)
    xs, y_count, y_id, y_loc = [], [], [], []

    for idx, row in df.iterrows():
        label = row["label"]
        amp = None
        if amp_dir is not None:
            p = amp_dir / f"{label}.npy"
            if p.exists():
                amp = _load_amp(p)

        if amp is None and use_synthetic:
            locs = [str(row[c]) for c in [f"user_{i}_location" for i in range(1, 7)] if str(row[c]).strip() and str(row[c]).lower() != "nan"]
            acts = [str(row[c]) for c in [f"user_{i}_activity" for i in range(1, 7)] if str(row[c]).strip() and str(row[c]).lower() != "nan"]
            amp = synth_amplitude(int(row["number_of_users"]), locs, acts, seed=int(rng.integers(0, 1_000_000)))

        if amp is None:
            continue

        xs.append(extract_features(amp))
        y_count.append(encode_count(row))
        y_id.append(encode_identity(row))
        y_loc.append(encode_location(row))

    return (
        np.stack(xs),
        np.asarray(y_count, dtype=np.int64),
        np.asarray(y_id, dtype=np.float32),
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
    out = Path(out_dir or MODEL_DIR)
    out.mkdir(parents=True, exist_ok=True)

    amp_path = Path(amp_dir) if amp_dir else None
    x, y_count, y_id, y_loc = build_dataset(amp_path, max_samples=max_samples, use_synthetic=use_synthetic)

    n = len(x)
    split = int(n * 0.85)
    perm = np.random.default_rng(39).permutation(n)
    tr, te = perm[:split], perm[split:]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = WimansMLP(x.shape[1]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    ce = torch.nn.CrossEntropyLoss()
    bce = torch.nn.BCEWithLogitsLoss()

    tx = torch.from_numpy(x[tr])
    ty_c = torch.from_numpy(y_count[tr])
    ty_i = torch.from_numpy(y_id[tr])
    ty_l = torch.from_numpy(y_loc[tr])

    ty_l_oh = torch.zeros(len(ty_l), 6, 5)
    for i in range(len(ty_l)):
        for s in range(6):
            if y_loc[tr][i, s] >= 0:
                ty_l_oh[i, s, y_loc[tr][i, s]] = 1.0

    loader = DataLoader(TensorDataset(tx, ty_c, ty_i, ty_l_oh.reshape(len(ty_l), -1)), batch_size=batch_size, shuffle=True)

    best_acc = 0.0
    best_state = None

    for epoch in range(epochs):
        model.train()
        for bx, bc, bi, bl in loader:
            bx, bc, bi, bl = bx.to(device), bc.to(device), bi.to(device), bl.to(device)
            out_pred = model(bx)
            loss = (
                ce(out_pred["count"], bc)
                + bce(out_pred["identity"], bi)
                + bce(out_pred["location"], bl)
            )
            opt.zero_grad()
            loss.backward()
            opt.step()

        model.eval()
        with torch.no_grad():
            pred = model(torch.from_numpy(x[te]).to(device))
            acc = float((pred["count"].argmax(1) == torch.from_numpy(y_count[te]).to(device)).float().mean())
        if acc > best_acc:
            best_acc = acc
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if (epoch + 1) % 10 == 0:
            print(f"epoch {epoch+1}/{epochs} test_count_acc={acc:.4f}")

    if best_state:
        model.load_state_dict(best_state)

    ckpt = {
        "state_dict": model.state_dict(),
        "in_dim": int(x.shape[1]),
        "annotation": str(ANNOTATION_PATH),
        "trained_samples": int(n),
        "real_amp_dir": str(amp_path) if amp_path else None,
        "use_synthetic": use_synthetic,
        "test_count_acc": best_acc,
    }
    torch.save(ckpt, out / "wimans_sensing.pt")
    meta = {k: v for k, v in ckpt.items() if k != "state_dict"}
    (out / "wimans_sensing.json").write_text(json.dumps(meta, indent=2))
    print(f"Saved model to {out / 'wimans_sensing.pt'} (count acc {best_acc:.4f}, n={n})")
    return meta
