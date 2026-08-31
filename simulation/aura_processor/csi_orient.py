"""Orient raw CSI arrays to (time_frames, subcarriers) for sensing."""

from __future__ import annotations

import numpy as np

# Typical WiFi OFDM subcarrier counts (Intel 5300 = 30/114, ESP32 ≈ 52–64)
COMMON_SUBCARRIERS = {26, 28, 30, 32, 48, 52, 56, 64, 96, 114, 128, 256, 512}


def _is_subcarrier_dim(n: int) -> bool:
    return n in COMMON_SUBCARRIERS or (28 <= n <= 130)


def _pick_axes(shape: tuple[int, ...]) -> tuple[int, int, int | None]:
    """
    Pick (time_axis, subcarrier_axis, antenna_axis) for 2D or 3D CSI.
    Time is usually the largest dimension; subcarriers match known OFDM sizes.
    """
    nd = len(shape)
    if nd == 2:
        a, b = 0, 1
        if _is_subcarrier_dim(shape[a]) and not _is_subcarrier_dim(shape[b]) and shape[b] > shape[a]:
            return b, a, None
        if _is_subcarrier_dim(shape[b]) and not _is_subcarrier_dim(shape[a]) and shape[a] > shape[b]:
            return a, b, None
        if shape[a] < shape[b] and shape[a] <= 256:
            return b, a, None
        return a, b, None

    if nd != 3:
        raise ValueError(f"Expected 2D or 3D CSI, got shape {shape}")

    sc_axis = next((i for i, n in enumerate(shape) if _is_subcarrier_dim(n)), None)
    time_axis = int(np.argmax(shape))
    if sc_axis is None:
        others = [i for i in range(3) if i != time_axis]
        sc_axis = min(others, key=lambda i: shape[i])
    ant_axis = next(i for i in range(3) if i not in (time_axis, sc_axis))
    return time_axis, sc_axis, ant_axis


def orient_csi(csi: np.ndarray, combine_antennas: str = "mean") -> tuple[np.ndarray, dict]:
    """
    Convert arbitrary CSI layout to (T, N_subcarriers) complex64.
    Preserves full complex amplitude + phase.
    """
    arr = np.asarray(csi)
    info: dict = {"input_shape": tuple(arr.shape), "input_dtype": str(arr.dtype)}

    if arr.ndim == 1:
        if arr.dtype == np.complex64 or arr.dtype == np.complex128 or np.iscomplexobj(arr):
            arr = arr.reshape(1, -1)
        elif len(arr) % 2 == 0:
            imag = arr[0::2].astype(np.float32)
            real = arr[1::2].astype(np.float32)
            arr = (real + 1j * imag).reshape(1, -1)
        else:
            raise ValueError(f"Cannot orient 1D CSI shape {arr.shape}")

    if not np.iscomplexobj(arr):
        if arr.ndim == 3 and arr.shape[-1] == 2:
            arr = arr[..., 0] + 1j * arr[..., 1]
        elif arr.ndim == 3 and arr.shape[1] == 2:
            arr = arr[:, 0, :] + 1j * arr[:, 1, :]
        else:
            arr = arr.astype(np.complex64)

    if arr.ndim == 4:
        # (packets, tones, nrx, ntx) or (ntx, nrx, sc, time)
        if arr.shape[-1] == 1 or arr.shape[-2] == 1:
            arr = arr[..., 0, 0]
        elif arr.shape[0] <= 4 and _is_subcarrier_dim(arr.shape[1]):
            arr = arr[0]
        else:
            arr = arr[:, :, 0, 0]

    if arr.ndim == 3:
        t_ax, sc_ax, ant_ax = _pick_axes(arr.shape)
        arr = np.moveaxis(arr, (ant_ax, sc_ax, t_ax), (0, 1, 2))  # (ant, sc, time)
        if arr.shape[0] == 1:
            out = np.moveaxis(arr[0], 0, 1)  # (time, sc)
        elif combine_antennas == "first":
            out = np.moveaxis(arr[0], 0, 1)
        else:
            out = np.moveaxis(np.mean(arr, axis=0), 0, 1)
        info["antenna_axis"] = ant_ax
        info["combined_antennas"] = int(arr.shape[0])
    elif arr.ndim == 2:
        t_ax, sc_ax, _ = _pick_axes(arr.shape)
        if t_ax == 0 and sc_ax == 1:
            out = arr
        else:
            out = arr.T
    else:
        raise ValueError(f"Cannot orient CSI with shape {csi.shape}")

    out = np.ascontiguousarray(out.astype(np.complex64))
    info.update({
        "output_shape": out.shape,
        "is_complex": True,
        "n_frames": int(out.shape[0]),
        "n_subcarriers": int(out.shape[1]),
        "has_phase": bool(np.std(np.angle(out)) > 1e-4),
    })
    return out, info


def combine_amplitude_phase(
    amplitude: np.ndarray,
    phase: np.ndarray,
) -> np.ndarray:
    """Build complex CSI from separate amplitude and phase matrices (radians)."""
    amp = np.asarray(amplitude, dtype=np.float64)
    ph = np.asarray(phase, dtype=np.float64)
    if amp.shape != ph.shape:
        if amp.shape == ph.shape[::-1]:
            ph = ph.T
        else:
            raise ValueError(f"Amplitude {amp.shape} and phase {ph.shape} differ")
    return (amp * np.exp(1j * ph)).astype(np.complex64)
