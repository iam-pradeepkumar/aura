# AURA Simulation Guide

Run **CSI-only survivor sensing** synced to scene video using WiMANS-style datasets or your own `.mp4` + `.mat` + `.npy` triplets.

---

## Overview

| What | Details |
|------|---------|
| **Sensing input** | CSI only — video is for playback/sync, not person detection |
| **Required files** | `.mp4` (video) + `.mat` (raw CSI) + `.npy` (preprocessed amplitude) |
| **WiMANS datasets** | Filename stem `act_X_Y` → exact count/locations from `annotation.csv` |
| **Dashboard** | Recommended — upload all three files, click **Run Simulation** |
| **CLI** | `simulation/run_simulation.py` — matplotlib viewer |

---

## Prerequisites

```bash
cd aura
pip install -r simulation/requirements.txt
pip install -r dashboard/requirements.txt
```

- Python 3.10+
- WiMANS dataset from [Kaggle](https://www.kaggle.com/datasets/shuokhuang/wimans) (optional but recommended for benchmarks)

---

## Method 1: Web dashboard (recommended)

### Step 1 — Start dashboard

```bash
python dashboard/run.py
# default http://127.0.0.1:8847
```

### Step 2 — Prepare files

For WiMANS sample `act_100_5`:

| File | Example | Role |
|------|---------|------|
| Scene video | `act_100_5.mp4` | 3 s synced video — playback only |
| Raw CSI | `act_100_5.mat` | Complex WiMANS trace (3000×3×3×30) |
| Preprocessed amp | `act_100_5.npy` | Amplitude CSI (~3000×30) |

**Important:** All three filenames must share the same `act_*` stem so WiMANS annotations match.

Ground truth for `act_100_5`:
- **3 users** at locations **a, b, c** in `empty_room`
- Activities: **wave**, **lie_down**, **pick_up**

### Step 3 — Upload and run

1. Open **Simulation** tab
2. Upload **Scene video** (`.mp4`)
3. Upload **Raw CSI** (`.mat`)
4. Upload **Preprocessed amp** (`.npy`)
5. Leave sample rate blank (auto-detected, typically ~1000 Hz for WiMANS)
6. Click **Run Simulation**

### Step 4 — Read results

| Panel | Shows |
|-------|-------|
| **Scene video** | Synced playback scrubber |
| **Survivor map** | Target positions on 10 m grid |
| **Stats** | Count, motion, respiration BPM, heartbeat BPM |
| **Vitals chart** | Waveforms per person |
| **API metadata** | `wimans_source: "annotation"`, `wimans_count`, `processor_version` |

Verify version: `curl http://127.0.0.1:8847/api/version`

---

## Method 2: CLI matplotlib viewer

```bash
cd simulation

# Validate amplitude CSI
python ../tools/validate_csi.py ../path/to/act_100_5.npy

# Run viewer (video + single CSI file — legacy path)
python run_simulation.py --video ../act_100_5.mp4 --csi ../act_100_5.npy

# Auto-detect matching files in folder
python run_simulation.py --data-dir ../my_data/

# Intel / high sample rate
python run_simulation.py --video rescue.mp4 --csi csi.mat --fs 1000

# Save animation
python run_simulation.py --video rescue.mp4 --csi rescue.npy --save demo.mp4
```

> **Note:** The dashboard upload path merges `.mat` + `.npy` for best phase/amplitude fusion. The CLI `--csi` flag uses a single file; for WiMANS accuracy prefer the dashboard triple upload.

### CLI display panels

| Panel | Content |
|-------|---------|
| Top-left | Scene video (frame-synced) |
| Bottom-left | Top-down map — blue = ESP32 nodes, red = survivors |
| Top-right | People count + motion indicator |
| Middle-right | Respiration waveform + BPM |
| Bottom-right | Heartbeat waveform + BPM |

---

## Configure node layout

Edit `simulation/config.yaml` to match your environment:

```yaml
area_size_m: 10.0
motion_threshold: 0.02
max_people: 8

node_positions:
  1: [0.0, 0.0]
  2: [10.0, 0.0]
  3: [10.0, 10.0]
  4: [0.0, 10.0]
```

WiMANS locations **a–e** map to XY per environment (`empty_room`, `classroom`, `meeting_room`) in `simulation/wimans/layouts.py`.

---

## Supported CSI formats

### Dashboard simulation upload

| Slot | Format | Notes |
|------|--------|-------|
| Video | `.mp4`, `.mov`, `.avi` | Required |
| Raw CSI | `.mat` | WiMANS `trace` cells, Intel, HDF5 — auto-detected |
| Amplitude | `.npy` | Required; ~3000×30 for WiMANS |

### CLI / tools (single-file)

| Format | Description |
|--------|-------------|
| `.npy` | `(frames, subcarriers)` complex or amplitude; dict with `csi` + `timestamp_ms` |
| `.mat` | Fields: `csi`, `CSI`, `trace`, `data` |
| `.npz` | Zip with `csi` + optional timestamps |
| `.csv` / `.bin` | AURA ESP32 recorder output |

```bash
python tools/validate_csi.py myfile.npy
```

---

## WiMANS annotation sensing

When the upload filename matches `act_*` in `simulation/wimans/data/annotation.csv` (11,286 labels):

| Output | Source |
|--------|--------|
| **Count** | `number_of_users` from annotation |
| **Locations** | `user_N_location` → a/b/c/d/e → XY map |
| **Activities** | `user_N_activity` → vitals priors |
| **Vitals BPM** | Activity-based (wave, lie_down, pick_up, walk, …) |
| **CSI refinement** | Small position nudge + waveform display from amplitude |

API response includes:
```json
{
  "wimans_sensing": true,
  "wimans_source": "annotation",
  "wimans_count": 3,
  "wimans_activities": ["wave", "lie_down", "pick_up"]
}
```

For unlabeled `.npy` files, AURA falls back to the sklearn model in `simulation/wimans/models/wimans_sensing.joblib`. Retrain on real data — see [WIMANS_TRAINING.md](WIMANS_TRAINING.md).

---

## CSV / binary format (ESP32 recordings)

AURA binary frame (18-byte header + I/Q):

```
magic(4) | version(1) | node_id(1) | link_id(1) | reserved(1)
timestamp_ms(4) | rssi(1) | channel(1) | subcarriers(2) | payload_bytes(2) | IQ...
```

CSV export from `tools/record_session.py`:

```csv
timestamp_ms,node_id,rssi,channel,iq
0,1,-45,6,"[0,1,-2,3,...]"
```

I/Q values are int8, interleaved **Imaginary, Real** (Espressif CSI format).

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Upload error on `.mat` | Ensure WiMANS ZIP extracted; try matching `.npy` from same `act_*` folder |
| Count wrong / always same | Filenames must match `act_*` stem; `git pull` for latest processor |
| `wimans_source` not `annotation` | Rename files to `act_X_Y.mp4/.mat/.npy` |
| No targets, motion only | `.mat` may lack phase — dashboard merges `.npy` amplitude automatically |
| Video/CSI length mismatch | WiMANS clips are 3 s; CSI trimmed to video duration on upload |
| `.mat` load error | `pip install mat73 h5py` for HDF5 WiMANS traces |
| Hard refresh needed | `Ctrl+Shift+R` after `git pull` |

---

## Related docs

- [WIMANS_TRAINING.md](WIMANS_TRAINING.md) — train model on real amplitude files
- [WIRELESS_AND_SIMULATION.md](WIRELESS_AND_SIMULATION.md) — full format reference
- [HARDWARE_SETUP.md](HARDWARE_SETUP.md) — record your own CSI in the field
