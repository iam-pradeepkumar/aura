# AURA — Adaptive Urban Rescue Array

**Offline disaster survivor detection using ESP32 WiFi CSI — no internet, no router, no cloud.**

AURA places low-cost ESP32 nodes around a collapsed structure. One node transmits WiFi probe frames; receiver nodes capture **Channel State Information (CSI)** from human body reflections. Signal processing (adapted from [WiDFS 3.0 / SISO bistatic ISAC research](https://arxiv.org/pdf/2508.12614)) extracts:

| Function | Description |
|----------|-------------|
| **Motion detection** | Human presence via CSI amplitude/phase dynamics |
| **Moving target localization** | XY position, velocity, acceleration |
| **Tracking** | Trajectory history; entry/exit events |
| **Static target localization** | XY of stationary survivors (low Doppler) |
| **Vital signs** | Respiration & heartbeat waveforms + BPM |

---

## Quick Start

### Hardware (see [docs/HARDWARE_SETUP.md](docs/HARDWARE_SETUP.md))

1. Flash **1× TX** + **4× RX** ESP32 nodes (ESP32-C6 recommended)
2. Place nodes around the search area — no WiFi router needed
3. Record 3 s CSI while filming the scene
4. Run the simulation viewer

### Simulation (with your .mp4 + .npy / .mat files)

```bash
cd simulation
pip install -r requirements.txt

# Validate CSI
python ../tools/validate_csi.py ../my_data/rescue.npy

# Run video-synced viewer
python run_simulation.py --video ../my_data/rescue.mp4 --csi ../my_data/rescue.npy

# Or auto-detect from folder
python run_simulation.py --data-dir ../my_data
```

### Wireless live results (all nodes, no USB cables)

```bash
# 1. Start laptop hotspot: SSID=AURA_HUB, password=aura2026
# 2. Power on all ESP32 RX nodes
python tools/wireless_hub.py
```

See **[docs/WIRELESS_AND_SIMULATION.md](docs/WIRELESS_AND_SIMULATION.md)** for full setup.

---

## Project Structure

```
AURA/
├── firmware/
│   ├── aura_tx/          # Offline CSI probe transmitter
│   ├── aura_rx/          # CSI receiver + UART stream
│   └── common/           # Shared protocol headers
├── simulation/
│   ├── aura_processor/   # SRCC, Doppler, vitals, tracking
│   ├── run_simulation.py # Video-synced matplotlib viewer
│   └── config.yaml       # Node positions (meters)
├── tools/
│   ├── record_session.py # UART → .bin + .csv
│   └── validate_csi.py   # Format checker
└── docs/
    ├── HARDWARE_SETUP.md
    ├── SIMULATION_GUIDE.md
    └── BENCHMARKS.md
```

---

## How It Works (No Network)

```
  [TX ESP32]  ----WiFi probes (ch 6)---->  air  <---- human body reflections
                                                |
                    +---------------------------+---------------------------+
                    |                           |                           |
               [RX Node 1]                  [RX Node 2]                  [RX Node N]
               promiscuous CSI             promiscuous CSI              promiscuous CSI
                    |                           |                           |
                    +-------- USB-UART --------> Laptop (record + process)
```

- **No router, no internet, no AP association** — RX nodes use promiscuous mode + CSI on a fixed channel
- TX sends periodic 802.11 frames on channel 6
- Human motion/vitals modulate multipath → detectable in CSI phase/amplitude
- **SRCC** (Self-Referencing Cross-Correlation) removes clock-asynchrony phase noise (SISO bistatic, per WiDFS 3.0)
- Multi-node range estimates → multilateration for XY survivor positions

---

## References

- [Towards SISO Bistatic Sensing for ISAC (arXiv:2508.12614)](https://arxiv.org/pdf/2508.12614)
- [csiread](https://github.com/Zhongqin-Wang/csiread) — Intel 5300 CSI tools (reference)
- [Towards-SISO-Bistatic-Sensing-for-ISAC](https://github.com/Zhongqin-Wang/Towards-SISO-Bistatic-Sensing-for-ISAC)
- [Espressif esp-csi](https://github.com/espressif/esp-csi) — ESP32 CSI examples

---

## License

MIT — Use responsibly in real rescue operations only with trained personnel and validated hardware.
