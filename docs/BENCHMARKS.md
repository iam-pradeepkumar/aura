# AURA Benchmarks & Specifications

Expected performance for ESP32-based offline CSI disaster sensing and WiMANS simulation benchmarks.

Values are **indicative** from ESP32 CSI literature, WiDFS 3.0 (Intel 5300), WiMANS dataset specs, and field testing guidance — **validate in your deployment environment**.

---

## System specifications

| Parameter | Simulation (WiMANS) | Live hardware (ESP32) |
|-----------|---------------------|------------------------|
| RF band | 2.4 / 5 GHz (dataset) | 2.4 GHz (802.11n) |
| Channel | Per dataset | 6 (fixed, firmware) |
| CSI sample rate | ~1000 Hz | ~10–20 Hz |
| Subcarriers | 30 (WiMANS amp) | 52–128 → normalized to 64 |
| Antennas | MIMO (dataset) | SISO per link |
| Network | None (offline files) | Laptop hotspot only |
| Internet | None | None |
| Power per node | N/A | ~80–150 mA @ 5V |

**Processor version reference:** `2026.08.31-26`

---

## Sensing function benchmarks

### 1. Motion detection

| Metric | ESP32 live (outdoor) | WiMANS simulation |
|--------|----------------------|---------------------|
| Detection range | 3–8 m per link | Dataset-dependent |
| Latency | 50–200 ms | Real-time replay |
| False alarm rate | 5–15% (wind/debris multipath) | Low on labeled data |
| Method | SRCC + amplitude variance | SRCC + WiMANS annotation |

Use ≥3 RX nodes for consensus in the field.

### 2. People counting

| Mode | Expected accuracy |
|------|-------------------|
| WiMANS `act_*` + annotation | **Exact** (ground truth from annotation.csv) |
| WiMANS + sklearn (retrained) | 85–95% on held-out real amp files |
| WiMANS + synthetic model | Poor on real data — retrain required |
| ESP32 live hardware | 1–4 targets; field-dependent; multinode fusion helps |

### 3. Localization (XY map)

| Metric | ESP32 live | WiMANS annotation |
|--------|------------|-------------------|
| XY accuracy | 0.5–2.5 m (4-node, 10 m area) | Exact a–e grid positions |
| Reference frame | `config.yaml` node positions | `layouts.py` per environment |
| Update rate | ~4 Hz dashboard / ~20 Hz CSI | Per video frame |

Each live RX node localizes from **its own corner**; `fuse_multinode_targets()` merges duplicates within ~1.6 m.

### 4. Tracking

| Metric | Expected |
|--------|----------|
| Max simultaneous targets | 2–4 (SISO, 4 nodes) |
| Trajectory memory | Full session |
| Entry/exit events | Gate distance ~1.5 m |
| ID switch risk | Moderate when paths cross |

### 5. Vital sign estimation

| Vital | Band (Hz) | BPM range | Rest reference | ESP32 @ 20 Hz |
|-------|-----------|-----------|----------------|---------------|
| Respiration | 0.1–0.55 | 6–30/min | ~11–18/min | ±2–4 BPM @ 3–5 m |
| Heartbeat | 0.7–2.0 | 48–120/min | ~58–85/min | ±5–15 BPM (harder) |

**Live hardware requirements:**
- `window_packets: 200` (~10 s at 20 Hz) in `config.yaml`
- Subject relatively still
- Partial line-of-sight through light debris

**WiMANS simulation:** Activity-based BPM priors (wave, lie_down, pick_up, walk, …) plus CSI waveform display.

---

## Range & coverage

| Deployment | Approximate coverage |
|------------|---------------------|
| 1 TX + 1 RX | Single link, 3–8 m radius |
| 1 TX + 4 RX (10 m perimeter) | ~10 m × 10 m search cell |
| Through concrete/rebar | Range drops 30–70% vs open air |

---

## Latency budget

### Live hardware (end-to-end)

| Stage | Time |
|-------|------|
| CSI capture (ESP32) | 50 ms |
| WiFi UDP to laptop | 5–20 ms |
| Buffer fill (first result) | 4–10 s |
| SRCC + localization + vitals | 20–80 ms |
| Dashboard WebSocket | 250 ms refresh |
| **Steady-state update** | **~250–500 ms** |

### Simulation

| Stage | Time |
|-------|------|
| Upload + merge mat+npy | 1–5 s |
| Full session process | 2–15 s (dataset size) |
| Per-frame scrub | Real-time |

---

## Comparison: Intel 5300 vs AURA ESP32 vs WiMANS sim

| Feature | Intel 5300 (WiDFS) | AURA ESP32 live | AURA WiMANS sim |
|---------|-------------------|-----------------|-----------------|
| Cost per node | $500+ | ~$8–15 | N/A (files) |
| Sample rate | Up to 1000 Hz | ~20 Hz | ~1000 Hz |
| Outdoor / no network | Impractical | **Designed for** | Offline replay |
| Count accuracy | Paper F1 ~0.63 | Field-dependent | Exact on `act_*` |
| Vital signs | Strong indoor | Feasible close range | Activity priors + CSI |

---

## Validation checklist

### Before field deployment

- [ ] All RX nodes show `link: good` in dashboard (>8 Hz packet rate)
- [ ] TX powered; channel 6 confirmed
- [ ] `node_positions` measured and entered in `config.yaml`
- [ ] Motion detected when person walks through search area
- [ ] Count increases with additional people
- [ ] Respiration BPM 8–25 when subject still at 3 m

### Before simulation demo

- [ ] `act_*` filenames match across `.mp4`, `.mat`, `.npy`
- [ ] `curl /api/version` shows current `processor_version`
- [ ] `wimans_source: "annotation"` for labeled WiMANS files
- [ ] `validate_csi.py` passes on `.npy`

---

## Known limitations

1. **SISO** — SRCC helps but cannot match full MIMO performance
2. **20 Hz sample rate** — heartbeat is harder than respiration on ESP32
3. **Outdoor multipath** — ghost targets possible; use 4-node fusion
4. **Simulation ≠ hardware** — WiMANS annotation accuracy does not transfer to live ESP32 without field calibration
5. **Not certified** — supplementary research tool only

---

## Related docs

- [HARDWARE_SETUP.md](HARDWARE_SETUP.md) — deploy ESP32 nodes
- [SIMULATION_GUIDE.md](SIMULATION_GUIDE.md) — WiMANS upload workflow
- [WIMANS_TRAINING.md](WIMANS_TRAINING.md) — improve sklearn fallback
