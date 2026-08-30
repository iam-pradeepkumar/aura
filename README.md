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

### Simulation

```bash
cd simulation
pip install -r requirements.txt

# Validate your real CSI recording
python ../tools/validate_csi.py session.csv

# Live matplotlib viewer synced to your 3-second video
python run_simulation.py --video rescue.mp4 --csi session.csv
```

**Important:** AURA processes **real CSI only**. Record data with `tools/record_session.py` from ESP32 hardware. The system does not ship pre-recorded or synthetic survivor data.

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
