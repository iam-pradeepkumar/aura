#!/usr/bin/env bash
# Flash AURA TX probe (joins AURA_HUB hotspot, probes on AP channel).
# Usage: ./tools/flash_tx.sh [/dev/ttyUSB0]

set -euo pipefail

PORT="${1:-/dev/ttyUSB0}"
BAUD="${BAUD:-57600}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TX_DIR="$ROOT/firmware/aura_tx"

if [[ -z "${IDF_PATH:-}" ]]; then
  # shellcheck disable=SC1091
  . "$HOME/esp/esp-idf/export.sh"
fi

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  echo "WARNING: Run 'deactivate' before flashing."
fi

cd "$TX_DIR"
echo "Flashing AURA TX on $PORT ..."
idf.py set-target esp32 2>/dev/null || true
idf.py -b "$BAUD" build flash -p "$PORT"
echo "Monitor: idf.py -p $PORT monitor"
echo "Expect: TX linked — IP ... | probing on AP channel N"
