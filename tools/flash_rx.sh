#!/usr/bin/env bash
# Flash one AURA RX board with a unique node ID (1-4).
# Usage:  ./tools/flash_rx.sh 2
#         ./tools/flash_rx.sh 3 /dev/ttyUSB0

set -euo pipefail

NODE_ID="${1:-}"
PORT="${2:-/dev/ttyUSB0}"
BAUD="${BAUD:-57600}"

if [[ -z "$NODE_ID" || ! "$NODE_ID" =~ ^[1-4]$ ]]; then
  echo "Usage: $0 <node_id 1-4> [serial_port]"
  echo "Example: $0 2 /dev/ttyUSB0"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RX_DIR="$ROOT/firmware/aura_rx"

if [[ -z "${IDF_PATH:-}" ]]; then
  if [[ -f "$HOME/esp/esp-idf/export.sh" ]]; then
  # shellcheck disable=SC1091
    . "$HOME/esp/esp-idf/export.sh"
  else
    echo "ESP-IDF not loaded. Run: . ~/esp/esp-idf/export.sh"
    exit 1
  fi
fi

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  echo "WARNING: Python venv is active ($VIRTUAL_ENV). Run 'deactivate' first."
fi

cd "$RX_DIR"
export AURA_NODE_ID="$NODE_ID"

echo "============================================"
echo " Flashing AURA RX node ID = $NODE_ID"
echo " Port: $PORT  Baud: $BAUD"
echo "============================================"

idf.py -D "AURA_RX_NODE_ID=$NODE_ID" reconfigure
idf.py -D "AURA_RX_NODE_ID=$NODE_ID" -b "$BAUD" build flash -p "$PORT"

echo ""
echo "Done. Verify with: idf.py -p $PORT monitor"
echo "Log MUST show:  RX node $NODE_ID  and  (node $NODE_ID, DHCP gateway)"
