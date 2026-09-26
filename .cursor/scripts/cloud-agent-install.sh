#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for AURA.
# Dependencies are installed in .cursor/Dockerfile at image build time.
# This script verifies imports and prepares runtime data directories.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

mkdir -p disaster_alert/data dashboard/uploads

python3 <<'PY'
import importlib
import sys

required = [
    "numpy",
    "scipy",
    "matplotlib",
    "pandas",
    "yaml",
    "fastapi",
    "uvicorn",
    "sklearn",
    "cv2",
    "h5py",
    "serial",
]
missing = []
for name in required:
    try:
        importlib.import_module(name)
    except ImportError:
        missing.append(name)

if missing:
    print("Missing Python packages:", ", ".join(missing))
    print("Rebuild the environment image (.cursor/Dockerfile) or allow pypi.org egress.")
    sys.exit(1)

print("AURA dependency check OK")
PY

echo "AURA install OK ($(python3 --version))"
