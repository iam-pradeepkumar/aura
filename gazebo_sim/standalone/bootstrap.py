"""Bootstrap paths + optional scipy shim before aura_processor imports."""

from __future__ import annotations

import sys
from pathlib import Path


def bootstrap() -> Path:
    root = Path(__file__).resolve().parents[2]
    sim = root / "simulation"
    gz = root / "gazebo_sim"
    for p in (str(sim), str(gz)):
        if p not in sys.path:
            sys.path.insert(0, p)
    from aura_processor._scipy_compat import install_scipy_shim

    install_scipy_shim()
    return root
