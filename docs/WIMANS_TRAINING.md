# WiMANS Training for AURA

AURA integrates the [WiMANS](https://github.com/huangshk/WiMANS) benchmark for accurate **people count**, **localization** (locations A–E), and **vitals** on uploaded `act_*.npy` amplitude CSI.

## Quick start (recommended)

After downloading WiMANS from [Kaggle](https://www.kaggle.com/datasets/shuokhuang/wimans):

```bash
# Unzip so you have dataset/wifi_csi/amp/act_*.npy
python tools/train_wimans.py \
  --amp-dir /path/to/WiMANS/dataset/wifi_csi/amp \
  --epochs 60 \
  --batch-size 128
```

This writes `simulation/wimans/models/wimans_sensing.pt`. Restart the dashboard and upload matching `video + .mat + .npy` triplets.

## What gets trained

| Output | Description |
|--------|-------------|
| **Count** | 0–5 users (multiclass head) |
| **Identity** | 6 user slots occupied |
| **Location** | WiMANS positions a–e per slot → XY map |

Annotations ship in `simulation/wimans/data/annotation.csv` (11,286 labels).

## Bootstrap model (default)

The repo includes a model trained on **synthetic** CSI aligned to WiMANS labels (~96% count accuracy on synthetic validation). For production accuracy on your uploads, **retrain on real `.npy` amplitude files**.

## Example: `act_100_5`

Ground truth (from annotation.csv): **3 users** at locations **a, b, c** in `empty_room`, 5 GHz band.

## Dashboard

After training, uploads show:

- `wimans_sensing: true`
- `wimans_count` in API response
- Processor version `2026.08.31-22+`

Hard refresh (`Ctrl+Shift+R`) after retraining.
