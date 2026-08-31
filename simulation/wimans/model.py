"""Lightweight scikit-learn models for WiMANS sensing (no PyTorch required)."""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.multioutput import MultiOutputClassifier


def make_count_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=200,
        learning_rate=0.08,
        max_depth=8,
        random_state=39,
    )


def make_identity_model() -> MultiOutputClassifier:
    return MultiOutputClassifier(
        HistGradientBoostingClassifier(max_iter=100, max_depth=7, learning_rate=0.1, random_state=39),
    )


def make_location_model() -> MultiOutputClassifier:
    return MultiOutputClassifier(
        HistGradientBoostingClassifier(max_iter=100, max_depth=7, learning_rate=0.1, random_state=41),
    )


@dataclass
class WimansBundle:
    count: HistGradientBoostingClassifier
    identity: MultiOutputClassifier
    location: MultiOutputClassifier
    in_dim: int
    backend: str = "sklearn"
