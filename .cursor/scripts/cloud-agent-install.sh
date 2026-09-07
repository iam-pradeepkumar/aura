#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for AURA.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

python3 -m pip install --upgrade pip --quiet
python3 -m pip install -r simulation/requirements.txt -r dashboard/requirements.txt -r tools/requirements.txt pytest --quiet

# Ensure runtime data dirs exist (settings are gitignored).
mkdir -p disaster_alert/data dashboard/uploads

echo "AURA install OK ($(python3 --version))"
