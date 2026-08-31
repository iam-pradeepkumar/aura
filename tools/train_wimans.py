#!/usr/bin/env python3
"""
Train WiMANS sensing models for AURA (scikit-learn only — no PyTorch).

Examples:
  python tools/train_wimans.py
  python tools/train_wimans.py --synthetic-only
  python tools/train_wimans.py --amp-dir ~/Downloads/WiMANS
  python tools/train_wimans.py --amp-dir ~/Downloads/WiMANS/dataset/wifi_csi/amp
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "simulation"))

from wimans.amp_index import resolve_amp_dir  # noqa: E402
from wimans.train import train_models  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="Train AURA WiMANS sensing models")
    p.add_argument(
        "--amp-dir",
        type=str,
        default=None,
        help="WiMANS folder (dataset root, wifi_csi/, or amp/ — auto-detected)",
    )
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--max-samples", type=int, default=None)
    p.add_argument(
        "--synthetic-only",
        action="store_true",
        help="Ignore .npy files; train on synthetic CSI only",
    )
    p.add_argument("--out-dir", type=str, default=None)
    args = p.parse_args()

    amp_path = None
    amp_index = None

    if args.amp_dir and not args.synthetic_only:
        amp_path, amp_index = resolve_amp_dir(args.amp_dir)
        if amp_path is None:
            print(f"WARNING: path not found: {args.amp_dir}", file=sys.stderr)
            print("Falling back to synthetic training.", file=sys.stderr)
        elif not amp_index:
            print(f"WARNING: no act_*.npy under {amp_path}", file=sys.stderr)
            print("Try: find ~ -name 'act_100_5.npy' 2>/dev/null", file=sys.stderr)
            print("Falling back to synthetic training.", file=sys.stderr)
            amp_path, amp_index = None, None
        else:
            print(f"Using {len(amp_index)} act_*.npy files from {amp_path}")

    # Always allow synthetic fill-in so training never crashes on bad paths
    use_synthetic = True

    meta = train_models(
        amp_dir=str(amp_path) if amp_path and amp_index else None,
        epochs=args.epochs,
        batch_size=args.batch_size,
        max_samples=args.max_samples,
        use_synthetic=use_synthetic,
        out_dir=args.out_dir,
    )
    print(meta)


if __name__ == "__main__":
    main()
