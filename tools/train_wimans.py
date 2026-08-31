#!/usr/bin/env python3
"""
Train WiMANS sensing models for AURA.

With real WiMANS amplitude files (recommended):
  python tools/train_wimans.py --amp-dir /path/to/WiMANS/dataset/wifi_csi/amp --epochs 60

Bootstrap (synthetic, shipped by default):
  python tools/train_wimans.py --synthetic-only

No PyTorch required — uses scikit-learn only (~50 MB disk vs 500+ MB for torch).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "simulation"))

from wimans.train import train_models  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="Train AURA WiMANS sensing models")
    p.add_argument("--amp-dir", type=str, default=None, help="Path to WiMANS wifi_csi/amp folder")
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--max-samples", type=int, default=None, help="Limit samples for quick tests")
    p.add_argument("--synthetic-only", action="store_true", help="Train only on synthetic CSI")
    p.add_argument("--out-dir", type=str, default=None)
    args = p.parse_args()

    meta = train_models(
        amp_dir=args.amp_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        max_samples=args.max_samples,
        use_synthetic=args.synthetic_only or args.amp_dir is None,
        out_dir=args.out_dir,
    )
    print(meta)


if __name__ == "__main__":
    main()
