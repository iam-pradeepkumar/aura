# AURA Simulation Guide

Run the **video-synced matplotlib viewer** using your **real ESP32 CSI recording** and a matching scene video (typically 3 seconds).

---

## Prerequisites

- Python 3.10+
- Real CSI file from `tools/record_session.py` (`.csv` or `.bin`)
- Video filmed during the **same time window** as CSI capture

---

## Step 1: Record CSI (Hardware)

```bash
python tools/record_session.py -p /dev/ttyUSB0 -d 3 -o my_session.bin
```

Outputs:
- `my_session.bin` — raw AURA binary (UART stream)
- `my_session.csv` — parsed for simulation

---

## Step 2: Validate CSI

```bash
python tools/validate_csi.py my_session.csv
```

Expected output:
```
Frames: ~60 (for 3 s @ 20 Hz)
Subcarriers: 52–128 (chip-dependent)
Sample rate: ~20 Hz
Duration: ~3.00 s
OK — ready for run_simulation.py
```

If frame count is 0, re-record with TX node powered on.

---

## Step 3: Configure Node Layout

Edit `simulation/config.yaml` to match **measured** node positions:

```yaml
area_size_m: 10.0
node_positions:
  1: [0.0, 0.0]
  2: [10.0, 0.0]
  3: [10.0, 10.0]
  4: [0.0, 10.0]
```

Accurate positions improve XY localization via multilateration.

---

## Step 4: Run Live Viewer

```bash
cd simulation
pip install -r requirements.txt
python run_simulation.py --video ../rescue.mp4 --csi ../my_session.csv
```

### Display panels

| Panel | Content |
|-------|---------|
| **Top-left** | Scene video (synced frame-by-frame) |
| **Bottom-left** | Top-down map — blue squares = ESP32 nodes, red = moving, orange = static survivors |
| **Top-right** | People count + motion/static indicator |
| **Middle-right** | Respiration waveform + BPM (reference ~11/min at rest) |
| **Bottom-right** | Heartbeat waveform + BPM (reference ~65/min at rest) |

---

## Step 5: Save Animation (Optional)

```bash
python run_simulation.py --video rescue.mp4 --csi my_session.csv --save demo.mp4
```

Requires `ffmpeg` installed.

---

## CSV Format Reference

If exporting CSI manually, use:

```csv
timestamp_ms,node_id,rssi,channel,iq
0,1,-45,6,"[0,1,-2,3,...]"
50,1,-44,6,"[1,0,-1,2,...]"
```

- `iq`: Python list of int8 values, interleaved **Imaginary, Real** per Espressif CSI format
- One row per CSI frame

---

## Multi-Node Sessions

For multiple RX nodes, merge CSVs by `timestamp_ms` or record nodes sequentially while survivors hold position. Full simultaneous multi-node merge is planned; current pipeline uses per-node CSI with config-based multilateration when multiple node IDs are present in one file.

---

## No Synthetic Data Policy

AURA does **not** include fake survivor datasets. All detection outputs derive from your uploaded CSI. If the scene has no human CSI signature, count will be zero — this is correct behavior.
