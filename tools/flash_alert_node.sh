#!/usr/bin/env bash
# Flash the ONE AURA alert monitor node (hazard APIs + LAN alert page).
# Rescue nodes use flash_rx.sh — do NOT flash aura_alert on all boards.
set -euo pipefail
PORT="${1:-/dev/ttyUSB0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ALERT_DIR="$ROOT/firmware/aura_alert_node"

if [[ -z "${IDF_PATH:-}" ]]; then
  # shellcheck disable=SC1091
  . "$HOME/esp/esp-idf/export.sh"
fi

if [[ ! -d "$ALERT_DIR" ]]; then
  echo "ERROR: firmware/aura_alert_node not found."
  exit 1
fi

cd "$ALERT_DIR"
echo "============================================"
echo " Flashing AURA ALERT NODE (single monitor)"
echo " Port: $PORT"
echo " Rescue RX nodes: use ./tools/flash_rx.sh N"
echo "============================================"
idf.py set-target esp32 2>/dev/null || true
idf.py -b 57600 build flash -p "$PORT"
echo "Monitor: idf.py -p $PORT monitor"
echo "Expect: alert node on public WiFi + http://<ip>:8080/alert"
