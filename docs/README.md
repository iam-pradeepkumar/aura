# AURA Documentation

Complete documentation for the **Adaptive Urban Rescue Array** — ESP32 WiFi CSI disaster survivor detection.

---

## Start here

| I want to… | Read |
|------------|------|
| Get started quickly | [../README.md](../README.md) |
| Run WiMANS simulation in browser | [SIMULATION_GUIDE.md](SIMULATION_GUIDE.md) |
| Deploy ESP32 nodes in the field | [HARDWARE_SETUP.md](HARDWARE_SETUP.md) |
| Stream live CSI from all nodes | [WIRELESS_AND_SIMULATION.md](WIRELESS_AND_SIMULATION.md) → Part 1 |
| Train on WiMANS `.npy` files | [WIMANS_TRAINING.md](WIMANS_TRAINING.md) |
| Flash ESP32 firmware | [../firmware/README.md](../firmware/README.md) |
| Expected accuracy & range | [BENCHMARKS.md](BENCHMARKS.md) |

---

## Quick commands

```bash
# Install
pip install -r simulation/requirements.txt dashboard/requirements.txt

# Web dashboard (simulation + live hardware)
python dashboard/run.py

# Live hardware CLI
python tools/wireless_hub.py

# WiMANS simulation CLI
cd simulation && python run_simulation.py --data-dir ../my_data/

# Train WiMANS model
python tools/train_wimans.py --amp-dir ~/WiMANS/dataset/wifi_csi/amp
```

---

## Project modes

```
┌─────────────────────┐     ┌─────────────────────┐
│     SIMULATION      │     │   LIVE HARDWARE     │
│  .mp4 + .mat + .npy │     │  ESP32 → UDP :5555  │
│  WiMANS annotation  │     │  Per-node outdoor   │
│  Dashboard / CLI    │     │  Dashboard / CLI    │
└─────────────────────┘     └─────────────────────┘
           │                           │
           └───────────┬───────────────┘
                       ▼
              aura_processor/ (shared DSP)
```

---

## File map

| Path | Description |
|------|-------------|
| `dashboard/` | FastAPI web UI |
| `simulation/aura_processor/` | CSI DSP pipeline |
| `simulation/wimans/` | WiMANS annotations + model |
| `firmware/` | ESP32 TX/RX source |
| `tools/` | Training, validation, wireless hub |
| `simulation/config.yaml` | Node positions + hardware settings |
