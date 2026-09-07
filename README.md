# AURA — Adaptive Urban Rescue & Alert Array

**Early warning + offline survivor detection for South Asian communities using ESP32 WiFi CSI.**

AURA (**Adaptive Urban Rescue & Alert Array**) solves two problems that cost lives in every major disaster:

1. **Before disaster** — communities lack hyper-local early warning (earthquakes, floods, storms).
2. **After disaster** — rescuers do not know **where** survivors are, **how many** are trapped, or whether they are still alive — and existing tools (dogs, thermal cameras, microphones) fail in rubble, mud, and rain.

AURA combines a **disaster alert engine** (USGS + Open-Meteo → DM approval → broadcast) with **WiFi Channel State Information (CSI) sensing** (ESP32 nodes → count, position, vitals) — all runnable without cloud dependency for rescue.

---

## What AURA does

| Capability | Phase | How |
|------------|-------|-----|
| Earthquake & weather monitoring | Early warning | USGS + Open-Meteo polled at your watch coordinates |
| DM-approved public alerts | Early warning | LAN multicast + webhook + `/alerts` feed |
| Safe-house routing | Early warning | Editable shelter list with coordinates |
| Survivor count & motion | Rescue | CSI amplitude dynamics from 4 RX nodes |
| XY localization | Rescue | Multinode fusion on a 10×10 m map |
| Respiration & heartbeat | Rescue | Phase/amplitude vitals extraction |
| Offline operation | Rescue | Laptop hotspot `AURA_HUB` — no internet needed |

**Processor version:** `2026.09.04-42` · **Sensing accuracy:** >90% (validated on WiMANS + field calibration)

---

## System architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1 — EARLY WARNING (internet optional for hazard APIs)    │
├─────────────────────────────────────────────────────────────────┤
│  USGS earthquakes + Open-Meteo weather                          │
│       ↓                                                         │
│  Hazard engine (thresholds in disaster_alert/config.yaml)       │
│       ↓                                                         │
│  DM Console queue → human approves & edits message              │
│       ↓                                                         │
│  Broadcast: LAN multicast + webhook + public /alerts page       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2 — RESCUE SENSING (no internet)                         │
├─────────────────────────────────────────────────────────────────┤
│  [TX ESP32] ── WiFi probes (ch 6) ──► air ◄── human body       │
│       │                              reflections                │
│  [RX×4] capture CSI ── UDP :5555 ──► Laptop (AURA_HUB hotspot) │
│       ↓                                                         │
│  aura_processor: count · position · vitals · motion             │
│       ↓                                                         │
│  tools/field_live.py  OR  /simulation (WiMANS replay)          │
└─────────────────────────────────────────────────────────────────┘
```

### Hardware layout (6 ESP32 boards)

| Board | Firmware | Role |
|-------|----------|------|
| 1× | `aura_alert_node` | Optional LAN hazard broadcast (laptop is primary poller) |
| 1× | `aura_tx` | WiFi probe transmitter |
| 4× | `aura_rx` | CSI receivers (unique `NODE_ID` each) |
| 1× | Laptop | Dashboard, alert engine, CSI fusion |

---

## Quick start

### 1. Install

```bash
git clone https://github.com/iam-pradeepkumar/aura.git
cd aura
pip install -r simulation/requirements.txt
pip install -r dashboard/requirements.txt
```

Requires **Python 3.10+**.

### 2. Start the dashboard

```bash
python3 dashboard/run.py
# Default: http://127.0.0.1:8847
```

| Page | URL | Purpose |
|------|-----|---------|
| **Home** | `/` | Problem, solution, how concepts work |
| **Simulation** | `/simulation` | Try bundled `act_105_48` or upload WiMANS dataset |
| **Alerts** | `/alerts` | Public feed + watch location editor |
| **DM Console** | `/manage` | Simulate/approve hazards, safe zones, webhook |

### 3. Try simulation (no hardware)

1. Open **http://127.0.0.1:8847/simulation**
2. Click **Try simulation (act_105_48)** — bundled video + `.mat` + `.npy`
3. Watch count, position map, respiration, and heartbeat sync to video

### 4. Try the alert flow (no hardware)

1. Open **http://127.0.0.1:8847/manage**
2. Set your **watch location** (name, latitude, longitude) and save
3. Click **Simulate hazard alert** → review in pending queue
4. Edit message + safe zones → **Broadcast to area**
5. View approved alert on **http://127.0.0.1:8847/alerts**

> **Offline / no internet?** Uncheck **Live API polling** on Alerts. Use DM Console simulate instead of USGS/Open-Meteo.

---

## How early warning works

1. **Watch zone** — You set coordinates on Alerts or DM Console (default: Vellore `12.334258, 79.783187`). Settings persist in `disaster_alert/data/alert_settings.json`.

2. **Polling** — Every 120 s (configurable), the engine fetches:
   - [USGS](https://earthquake.usgs.gov/) earthquake feed — magnitude & distance thresholds
   - [Open-Meteo](https://open-meteo.com/) — wind, gusts, precipitation thresholds

3. **DM queue** — Raw hazards never go public automatically. They appear in DM Console **Pending review**.

4. **Approval** — Disaster manager edits title, message, and safe-house list, then broadcasts.

5. **Delivery** — Approved alerts go to:
   - Public `/alerts` page
   - LAN HTTP server (port 8765) + UDP multicast (port 5558)
   - Optional webhook (Slack, custom HTTP)

Configure thresholds in `disaster_alert/config.yaml`. Safe zones in DM Console.

---

## How rescue sensing works

1. **WiFi CSI** — ESP32 receivers measure how WiFi signals change when a human body reflects, absorbs, or moves in the channel.

2. **Probe TX** — One transmitter sends periodic WiFi frames on channel 6.

3. **Four RX nodes** — Placed around a search perimeter; positions in `simulation/config.yaml`.

4. **Laptop hotspot** — SSID `AURA_HUB`, password `aura2026`, IP `192.168.4.1`. Nodes stream CSI via UDP port **5555**.

5. **Signal processing** (`simulation/aura_processor/`):
   - SRCC phase correction
   - Motion & Doppler detection
   - Multitarget count and XY fusion
   - Respiration / heartbeat waveforms

6. **Live viewer** — `python3 tools/field_live.py` (matplotlib). **Calibrate 5 s with empty scene first.**

7. **Simulation replay** — Upload WiMANS triple (`.mp4` + `.mat` + `.npy`) or use bundled `act_105_48` in the web lab.

---

## Simulation (WiMANS / dataset replay)

**Bundled sample:** `dashboard/demo_data/act_105_48.{mp4,mat,npy}` — click **Try simulation** in the web UI.

**Custom upload:** three files with matching `act_*` stem:

| # | File | Purpose |
|---|------|---------|
| 1 | `.mp4` | Scene video (sync timeline) |
| 2 | `.mat` | Raw complex CSI |
| 3 | `.npy` | Preprocessed amplitude CSI |

```bash
# CLI viewer (optional)
cd simulation
python run_simulation.py --video act_105_48.mp4 --csi act_105_48.npy

# Validate CSI format
python tools/validate_csi.py act_105_48.npy
```

See [docs/SIMULATION_GUIDE.md](docs/SIMULATION_GUIDE.md) and [docs/WIMANS_TRAINING.md](docs/WIMANS_TRAINING.md).

---

## Live hardware deployment

### Components

| Item | Qty |
|------|-----|
| ESP32-C6 (or ESP32 / ESP32-C3) | 6 |
| External 2.4 GHz antenna (U.FL) | 5 |
| USB power banks (10,000 mAh+) | 5 |
| Laptop with Python 3.10+ | 1 |

### Field steps

1. Flash **aura_tx** (1), **aura_rx** (4, unique `NODE_ID`), optionally **aura_alert_node** (1)
2. Edit `simulation/config.yaml` — node XY positions
3. Start laptop hotspot: **SSID `AURA_HUB`**, password **`aura2026`**
4. Power TX, then RX nodes
5. Run `python3 tools/field_live.py` — **close dashboard first** (same UDP port 5555)

See [docs/HARDWARE_SETUP.md](docs/HARDWARE_SETUP.md) and [docs/HARDWARE_FIELD_DEPLOYMENT.md](docs/HARDWARE_FIELD_DEPLOYMENT.md).

---

## Project structure

```
AURA/
├── dashboard/              # Web UI (hand-drawn design)
│   ├── app.py              # FastAPI — simulation + alerts API
│   ├── demo_data/          # Bundled act_105_48 WiMANS sample
│   └── static/             # Landing, simulation, alerts, DM console
├── disaster_alert/         # Early-warning engine
│   ├── config.yaml         # Coordinates, thresholds, safe zones
│   ├── engine.py           # USGS + Open-Meteo poller
│   └── router.py           # /api/alerts/*
├── firmware/
│   ├── aura_tx/            # WiFi probe transmitter
│   ├── aura_rx/            # CSI receiver → UDP
│   └── aura_alert_node/    # Optional single alert ESP32
├── simulation/
│   ├── aura_processor/     # CSI DSP pipeline (shared)
│   └── wimans/             # WiMANS annotations + model
└── tools/
    ├── field_live.py       # Live ESP32 matplotlib UI
    └── train_wimans.py     # Train count/localization model
```

---

## Documentation

| Document | Contents |
|----------|----------|
| [docs/README.md](docs/README.md) | Documentation index |
| [docs/SIMULATION_GUIDE.md](docs/SIMULATION_GUIDE.md) | Web + CLI simulation |
| [docs/HARDWARE_SETUP.md](docs/HARDWARE_SETUP.md) | Flashing & field layout |
| [docs/HARDWARE_FIELD_DEPLOYMENT.md](docs/HARDWARE_FIELD_DEPLOYMENT.md) | Outdoor deployment guide |
| [docs/WIRELESS_AND_SIMULATION.md](docs/WIRELESS_AND_SIMULATION.md) | Wireless + simulation reference |
| [docs/WIMANS_TRAINING.md](docs/WIMANS_TRAINING.md) | Training on WiMANS data |
| [docs/BENCHMARKS.md](docs/BENCHMARKS.md) | Accuracy & latency |

---

## References

- [Towards SISO Bistatic Sensing for ISAC (arXiv:2508.12614)](https://arxiv.org/pdf/2508.12614)
- [WiMANS dataset](https://www.kaggle.com/datasets/shuokhuang/wimans)
- [Espressif esp-csi](https://github.com/espressif/esp-csi)

---

## License

MIT — Use responsibly in real rescue operations only with trained personnel and validated hardware. AURA is a **research/demonstration** platform, not a certified life-detection device.
