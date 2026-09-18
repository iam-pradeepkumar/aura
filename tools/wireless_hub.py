#!/usr/bin/env python3
"""
Legacy entry point — redirects to AURA Field Live (full rescue pipeline).

Use: python3 tools/field_live.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.field_live import main


if __name__ == "__main__":
    print("Note: wireless_hub.py now uses the full Field Live engine (calibration, fusion, tracking).")
    print("For disaster rescue deployment, use: python3 tools/field_live.py\n")
    main()
