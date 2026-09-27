"""AURA - Adaptive Urban Rescue & Alert Array signal processing."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "load_csi",
    "load_csi_csv",
    "load_csi_binary",
    "load_csi_npy",
    "load_csi_mat",
    "load_csi_npz",
    "merge_csi_mat_npy",
    "amplitude_to_complex",
    "AURAPipeline",
    "SensingResult",
]

if TYPE_CHECKING:
    from .loader import (
        load_csi,
        load_csi_csv,
        load_csi_binary,
        load_csi_npy,
        load_csi_mat,
        load_csi_npz,
        merge_csi_mat_npy,
        amplitude_to_complex,
    )
    from .pipeline import AURAPipeline, SensingResult


def __getattr__(name: str):
    if name in (
        "load_csi",
        "load_csi_csv",
        "load_csi_binary",
        "load_csi_npy",
        "load_csi_mat",
        "load_csi_npz",
        "merge_csi_mat_npy",
        "amplitude_to_complex",
    ):
        from .loader import (
            load_csi,
            load_csi_csv,
            load_csi_binary,
            load_csi_npy,
            load_csi_mat,
            load_csi_npz,
            merge_csi_mat_npy,
            amplitude_to_complex,
        )
        return {
            "load_csi": load_csi,
            "load_csi_csv": load_csi_csv,
            "load_csi_binary": load_csi_binary,
            "load_csi_npy": load_csi_npy,
            "load_csi_mat": load_csi_mat,
            "load_csi_npz": load_csi_npz,
            "merge_csi_mat_npy": merge_csi_mat_npy,
            "amplitude_to_complex": amplitude_to_complex,
        }[name]
    if name in ("AURAPipeline", "SensingResult"):
        from .pipeline import AURAPipeline, SensingResult
        return AURAPipeline if name == "AURAPipeline" else SensingResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
