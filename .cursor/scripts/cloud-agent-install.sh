#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for AURA.
# Prefer deps baked in via .cursor/Dockerfile; fall back to pip when PyPI is reachable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

mkdir -p disaster_alert/data dashboard/uploads

need_pip=0
python3 <<'PY' || need_pip=1
import importlib
required = [
    "numpy", "scipy", "matplotlib", "pandas", "yaml",
    "fastapi", "uvicorn", "sklearn", "cv2", "h5py", "serial",
]
missing = []
for name in required:
    try:
        importlib.import_module(name)
    except ImportError:
        missing.append(name)
if missing:
    raise SystemExit(1)
print("AURA dependency check OK (preinstalled)")
PY

if [[ "$need_pip" -eq 1 ]]; then
  echo "Installing Python dependencies via pip..."
  python3 -m pip install --upgrade pip --quiet || true
  python3 -m pip install -r simulation/requirements.txt -r dashboard/requirements.txt -r tools/requirements.txt pytest --quiet
  python3 <<'PY'
import importlib
import importlib.util
required = ["numpy", "scipy", "matplotlib", "pandas", "yaml", "fastapi", "uvicorn", "sklearn", "cv2", "h5py", "serial"]
missing = [n for n in required if importlib.util.find_spec(n) is None]
if missing:
    print("Still missing after pip:", ", ".join(missing))
    print("Approve pypi.org + files.pythonhosted.org egress, or Save environment with Dockerfile build.")
    raise SystemExit(1)
print("AURA dependency check OK (pip)")
PY
fi

echo "AURA install OK ($(python3 --version))"
