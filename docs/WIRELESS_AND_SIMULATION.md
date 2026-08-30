# AURA Wireless + Simulation Guide

## Part 1: All Nodes Wireless to Laptop (No USB Cables)

### Setup (one-time)

1. **Laptop WiFi hotspot** (local only — no internet needed):
   - SSID: `AURA_HUB`
   - Password: `aura2026`
   - Note your laptop IP (usually `192.168.4.1` on Windows/macOS hotspot)

2. If your hotspot IP is different, edit `firmware/common/aura_protocol.h`:
   ```c
   #define AURA_HUB_IP "192.168.137.1"   // your laptop IP
   ```
   Re-flash all RX nodes after changing.

3. Flash **aura_rx** on each ESP32 with unique node ID:
   ```bash
   idf.py -D CONFIG_AURA_NODE_ID=1 build flash   # Node 1
   idf.py -D CONFIG_AURA_NODE_ID=2 build flash   # Node 2
   # ... nodes 3, 4
   ```

4. Flash **aura_tx** on the probe transmitter (battery powered, no laptop).

### Field use

1. Power on TX node, then all RX nodes.
2. RX nodes auto-join `AURA_HUB` hotspot and stream CSI via UDP.
3. On laptop:
   ```bash
   cd simulation && pip install -r requirements.txt
   python ../tools/wireless_hub.py
   ```

### Live dashboard shows

- **Survivor map** — XY positions from all nodes combined
- **People count** — aggregated across nodes
- **Vital signs** — respiration waveform
- **Node status** — which nodes are connected wirelessly

```
┌─────────────────────────────────────────────────────┐
│  Laptop Hotspot (AURA_HUB)  ← WiFi →  RX Node 1   │
│         ↑                              RX Node 2   │
│    wireless_hub.py                     RX Node 3   │
│    (all results live)                  RX Node 4   │
└─────────────────────────────────────────────────────┘
         TX probe (battery, no cable)
```

---

## Part 2: Simulation with Your .mp4 + .npy / .mat Files

### Your files

Place in one folder, e.g. `my_data/`:
```
my_data/
  rescue.mp4      ← 3-second scene video
  rescue.npy      ← CSI array (same session)
  # OR rescue.mat
```

### Supported CSI formats

| Format | Description |
|--------|-------------|
| `.npy` | NumPy array — shapes: `(frames, subcarriers)` complex, `(frames, tones, nrx, ntx)`, or `(frames, N, 2)` real/imag |
| `.mat` | MATLAB — fields: `csi`, `CSI`, `data`, or `csi_data` |
| `.npz` | NumPy zip with `csi` + optional `timestamp_ms` |
| `.csv` / `.bin` | AURA ESP32 recorder output |

### Run simulation

**Option A — explicit paths:**
```bash
cd simulation
pip install -r requirements.txt

python ../tools/validate_csi.py ../my_data/rescue.npy
python run_simulation.py --video ../my_data/rescue.mp4 --csi ../my_data/rescue.npy
```

**Option B — auto-detect from folder:**
```bash
python run_simulation.py --data-dir ../my_data
```

**Intel 5300 / csiread .mat (1000 Hz):**
```bash
python run_simulation.py --video rescue.mp4 --csi csi.mat --fs 1000
```

### .npy format examples

**Simple complex array:**
```python
import numpy as np
csi = np.array(...)  # shape (60, 30) complex64 for 3s @ 20Hz
np.save("rescue.npy", csi)
```

**With timestamps (recommended):**
```python
np.save("rescue.npy", {"csi": csi, "timestamp_ms": timestamps, "node_id": node_ids})
```

**Intel/csiread style `(packets, tones, nrx, ntx)`:**
```python
np.save("rescue.npy", csi)  # shape (3000, 30, 3, 2) — auto-detected
```

### Save demo video
```bash
python run_simulation.py --video rescue.mp4 --csi rescue.mat --save demo_output.mp4
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Nodes not appearing in wireless hub | Check hotspot SSID/password; laptop firewall allow UDP 5555 |
| `.mat` load error | Install csiread: `pip install csiread` or ensure `csi` field exists |
| `.npy` wrong shape | Run `validate_csi.py` — see supported shapes above |
| Video/CSI length mismatch | Use same 3s clip; set `--fs` if timestamps missing |
| No survivors detected | Real CSI required — ensure human present during recording |
