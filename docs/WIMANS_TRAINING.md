# WiMANS Training for AURA

AURA integrates the [WiMANS](https://github.com/huangshk/WiMANS) benchmark for **people count**, **localization** (locations A–E), **activities**, and **vitals** on uploaded CSI datasets.

---

## How sensing works (current)

| Filename pattern | Sensing method | Accuracy |
|------------------|----------------|----------|
| `act_X_Y.*` (in annotation.csv) | **Annotation ground truth** | Exact count, locations, activities |
| Other `.npy` files | **sklearn model** fallback | Depends on training data |

When you upload `act_100_5.mp4` + `act_100_5.mat` + `act_100_5.npy`, AURA reads `simulation/wimans/data/annotation.csv` and returns:

- **Count:** 3
- **Locations:** a, b, c → XY in `empty_room`
- **Activities:** wave, lie_down, pick_up
- **API:** `wimans_source: "annotation"`

No model training is required for labeled WiMANS `act_*` files.

---

## When to train

Train a custom model when:

- You have WiMANS `.npy` amplitude files but **non-standard filenames**
- You want better fallback accuracy on **unlabeled** amplitude CSI
- You collected your own amplitude CSI in WiMANS format

Training uses **scikit-learn only** — no PyTorch (avoids large disk installs).

---

## Quick start

### 1. Download WiMANS

From [Kaggle — WiMANS](https://www.kaggle.com/datasets/shuokhuang/wimans):

```
WiMANS/
  dataset/
    wifi_csi/
      amp/
        act_1_1.npy
        act_100_5.npy
        ...
```

Find your amp folder:

```bash
find ~ -name "act_100_5.npy" 2>/dev/null
```

### 2. Install dependencies

```bash
pip install -r simulation/requirements.txt
```

### 3. Train

```bash
# Real WiMANS amplitude files (recommended)
python tools/train_wimans.py --amp-dir ~/WiMANS/dataset/wifi_csi/amp

# Auto-detect amp folder under a parent path
python tools/train_wimans.py --amp-dir ~/Downloads/WiMANS

# Synthetic bootstrap only (no .npy files needed)
python tools/train_wimans.py --synthetic-only

# Default — tries synthetic if no amp dir found
python tools/train_wimans.py
```

Output: `simulation/wimans/models/wimans_sensing.joblib` (~17 MB)

### 4. Restart dashboard

```bash
python dashboard/run.py
```

Upload matching `video + .mat + .npy` triplets. For `act_*` files, annotation sensing takes priority over the model.

---

## What gets trained

| Head | Output |
|------|--------|
| **Count** | 0–5 users (multiclass) |
| **Identity** | 6 user slots occupied (0/1) |
| **Location** | WiMANS slot → position a–e |

Labels from `simulation/wimans/data/annotation.csv` (11,286 entries).

Layouts map a–e to XY per environment in `simulation/wimans/layouts.py`:
- `empty_room`
- `classroom`
- `meeting_room`

---

## Shipped bootstrap model

The repo includes `simulation/wimans/models/wimans_sensing.joblib` trained on **synthetic** CSI aligned to WiMANS labels. Use it as a fallback; for production accuracy on real uploads, **retrain on real `act_*.npy` files**.

Metadata: `simulation/wimans/models/wimans_sensing.json`

---

## Example: `act_100_5`

From `annotation.csv`:

| Field | Value |
|-------|-------|
| Environment | `empty_room` |
| WiFi band | 5 GHz |
| Users | 3 |
| Locations | a, b, c |
| Activities | wave, lie_down, pick_up |

Expected dashboard output after upload:
```json
{
  "target_count": 3,
  "wimans_sensing": true,
  "wimans_source": "annotation",
  "wimans_count": 3,
  "wimans_activities": ["wave", "lie_down", "pick_up"]
}
```

---

## Troubleshooting training

| Error | Fix |
|-------|-----|
| `need at least one array to stack` | Wrong `--amp-dir` — use real path, not `/path/to/...` placeholder |
| No `act_*.npy` found | Point to `wifi_csi/amp` subfolder |
| Disk quota / PyTorch error | Use current repo — PyTorch removed; sklearn only |
| Training slow | Use `--max-samples 2000` for quick test |

```bash
python tools/train_wimans.py --help
```

---

## Dashboard API fields

After upload or training:

| Field | Meaning |
|-------|---------|
| `wimans_sensing` | WiMANS path was used |
| `wimans_source` | `"annotation"` or `"sklearn"` |
| `wimans_count` | WiMANS-derived person count |
| `wimans_activities` | Per-user activities (annotation mode) |
| `processor_version` | e.g. `2026.08.31-26` |

Hard refresh browser after `git pull`: **Ctrl+Shift+R**

---

## Related docs

- [SIMULATION_GUIDE.md](SIMULATION_GUIDE.md) — upload workflow
- [WIRELESS_AND_SIMULATION.md](WIRELESS_AND_SIMULATION.md) — format reference
