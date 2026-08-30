# AURA Hardware Setup Guide (Beginner)

This guide walks you through building and deploying AURA ESP32 nodes for **offline** disaster survivor detection using WiFi CSI only.

---

## 1. Components List

| Item | Qty | Notes |
|------|-----|-------|
| **ESP32-C6** dev board (or ESP32 / ESP32-C3) | 5 minimum | C6 has best RF; use external antenna in rubble |
| **External 2.4 GHz WiFi antenna** (U.FL/IPX) | 5 | PCB antennas are weak through debris |
| **USB cables** (data-capable) | 5 | Power + UART for one recording node |
| **5V USB power banks** | 5 | 10,000 mAh+ for field deployment |
| **Tripods / magnetic mounts** | 5 | Mount nodes at 1–2 m height around perimeter |
| **Laptop** (Linux/macOS/Windows) | 1 | Python 3.10+, ESP-IDF v5.1+ |
| **Measuring tape** | 1 | Record node XY positions for `config.yaml` |
| **Phone/camera** | 1 | Optional 3 s scene video for simulation sync |

**Optional:** microSD on coordinator node for standalone logging (future firmware extension).

---

## 2. Node Roles

| Role | Firmware folder | Purpose |
|------|-----------------|---------|
| **TX (Transmitter)** | `firmware/aura_tx` | Sends WiFi probe frames on channel 6 — **no network** |
| **RX (Receiver)** | `firmware/aura_rx` | Captures CSI in promiscuous mode, streams via USB-UART |

**Minimum deployment:** 1 TX + 3 RX (triangle) for basic XY. **Recommended:** 1 TX + 4 RX (square perimeter) for multilateration and people counting.

---

## 3. Wiring & Connections

ESP32 dev boards need **no extra wiring** for CSI sensing:

```
ESP32-C6 DevKit
├── USB ──────────> Laptop (RX node #1 only, for recording)
├── Antenna ──────> External 2.4 GHz (screw onto U.FL connector)
└── Power bank ───> USB (all nodes in field)
```

**Physical layout (10 m × 10 m example):**

```
        Node 4 (0,10) ───────────── Node 3 (10,10)
              │                           │
              │    [Collapsed structure]    │
              │         (search area)       │
              │                           │
        Node 1 (0,0) ────────────── Node 2 (10,0)

        TX probe: place OUTSIDE perimeter, 2 m from Node 1
                   e.g. position (5, -2) in config.yaml
```

Measure and enter positions in `simulation/config.yaml`.

---

## 4. Install ESP-IDF (One-Time)

```bash
# Linux/macOS — follow Espressif official guide
git clone -b v5.1.4 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf && ./install.sh esp32,esp32c6
. ./export.sh
```

Verify: `idf.py --version`

---

## 5. Flash Firmware

### TX Node (1 board)

```bash
cd firmware/aura_tx
idf.py set-target esp32c6    # or esp32
idf.py build flash -p /dev/ttyUSB0 monitor
```

You should see: `AURA probe transmitter running — pair with RX nodes on ch 6`

Press `Ctrl+]` to exit monitor.

### RX Nodes (4 boards, set unique NODE_ID)

Edit `firmware/aura_rx/main/main.c` — change `CONFIG_AURA_NODE_ID` or add to `sdkconfig`:

```bash
cd firmware/aura_rx
idf.py set-target esp32c6
idf.py -D CONFIG_AURA_NODE_ID=1 build flash -p /dev/ttyUSB0   # Node 1
# Repeat for nodes 2, 3, 4 on different boards/ports
```

Label each board with its node ID.

---

## 6. Field Deployment Procedure

1. **Power on TX first**, then all RX nodes (fixed channel 6, no pairing needed).
2. Place nodes at measured positions; antennas vertical, line-of-sight to search area where possible.
3. Connect **one RX node** (or rotate USB) to laptop.
4. Record CSI while rescuers simulate survivor motion OR during live search:

```bash
pip install pyserial numpy pandas
python tools/record_session.py -p /dev/ttyUSB0 -d 3 -o session.bin
```

This creates `session.bin` and `session.csv` (3 seconds at ~20 Hz ≈ 60 frames).

5. **Film the same 3 seconds** with your phone from above (for simulation overlay).
6. Transfer `session.csv` + `rescue.mp4` to laptop.

---

## 7. Process Real Results

```bash
cd simulation
pip install -r requirements.txt
python ../tools/validate_csi.py ../session.csv
python run_simulation.py --video ../rescue.mp4 --csi ../session.csv --config config.yaml
```

The viewer shows:
- Video frame sync
- Survivor count (CSI peak count)
- XY map with moving (red) / static (orange) markers
- Respiration & heartbeat waveforms with BPM

---

## 8. Troubleshooting

| Problem | Fix |
|---------|-----|
| No CSI frames in recording | Ensure TX is powered; same channel 6; RX in promiscuous mode |
| `validate_csi.py` fails | Check baud 921600; close `idf.py monitor` before recording |
| Zero people detected | Lower `motion_threshold` in config.yaml; move TX closer; check antenna |
| Vital signs noisy | Increase window to 2+ s; survivor within 3–5 m of at least one link |
| Phase jumps | Normal at boot — discard first 2 s of recording |

---

## 9. Safety & Ethics

- AURA is a **research/demonstration** platform — not a certified life-detection device.
- Always use alongside acoustic, canine, and thermal search methods.
- Obtain authorization before transmitting WiFi in disaster zones (some jurisdictions restrict RF).

---

## 10. Next Steps

- Deploy all 4 RX nodes simultaneously with ESP-NOW aggregation (roadmap)
- Add SD-card logging for fully untethered nodes
- See [BENCHMARKS.md](BENCHMARKS.md) for expected range and accuracy
