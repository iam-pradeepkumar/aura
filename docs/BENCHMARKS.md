# AURA Benchmarks & Specifications

Expected performance for ESP32-based offline CSI disaster sensing. Values are **indicative** from ESP32 CSI literature, WiDFS 3.0 paper (Intel 5300 baseline), and Espressif esp-csi guidance — **validate in your deployment environment**.

---

## System Specifications

| Parameter | Value |
|-----------|-------|
| RF band | 2.4 GHz (802.11b/g/n) |
| Channel | 6 (fixed, configurable in firmware) |
| CSI sample rate | ~10–20 Hz (ESP32 MGMT/beacon limited) |
| Subcarriers | 52–128 (chip/firmware dependent) |
| Antennas | 1 TX + 1 RX per link (SISO bistatic) |
| Network required | **None** |
| Internet required | **None** |
| Power per node | ~80–150 mA @ 5V USB |

---

## Sensing Function Benchmarks

### 1. Motion Detection

| Metric | ESP32 AURA (outdoor/debris) | Reference (WiDFS 3.0 indoor, Intel 5300) |
|--------|----------------------------|---------------------------------------------|
| Detection range | 3–8 m per link | 10+ m indoor LOS |
| Latency | 50–100 ms (1–2 frames) | ~8.5 ms feature extract |
| False alarm rate | 5–15% (multipath wind/debris) | <5% indoor |
| Method | SRCC + amplitude variance | SRCC + Doppler tensor |

**Note:** Debris multipath increases false positives — use ≥3 RX nodes for consensus.

### 2. Moving Target Localization

| Metric | Expected |
|--------|----------|
| XY accuracy | 0.5–2.0 m (4-node square, 10 m area) |
| Velocity resolution | ~0.1 m/s |
| Acceleration | Derived from velocity delta; noisy below 0.2 m/s² |
| Update rate | 10–20 Hz |

Coarse range from delay domain; angle from phase slope across subcarriers (SISO limitation — SIMO improves to ~0.3 m indoor per paper).

### 3. Tracking

| Metric | Expected |
|--------|----------|
| Max simultaneous targets | 2–4 (SISO, 4 nodes) |
| Trajectory memory | Full session |
| Entry/exit detection | Gate distance 1.5 m (configurable) |
| ID switch risk | Moderate when targets cross paths |

### 4. Static Target Localization

| Metric | Expected |
|--------|----------|
| Range | 2–5 m (respiration-driven phase) |
| XY accuracy | 1–3 m |
| Requires | Visible micro-Doppler from breathing (0.1–0.5 Hz) |
| Best case | Survivor lying still within 3 m of RX |

Static detection relies on **vital-sign micro-motion** — not purely zero-Doppler objects.

### 5. Vital Sign Estimation

| Vital | Band (Hz) | BPM range | Rest reference | ESP32 accuracy |
|-------|-----------|-----------|----------------|----------------|
| Respiration | 0.1–0.5 | 6–30/min | ~11/min | ±2–4 BPM @ 3–5 m |
| Heartbeat | 0.8–2.0 | 48–120/min | ~65/min | ±5–15 BPM (harder on ESP32) |

**Requirements:**
- Minimum 2 s window (3 s recommended)
- Line-of-sight or partial through light debris
- Subject relatively still

Heartbeat is significantly harder than respiration on ESP32 due to lower CSI sample rate vs Intel 5300 (1000 Hz).

---

## Range & Coverage

| Deployment | Approximate coverage |
|------------|---------------------|
| 1 TX + 1 RX | Single link, 3–8 m radius |
| 1 TX + 4 RX (10 m perimeter) | ~10 m × 10 m search cell |
| Multiple TX (staggered) | Extended rubble pile — non-overlapping channels |

**Through debris:** Range drops 30–70% vs open air depending on material (concrete, rebar, water).

---

## Comparison to Reference Projects

| Feature | Intel 5300 (csiread / WiDFS 3.0) | AURA ESP32 |
|---------|----------------------------------|------------|
| Cost per node | $500+ (laptop + NIC) | ~$8–15 (ESP32-C6) |
| Sample rate | Up to 1000 Hz | ~20 Hz |
| Bandwidth | 20 MHz | ~20 MHz (HT) |
| Outdoor / no network | Impractical | **Designed for** |
| Vital signs | Strong indoor | Feasible at close range |
| Multi-target F1 (paper) | 0.629 counting | Target 0.4–0.6 (field-dependent) |

---

## Latency Budget (End-to-End)

| Stage | Time |
|-------|------|
| CSI capture | 50 ms |
| UART transfer | 5–10 ms |
| SRCC + Doppler + vitals | 20–50 ms (Python, Pi 4 class) |
| Display update | 33 ms (30 fps video) |
| **Total** | **~150–200 ms** |

---

## Validation Checklist

Before demonstration:

- [ ] CSI frame rate ≥ 15 Hz (`validate_csi.py`)
- [ ] Motion detected when person walks through link
- [ ] Count increases with additional people
- [ ] Respiration BPM 8–20 when subject still at 3 m
- [ ] Static survivor marked when motion stops but vitals present
- [ ] Video and CSI timestamps overlap (same 3 s clip)

---

## Known Limitations

1. **SISO** — no cross-antenna phase cancellation; SRCC mitigates but not equivalent to MIMO
2. **Low sample rate** — heartbeat estimation is challenging
3. **Coarse delay resolution** — ESP32 subcarrier count limits range precision
4. **Multipath in rubble** — can create ghost targets; use multi-node fusion
5. **Not certified** — supplementary tool only, not replacement for professional SAR equipment
