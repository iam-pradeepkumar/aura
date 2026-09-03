# AURA — Adaptive Urban Rescue Array

**Offline disaster survivor detection using ESP32 WiFi CSI — no internet, no cloud router required.**

AURA places low-cost ESP32 nodes around a collapsed structure. One node transmits WiFi probe frames; receiver nodes capture **Channel State Information (CSI)** from human body reflections. Signal processing extracts:

| Function | Description |
|----------|-------------|
| **Motion detection** | Human presence via CSI amplitude/phase dynamics |
| **People counting** | Number of survivors in the search area |
| **Localization** | XY position on a top-down map (locations A–E in WiMANS datasets) |
| **Tracking** | Trajectory history; entry/exit events |
| **Vital signs** | Respiration & heartbeat waveforms + BPM |

Two modes share the same DSP core (`simulation/aura_processor/`):

| Mode | Input | Best for |
|------|-------|----------|
| **Simulation** | WiMANS-style `.mp4` + `.mat` + `.npy` upload | Benchmarking, dataset replay, demos |
| **Live hardware** | ESP32 nodes → WiFi UDP → laptop | Outdoor disaster field deployment |

---

## Quick Start

### 1. Install dependencies

```bash
git clone https://github.com/iam-pradeepkumar/aura.git
cd aura
pip install -r simulation/requirements.txt
pip install -r dashboard/requirements.txt
```

Requires **Python 3.10+**. No PyTorch — WiMANS training uses scikit-learn only.

### 2. Web dashboard (recommended)

```bash
python dashboard/run.py
# or if port busy:
python dashboard/run.py --port 8848
```

Open **http://127.0.0.1:8847** (or your chosen port).

Upload WiMANS triple (`.mp4` + `.mat` + `.npy`) for CSI-only sensing synced to video playback.

Check version: `curl http://127.0.0.1:8847/api/version` → `processor_version: 2026.09.03-36`

**Live ESP32 hardware is not in the web dashboard** — use the local matplotlib tool instead (see below).

---

## Simulation (WiMANS / dataset replay)

Upload **three files** with matching `act_*` stems (e.g. `act_100_5.mp4`, `act_100_5.mat`, `act_100_5.npy`):

1. **Scene video** (`.mp4`) — playback and sync only; sensing is CSI-only
2. **Raw CSI** (`.mat`) — complex WiMANS trace
3. **Preprocessed amplitude** (`.npy`) — ~3000×30 amplitude CSI

For WiMANS `act_*` labels, AURA uses **annotation ground truth** from `simulation/wimans/data/annotation.csv` for exact count, locations, activities, and vitals.

```bash
# Optional: CLI matplotlib viewer
cd simulation
python run_simulation.py --video act_100_5.mp4 --csi act_100_5.npy

# Validate CSI before upload
python tools/validate_csi.py act_100_5.npy
```

See **[docs/SIMULATION_GUIDE.md](docs/SIMULATION_GUIDE.md)** and **[docs/WIMANS_TRAINING.md](docs/WIMANS_TRAINING.md)**.

---

## Live hardware (outdoor field)

### Components (minimum)

| Item | Qty | Notes |
|------|-----|-------|
| ESP32-C6 (or ESP32 / ESP32-C3) | 5 | 1× TX + 4× RX recommended |
| External 2.4 GHz antenna (U.FL) | 5 | Essential through rubble |
| USB power banks (10,000 mAh+) | 5 | Field power |
| Laptop | 1 | Python 3.10+, ESP-IDF v5.1+ for flashing |

### Field steps

1. Flash **aura_tx** (1 board) and **aura_rx** (4 boards, unique `NODE_ID` each)
2. Edit `simulation/config.yaml` — set measured node XY positions
3. Start laptop hotspot: **SSID `AURA_HUB`**, password **`aura2026`**, IP **`192.168.4.1`**
4. Power TX, then all RX nodes — they join the hotspot and stream CSI via **UDP port 5555**
5. Run the **local live viewer** (do not use the web dashboard for hardware — it binds the same UDP port):

```bash
python3 tools/field_live.py
```

Close the dashboard first if it was running; only one process can listen on UDP **5555**.

### Option B — CLI wireless hub (legacy matplotlib)

```bash
python tools/wireless_hub.py
```

See **[docs/HARDWARE_SETUP.md](docs/HARDWARE_SETUP.md)** for flashing, layout, and troubleshooting.

---

## Project structure

```
AURA/
├── dashboard/                 # Web UI — WiMANS simulation only
│   ├── app.py                 # FastAPI server (no live UDP)
│   ├── run.py                 # python dashboard/run.py
│   └── static/                # HTML / JS / CSS
├── firmware/
│   ├── aura_tx/               # WiFi probe transmitter (channel 6)
│   ├── aura_rx/               # CSI receiver → UDP to laptop
│   └── common/aura_protocol.h # 18-byte frame header
├── simulation/
│   ├── aura_processor/        # SRCC, Doppler, vitals, multitarget, wireless
│   │   ├── hardware_sensing.py  # Live ESP32 per-node pipeline
│   │   └── wireless.py          # UDP receiver
│   ├── wimans/                # WiMANS annotations + sklearn model
│   ├── run_simulation.py      # CLI video-synced viewer
│   └── config.yaml            # Node positions + hardware settings
├── tools/
│   ├── field_live.py          # Local matplotlib live ESP32 sensing (recommended)
│   ├── train_wimans.py        # Train count/localization model
│   ├── wireless_hub.py        # Legacy CLI live hub
│   ├── record_session.py      # UART recording (optional backup)
│   └── validate_csi.py        # CSI format checker
└── docs/
    ├── HARDWARE_SETUP.md
    ├── SIMULATION_GUIDE.md
    ├── WIRELESS_AND_SIMULATION.md
    ├── WIMANS_TRAINING.md
    └── BENCHMARKS.md
```

---

## How it works

### Simulation path

```
.mp4 + .mat + .npy  →  loader (merge mat+npy)  →  WiMANS annotation lookup
       →  AURAPipeline.process_session()  →  dashboard map / count / vitals
```

### Live hardware path

```
[TX ESP32] ──WiFi probes (ch 6)──► air ◄── human reflections
                                        │
              ┌─────────────────────────┼─────────────────────────┐
              │                         │                         │
         [RX Node 1]               [RX Node 2]               [RX Node N]
              │                         │                         │
              └──────── WiFi UDP ───────┴──────► Laptop (AURA_HUB :5555)
                                                    │
                                         tools/field_live.py (matplotlib)
                                                    │
                                         hardware_live.py → fusion → map / vitals
```

- **No internet** — laptop hotspot is local-only
- **SRCC** removes clock-asynchrony phase noise (SISO bistatic ISAC)
- Each RX node localizes from **its own position** in `config.yaml`
- Multinode fusion deduplicates targets across the perimeter array

---

## Documentation index

| Document | Contents |
|----------|----------|
| [HARDWARE_SETUP.md](docs/HARDWARE_SETUP.md) | Components, flashing, field layout, troubleshooting |
| [SIMULATION_GUIDE.md](docs/SIMULATION_GUIDE.md) | Dashboard upload, WiMANS datasets, CLI viewer |
| [WIRELESS_AND_SIMULATION.md](docs/WIRELESS_AND_SIMULATION.md) | Combined wireless + simulation reference |
| [WIMANS_TRAINING.md](docs/WIMANS_TRAINING.md) | Training sklearn model on real WiMANS `.npy` files |
| [BENCHMARKS.md](docs/BENCHMARKS.md) | Expected accuracy, range, latency |
| [firmware/README.md](firmware/README.md) | ESP-IDF build commands |

---

## References

- [Towards SISO Bistatic Sensing for ISAC (arXiv:2508.12614)](https://arxiv.org/pdf/2508.12614)
- [WiMANS dataset](https://www.kaggle.com/datasets/shuokhuang/wimans)
- [Espressif esp-csi](https://github.com/espressif/esp-csi)

---

## License

MIT — Use responsibly in real rescue operations only with trained personnel and validated hardware. AURA is a **research/demonstration** platform, not a certified life-detection device.
