#!/usr/bin/env python3
"""Start the AURA web dashboard at http://127.0.0.1:8847"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "dashboard.app:app",
        host="0.0.0.0",
        port=8847,
        reload=False,
    )
