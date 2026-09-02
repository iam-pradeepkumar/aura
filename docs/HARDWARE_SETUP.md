# AURA Hardware Setup Guide

Complete guide for building and deploying AURA ESP32 nodes in an **outdoor disaster field** — wireless CSI streaming to a laptop, no internet required.

---

## 1. Components list

### Required

| Item | Qty | Est. cost | Notes |
|------|-----|-----------|-------|
| **ESP32-C6** dev kit | 5 | ~$8–15 each | Best RF; also ESP32 / ESP32-C3 supported |
| **External 2.4 GHz antenna** (U.FL/IPX) | 5 | ~$3–8 each | PCB antennas fail through rubble — use external |
| **5V USB power banks** (10,000 mAh+) | 5 | ~$15–25 each | 8+ hours field use per node |
| **Laptop** (Linux / macOS / Windows) | 1 | — | Python 3.10+, WiFi hotspot capability |
| **Measuring tape** | 1 | — | Record node XY for `config.yaml` |

### Recommended

| Item | Qty | Notes |
|------|-----|-------|
| Tripods or magnetic mounts | 5 | Mount nodes 1–2 m height at perimeter |
| USB cables (data-capable) | 2 | Flashing firmware + optional UART backup |
| Phone / camera | 1 | Optional scene video for post-mission simulation replay |
| Portable WiFi hotspot or laptop hotspot | 1 | SSID `AURA_HUB` (built into laptop is fine) |

### Optional

| Item | Notes |
|------|-------|
| UART recording | `tools/record_session.py` if UDP link fails |
| Second laptop | Monitor + command post separately |

---

## 2. Node roles

| Role | Firmware | Count | Purpose |
|------|----------|-------|---------|
| **TX (Transmitter)** | `firmware/aura_tx` | 1 | Broadcasts 802.11 probe frames on **channel 6** (~20 Hz) |
| **RX (Receiver)** | `firmware/aura_rx` | 3–4 | Captures CSI, streams to laptop via **WiFi UDP** |

**Minimum:** 1 TX + 3 RX (triangle perimeter)  
**Recommended:** 1 TX + 4 RX (square perimeter, 10 m × 10 m search area)

RX nodes join the laptop hotspot (`AURA_HUB`) and send CSI to **UDP port 5555**. No USB cable is needed during live operation.

---

## 3. Physical layout

Example **10 m × 10 m** disaster search cell:

```
        Node 4 (0,10) ───────────── Node 3 (10,10)
              │                           │
              │    [Collapsed structure]    │
              │         (search area)       │
              │                           │
        Node 1 (0,0) ────────────── Node 2 (10,0)

        TX probe: outside perimeter, ~2 m from edge
                   e.g. (5, -2) in config.yaml
```

1. Measure each node position in meters (origin = southwest corner).
2. Enter values in `simulation/config.yaml`:

```yaml
area_size_m: 10.0
motion_threshold: 0.02
max_people: 8

node_positions:
  1: [0.0, 0.0]      # southwest
  2: [10.0, 0.0]     # southeast
  3: [10.0, 10.0]    # northeast
  4: [0.0, 10.0]     # northwest

tx_position: [5.0, -2.0]   # informational

hardware:
  min_packets: 80          # ~4 s buffer before first detection
  window_packets: 200      # ~10 s window for vitals at 20 Hz
  refresh_every: 40
  motion_threshold_scale: 0.85   # slightly more sensitive outdoors
  link_timeout_sec: 5.0
```

Accurate positions are critical — each RX node localizes survivors **from its own corner**, then results are fused across nodes.

---

## 4. Install ESP-IDF (one-time)

```bash
git clone -b v5.1.4 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf && ./install.sh esp32,esp32c6
. ./export.sh
```

Verify: `idf.py --version`

---

## 5. Flash firmware

### TX node (1 board)

```bash
cd firmware/aura_tx
idf.py set-target esp32c6    # or esp32
idf.py build flash -p /dev/ttyUSB0 monitor
```

Expected log: `AURA probe transmitter running — pair with RX nodes on ch 6`

Press `Ctrl+]` to exit monitor. Power from USB bank in the field.

### RX nodes (one unique ID per board)

Flash **one board at a time** — unplug the previous board, plug in the next, same USB port.

**Important:** exit the AURA Python venv before ESP-IDF (`deactivate`). If your prompt shows `(venv)`, `idf.py` will fail with `Cannot import module "esp_idf_monitor"`.

**Easiest — use the flash helper** (sets node ID correctly every time):

```bash
cd ~/aura
git pull
deactivate
. ~/esp/esp-idf/export.sh
chmod +x tools/flash_rx.sh

./tools/flash_rx.sh 1    # RX board 1
./tools/flash_rx.sh 2    # swap board, flash RX 2
./tools/flash_rx.sh 3
./tools/flash_rx.sh 4
```

Manual flash (one board at a time):

```bash
cd ~/aura
git pull

deactivate
. ~/esp/esp-idf/export.sh
cd ~/aura/firmware/aura_rx
idf.py fullclean
idf.py set-target esp32

AURA_NODE_ID=1 idf.py -D AURA_RX_NODE_ID=1 -b 57600 build flash -p /dev/ttyUSB0
AURA_NODE_ID=2 idf.py -D AURA_RX_NODE_ID=2 -b 57600 build flash -p /dev/ttyUSB0
AURA_NODE_ID=3 idf.py -D AURA_RX_NODE_ID=3 -b 57600 build flash -p /dev/ttyUSB0
AURA_NODE_ID=4 idf.py -D AURA_RX_NODE_ID=4 -b 57600 build flash -p /dev/ttyUSB0
```

Set the node ID with the **`AURA_NODE_ID=N`** environment variable (not `-D CONFIG_AURA_NODE_ID=N`).

After flash, verify in monitor: `UDP hub → ... (node 2, DHCP gateway)`. If it still says `node 1`, run `idf.py fullclean` then re-flash that board.

Label each board with its node ID (1–4).

### Protocol note

Firmware sends **one UDP datagram per CSI frame**: 18-byte header + I/Q payload.  
Defined in `firmware/common/aura_protocol.h`, parsed by `simulation/aura_processor/wireless.py`.

If your laptop hotspot IP is not `192.168.4.1`, edit before flashing:

```c
// firmware/common/aura_protocol.h
#define AURA_HUB_IP "192.168.137.1"   // your hotspot gateway IP
```

---

## 6. Laptop hotspot setup

| Setting | Value |
|---------|-------|
| SSID | `AURA_HUB` |
| Password | `aura2026` |
| Gateway IP | `192.168.4.1` (typical; verify with `ip addr` / `ifconfig`) |
| UDP port | `5555` (allow in firewall) |

**Windows:** Settings → Mobile hotspot → configure SSID/password  
**macOS:** System Settings → Sharing → Internet Sharing (or create hotspot)  
**Linux:** `nmcli` or `create_ap` — ensure gateway is reachable by ESP32 nodes

---

## 7. Live field deployment

### Power-on sequence

1. Start laptop hotspot **`AURA_HUB`**
2. Start dashboard or wireless hub on laptop
3. Power **TX** node first
4. Power all **RX** nodes — they connect to hotspot and begin UDP streaming (~20 Hz)
5. Wait ~4–10 s per node for buffer fill, then sensing appears

### Option A — Web dashboard (recommended)

```bash
pip install -r simulation/requirements.txt
pip install -r dashboard/requirements.txt
python dashboard/run.py --port 8848
```

1. Open **http://127.0.0.1:8848**
2. Click **Live Hardware** tab
3. Click **Start Listening**
4. Power on nodes

Dashboard shows per node:
- Link status (`good` / `weak` / `offline`)
- RSSI and packet rate (Hz)
- Motion, count, respiration BPM, heartbeat BPM
- Fused survivor map across all nodes

### Option B — CLI wireless hub

```bash
python tools/wireless_hub.py
```

Opens a matplotlib window with live map, count, vitals, and node status.

---

## 8. Optional: UART backup recording

If WiFi link is unreliable, enable UART in firmware (`CONFIG_AURA_USE_UART=1`) and record:

```bash
pip install pyserial
python tools/record_session.py --port /dev/ttyUSB0 --duration 60 --out field_session.bin
```

Replay later via simulation tools or `simulation/aura_processor/loader.py` binary loader.

---

## 9. Post-mission simulation replay

If you filmed the scene during the exercise, replay through the simulation dashboard with matching CSI files for after-action review. See [SIMULATION_GUIDE.md](SIMULATION_GUIDE.md).

---

## 10. Troubleshooting

| Problem | Fix |
|---------|-----|
| `Cannot import esp_idf_monitor` | Run `deactivate` first (exit AURA `venv`), then `. ~/esp/esp-idf/export.sh` in a **new** terminal |
| Dashboard shows 1 node, 4 on WiFi | Re-flash each RX with unique `AURA_NODE_ID=1..4`; run `python3 tools/udp_probe.py` |
| Nodes not in dashboard | Check hotspot SSID/password; firewall UDP **5555**; `git pull` for DHCP gateway UDP fix |
| `buffering (N/80)` stuck | TX not powered; wrong channel; antenna disconnected |
| `link: weak` / low packet rate | Move node closer to laptop; external antenna; reduce WiFi interference |
| Count always 0 outdoors | Lower `motion_threshold` in config; survivor within 3–8 m of a link; wait full 10 s window |
| Wrong positions on map | Re-measure and update `node_positions` in `config.yaml`; restart hardware session |
| Vitals noisy | Need ~10 s of still subject; `window_packets: 200` helps at 20 Hz |
| After firmware update, no data | Re-flash all RX nodes; confirm single-datagram UDP (header+payload together) |
| Phase jumps at boot | Normal — discard first few seconds after power-on |

---

## 11. Safety & ethics

- AURA is **not certified** for life detection — use alongside acoustic, canine, and thermal SAR methods.
- Obtain authorization before transmitting WiFi in disaster zones.
- Label nodes clearly; coordinate with incident command before deploying RF equipment.

---

## 12. Related docs

- [WIRELESS_AND_SIMULATION.md](WIRELESS_AND_SIMULATION.md) — combined reference
- [BENCHMARKS.md](BENCHMARKS.md) — expected range and accuracy
- [firmware/README.md](../firmware/README.md) — build details
