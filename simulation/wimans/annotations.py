"""WiMANS annotation.csv loader and label lookup."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
ANNOTATION_PATH = DATA_DIR / "annotation.csv"

LOCATION_COLS = [f"user_{i}_location" for i in range(1, 7)]
ACTIVITY_COLS = [f"user_{i}_activity" for i in range(1, 7)]


@lru_cache(maxsize=1)
def load_annotations() -> pd.DataFrame:
    df = pd.read_csv(ANNOTATION_PATH, dtype=str)
    df.columns = [c.strip().lstrip("#") for c in df.columns]
    return df


def lookup_label(label: str) -> dict | None:
    """Return annotation row for act_X_Y label stem."""
    stem = Path(label).stem.lower()
    df = load_annotations()
    row = df[df["label"].str.lower() == stem]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "label": r["label"],
        "environment": r["environment"],
        "wifi_band": r["wifi_band"],
        "number_of_users": int(r["number_of_users"]),
        "locations": [r[c] for c in LOCATION_COLS if str(r[c]).strip() and str(r[c]).lower() != "nan"],
        "activities": [r[c] for c in ACTIVITY_COLS if str(r[c]).strip() and str(r[c]).lower() != "nan"],
    }


def encode_identity(row: pd.Series) -> list[int]:
    out = []
    for col in LOCATION_COLS:
        v = str(row[col]).strip().lower()
        out.append(1 if v and v != "nan" else 0)
    return out


def encode_location(row: pd.Series) -> list[int]:
    out = []
    for col in LOCATION_COLS:
        v = str(row[col]).strip().lower()
        if not v or v == "nan":
            out.append(-1)
        else:
            out.append({"a": 0, "b": 1, "c": 2, "d": 3, "e": 4}.get(v, -1))
    return out


def encode_count(row: pd.Series) -> int:
    return int(row["number_of_users"])
