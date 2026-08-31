# AURA — Wireless Live + Simulation Reference

Complete reference for **live hardware streaming** and **dataset simulation** in one place.

---

## Part 1: Live hardware (outdoor field)

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Laptop hotspot (AURA_HUB)  ←──WiFi──→  RX Node 1 (UDP)     │
│         ↑                                  RX Node 2         │
│  dashboard / wireless_hub.py               RX Node 3         │
│  UDP :5555                                 RX Node 4         │
└──────────────────────────────────────────────────────────────┘
         TX probe (battery, channel 6, ~20 Hz)
```

### One-time setup

| Step | Action |
|------|--------|
| 1 | Flash `firmware/aura_tx` on 1 board |
| 2 | Flash `firmware/aura_rx` on 3–4 boards with `CONFIG_AURA_NODE_ID=1..4` |
| 3 | Set `node_positions` in `simulation/config.yaml` |
| 4 | Configure laptop hotspot: SSID **`AURA_HUB`**, password **`aura2026`** |
| 5 | Allow **UDP port 5555** in firewall |

If hotspot gateway is not `192.168.4.1`, edit `AURA_HUB_IP` in `firmware/common/aura_protocol.h` and re-flash RX nodes.

### Field operation

```bash
# Terminal 1 — dashboard
pip install -r simulation/requirements.txt dashboard/requirements.txt
python dashboard/run.py --port 8848
```

1. **Live Hardware** tab → **Start Listening**
2. Power TX, then all RX nodes
3. Wait ~4–10 s per node (buffer fill)
4. Observe fused count, map, vitals

**CLI alternative:**

```bash
python tools/wireless_hub.py
```

### What live hardware shows

| Output | Description |
|--------|-------------|
| **People count** | Fused across all active RX nodes |
| **Survivor map** | XY positions (each node uses its corner position) |
| **Motion** | CSI amplitude/phase dynamics |
| **Vitals** | Respiration + heartbeat BPM and waveforms |
| **Per-node status** | RSSI, packet rate Hz, link quality (`good`/`weak`/`offline`) |
| **Confidence** | Session-level detection confidence |

### Hardware config (`simulation/config.yaml`)

```yaml
hardware:
  min_packets: 80          # packets before first detection (~4 s @ 20 Hz)
  window_packets: 200      # analysis window (~10 s for vitals)
  refresh_every: 40        # recompute session targets
  motion_threshold_scale: 0.85
  link_timeout_sec: 5.0
```

### UDP protocol (18-byte header)

Matches `firmware/common/aura_protocol.h`:

| Field | Type | Size |
|-------|------|------|
| magic | `0x41555241` ("AURA") | 4 |
| version | uint8 | 1 |
| node_id | uint8 | 1 |
| link_id | uint8 | 1 |
| reserved | uint8 | 1 |
| timestamp_ms | uint32 | 4 |
| rssi | int8 | 1 |
| channel | uint8 | 1 |
| subcarrier_count | uint16 | 2 |
| payload_bytes | uint16 | 2 |
| **payload** | int8 I/Q interleaved | variable |

Firmware sends **header + payload in one UDP datagram**.  
Python receiver: `simulation/aura_processor/wireless.py`  
Live DSP: `simulation/aura_processor/hardware_sensing.py`

### Hardware troubleshooting

| Issue | Fix |
|-------|-----|
| No nodes appear | Hotspot SSID/password; UDP 5555 firewall; check `AURA_HUB_IP` |
| Buffering forever | TX off or wrong channel; antenna issue |
| Weak link | External antenna; reduce distance to laptop hotspot |
| Ghost targets | Multipath outdoors — use 4-node fusion; raise `motion_threshold` |
| Low vitals accuracy | Need ~10 s still subject; increase `window_packets` |

---

## Part 2: Simulation (dataset replay)

### Architecture

```
act_100_5.mp4 + act_100_5.mat + act_100_5.npy
        │
        ▼
  loader.merge_csi_mat_npy()
        │
        ▼
  WiMANS annotation lookup (act_* stem)
        │
        ▼
  AURAPipeline.process_session()  →  dashboard / CLI viewer
```

### Required upload (dashboard)

| # | File | Example |
|---|------|---------|
| 1 | Scene video `.mp4` | `act_100_5.mp4` |
| 2 | Raw CSI `.mat` | `act_100_5.mat` |
| 3 | Preprocessed `.npy` | `act_100_5.npy` |

Filenames must share the same **`act_*`** stem for WiMANS ground-truth sensing.

### Run simulation

**Dashboard:** Simulation tab → upload 3 files → **Run Simulation**

**CLI:**

```bash
cd simulation
python run_simulation.py --video ../act_100_5.mp4 --csi ../act_100_5.npy
python run_simulation.py --data-dir ../my_wimans_folder/
python ../tools/validate_csi.py ../act_100_5.npy
```

### Supported CSI formats (CLI single-file)

| Format | Shapes / fields |
|--------|-----------------|
| `.npy` | `(T, 30)` amplitude; `(T, 30)` complex; `(T, tones, nrx, ntx)` |
| `.mat` | WiMANS `trace`, `csi`, `CSI`, HDF5 via mat73 |
| `.npz` | `csi` + optional `timestamp_ms` |
| `.bin` / `.csv` | AURA ESP32 recorder |

### WiMANS sensing modes

| Mode | When | Accuracy |
|------|------|----------|
| `wimans_source: "annotation"` | `act_*` filename in annotation.csv | Exact count, locations, activities |
| `wimans_source: "sklearn"` | Unlabeled `.npy` with trained model | Model-dependent — retrain recommended |

Train on real WiMANS amplitude files:

```bash
python tools/train_wimans.py --amp-dir ~/WiMANS/dataset/wifi_csi/amp
```

See [WIMANS_TRAINING.md](WIMANS_TRAINING.md).

### Simulation troubleshooting

| Issue | Fix |
|-------|-----|
| Wrong count | Match `act_*` filenames; pull latest code |
| `.mat` ZIP error | Extract WiMANS archive first |
| No phase in `.mat` | `.npy` fusion adds Hilbert synthetic phase automatically |
| `trim_csi_to_video` errors | Update to latest `dashboard/app.py` |
| Stale dashboard | Hard refresh; check `/api/version` |

---

## Part 3: Simulation vs hardware comparison

| Feature | Simulation | Live hardware |
|---------|------------|---------------|
| **Input** | `.mp4` + `.mat` + `.npy` | ESP32 UDP CSI stream |
| **Sample rate** | ~1000 Hz (WiMANS) | ~20 Hz (ESP32) |
| **Count source** | WiMANS annotation or sklearn | CSI heuristics + multinode fusion |
| **Localization** | WiMANS layout a–e or CSI AoA | Per-node sensor XY from config |
| **Vitals** | Activity priors + CSI waveforms | ~10 s window at 20 Hz |
| **Video** | Synced playback | Not used live |
| **Best for** | Benchmarks, demos, training | Outdoor disaster deployment |

Both paths use the same core: **SRCC → motion detection → multitarget localization → vitals extraction**.

---

## Part 4: Tools reference

| Tool | Command | Purpose |
|------|---------|---------|
| Dashboard | `python dashboard/run.py` | Web UI — simulation + hardware |
| Wireless hub | `python tools/wireless_hub.py` | CLI live hardware viewer |
| Validate CSI | `python tools/validate_csi.py file.npy` | Check format before upload |
| Train WiMANS | `python tools/train_wimans.py` | Build sklearn sensing model |
| Record UART | `python tools/record_session.py --port /dev/ttyUSB0` | Backup CSI recording |
| CLI simulation | `python simulation/run_simulation.py` | Matplotlib video viewer |

---

## Related docs

- [HARDWARE_SETUP.md](HARDWARE_SETUP.md) — components, flashing, field procedure
- [SIMULATION_GUIDE.md](SIMULATION_GUIDE.md) — step-by-step simulation
- [BENCHMARKS.md](BENCHMARKS.md) — expected performance numbers
