"""ESP32 live CSI normalization for outdoor field deployment."""

from __future__ import annotations

import numpy as np

TARGET_SUBCARRIERS = 64


def normalize_esp32_csi(csi: np.ndarray) -> np.ndarray:
    """
    Stabilize variable ESP32 CSI shapes for the shared DSP chain.
    - Collapse MIMO to mean if needed
    - Trim/pad to TARGET_SUBCARRIERS
    - Remove DC spike on subcarrier 0
    """
    x = np.asarray(csi)
    if x.ndim == 1:
        x = x.reshape(1, -1)
    if x.ndim > 2:
        x = x.reshape(x.shape[0], -1)
    if x.shape[1] > TARGET_SUBCARRIERS:
        # ESP32: keep central subcarriers (less edge noise outdoors)
        start = (x.shape[1] - TARGET_SUBCARRIERS) // 2
        x = x[:, start : start + TARGET_SUBCARRIERS]
    elif x.shape[1] < TARGET_SUBCARRIERS:
        pad = TARGET_SUBCARRIERS - x.shape[1]
        x = np.pad(x, ((0, 0), (0, pad)), mode="edge")
    if x.shape[1] > 0:
        x[:, 0] = np.median(x[:, 1:5], axis=1) if x.shape[1] > 4 else x[:, 0]
    return x.astype(np.complex128 if np.iscomplexobj(x) else np.float64, copy=False)
