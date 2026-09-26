# AURA Sensing Engine Upgrade — Design Document

**Status:** Implemented (v2 enabled via `hardware.sensing_engine: v2` in `simulation/config.yaml`)  
**Project:** AURA — Adaptive Urban Rescue & Alert Array (`iam-pradeepkumar/AURA`)  
**SIH context:** SIH26223 — device-free survivor detection & localization for disaster management  
**Processor baseline:** `simulation/aura_processor/` live path v`2026.09.18-50` via `tools/field_live.py`

---

## Executive summary

AURA already implements a complete **offline** ESP32 CSI pipeline: SRCC phase cleaning, multinode motion fusion, corner-based XY localization, temporal confirmation, vitals bandpass extraction, and a human-in-the-loop DM Console for hazard alerts. Four mature reference projects offer techniques AURA can **learn from and reimplement in Python** for ESP32 constraints — not copy as a dependency stack.

**Recommendation:** Upgrade AURA incrementally inside `simulation/aura_processor/` (new modules under a `sensing_v2/` package namespace), preserving:

- Existing `aura_tx` / `aura_rx` firmware and AURA UDP protocol (`:5555`, magic `0x41555241`)
- `LiveFieldEngine` orchestration and `field_live.py` viewer
- DM Console **pending → approve → broadcast** flow (no auto-publish)
- Full offline operation (no cloud inference)

**Do not** replace AURA with spatial-ai / wifi-densepose Rust servers wholesale — incompatible protocols, different deployment model, and loss of integrated alerts + simulation lab.

---

## A. Reference project research

### A.1 wifi-densepose-mat (WiFi-Mat / RuView ecosystem)

| Item | Detail |
|------|--------|
| **Repos** | [ruvnet/RuView](https://github.com/ruvnet/ruview) (umbrella), [ruvnet/wifi-densepose](https://github.com/ruvnet/wifi-densepose), crate `wifi-densepose-mat` on docs.rs; user cited [xnetsc/wifi-densepose](https://github.com/xnetsc/wifi-densepose) as a fork/mirror in the same lineage |
| **License** | **MIT** (main workspace); some sensing-server crates may be **MIT OR Apache-2.0** dual-licensed — verify per crate before porting code |
| **Published architecture** | **ADR-001: WiFi-Mat Disaster Detection** — Domain-Driven Design with bounded contexts: Detection, Localization, Alerting, Integration (adapters to signal + NN crates) |
| **Signal pipeline (documented)** | CSI ingest → adapters → `DetectionPipeline` (breathing, heartbeat, movement, ensemble classifier) → localization (triangulation, fingerprinting, depth) → triage (`TriageCalculator`, START) → alert dispatcher |
| **Classification** | Ensemble of vital-sign + movement modalities; optional neural adapters (`wifi-densepose-nn`); debris material models for depth |
| **Hardware assumptions** | Originally Intel 5300 / research NICs; v2 adds ESP32 path via `wifi-densepose-hardware`. **3D depth and sub-meter claims assume multinode geometry and often higher-quality CSI than ESP32 SISO at 20 Hz** |
| **ESP32 fit** | Presence/motion/breathing concepts portable; micro-Doppler heartbeat and 3D rubble depth are **partial** on ESP32 — see §D |

**Key ADR-001 entities (inform design, not copy):** `Survivor`, `ScanZone`, `BreathingDetector`, `HeartbeatDetector`, `MovementClassifier`, `Triangulator`, `DepthEstimator`, `TriageCalculator`.

---

### A.2 spatial-ai (RescueSense)

| Item | Detail |
|------|--------|
| **Repo** | [arjxnt/spatial-ai](https://github.com/arjxnt/spatial-ai) |
| **License** | **MIT** (copyright notice references rUv / RuView lineage) |
| **Architecture** | ESP32 firmware → UDP CSI (documented **100 Hz** on ESP32-S3) → **Rust v2 workspace** (~15 crates: signal, NN, vitals, hardware, CLI) → Web UI (WebSocket) + optional **MQTT / Home Assistant** |
| **Packet format** | Magic `0xC511_0001`, UDP port **5005** — **incompatible with AURA** (`0x41555241`, port **5555**) |
| **Signal pipeline** | Weighted subcarrier features, temporal variance, Goertzel-style breathing estimation, motion debounce with baseline EMA, multistatic fusion, Kalman pose tracker, 17-keypoint NN inference |
| **Classification** | Trained pose model + fall flags; vitals via bandpass / spectral peaks |
| **Hardware** | ESP32-S3 primary; optional ESP32-C6 + 60 GHz mmWave fallback node |
| **ESP32 fit** | Best reference for **ESP32-native motion debounce** and **MQTT interoperability patterns**; pose/fall models require **retraining on AURA CSI** — not plug-and-play |

---

### A.3 ESP32-Realtime-System

| Item | Detail |
|------|--------|
| **Repo** | [RS2002/ESP32-Realtime-System](https://github.com/RS2002/ESP32-Realtime-System) |
| **License** | **Not found in repository metadata during this review** — treat as **unknown / all-rights-reserved until LICENSE file confirmed**. Do not copy code without explicit permission |
| **Architecture** | Python desktop app + ESP32 serial/UDP CSI; modular scripts: `fall_detection.py`, `breath_detection.py`, `intrusion_detection.py`, `activity_recognition.py`, `gesture_recognition.py` |
| **Signal pipeline** | CSI parse (`csi_data_read_parse.py`) → per-task Python ML (includes data-driven fall detection) → visualization |
| **Datasets** | Related [WiFall](https://huggingface.co/datasets/RS2002/WiFall) on Hugging Face — ESP32-S3, **52 subcarriers**, ~**100 Hz**, actions: fall/jump/sit/stand/walk |
| **Hardware** | ESP32-S3 SISO, 2.4 GHz, 20 MHz — **closest match to AURA hardware class** |
| **ESP32 fit** | Excellent **reference for fall/breath task structure** and ESP32 sampling rates; reimplement algorithms, do not vendor code without license clarity |

**Patent note:** README references Chinese patent application 2023116499786 — independent implementation required.

---

### A.4 espressif/esp-csi (official reference)

| Item | Detail |
|------|--------|
| **Repo** | [espressif/esp-csi](https://github.com/espressif/esp-csi) |
| **License** | **Apache-2.0** |
| **Architecture** | CSI capture in WiFi RX callback → optional **AGC/FFT gain compensation** (`esp_radar_compensate_rx_gain`) → `esp-radar` features (`waveform_wander`, `waveform_jitter`) → **`esp_wifi_sensing` FSM** (baseline, hysteresis, ACTIVE hold, on-site training) |
| **Signal pipeline** | On-device motion/presence FSM; PC-side parsing in `csi_data_read_parse.py` for analysis |
| **Examples** | `csi_send` / `csi_recv`, `wifi_sensing_demo` (LED + Web Serial tuning), `console_test` |
| **Hardware** | ESP32 / S2 / S3 / C3 / C5 / C6 / C61 — **same family as AURA** |
| **ESP32 fit** | **Best reference for gain compensation, wander/jitter features, and calibration FSM** — can inform both firmware hints and laptop-side preprocessing |

---

## B. Gap analysis — stage-by-stage

**AURA live pipeline location:** `simulation/aura_processor/` — there is no `signal_processing.py`; the live path is `hardware_live.py` → `hardware_state.py` → `hardware_sensing.py` + `hardware_fusion.py` + `hardware_tracker.py` + `vitals.py` + `srcc.py` + `multitarget.py`.

| Stage | AURA today | wifi-densepose-mat | spatial-ai | ESP32-Realtime | esp-csi |
|-------|------------|-------------------|------------|----------------|---------|
| **CSI ingest** | UDP `:5555`, AURA 18-byte header, I/Q int8, ring buffer 512 (`wireless.py`) | Adapter layer to internal `CsiFrame`; multiple formats | UDP `:5005`, magic `0xC511_0001` | Serial / parsed CSV `CSI_DATA` records | UART 921600 or WiFi CSI callback |
| **Gain / DC fix** | Normalize to 64 SC, DC spike removal (`hardware_csi.py`) | Signal crate preprocessing | Per-frame amp/phase parse | Raw complex from 52 SC | **AGC + FFT gain compensation** (`esp_radar`) |
| **Phase correction** | `preprocess_csi` (mean removal) + **SRCC** (`srcc.py`) | Phase clean + SVD sources | Multistatic phase features | Task-specific | Wander/jitter on radar features |
| **Motion detection** | `esp32_motion_score` + `SceneCalibrator` + 2-node verdict (`hardware_motion.py`, `hardware_accuracy.py`) | `MovementClassifier` + ensemble | Weighted subcarrier temporal diff + baseline EMA debounce | Intrusion / activity scripts | **FSM**: hysteresis + ACTIVE hold (`esp_wifi_sensing`) |
| **Localization** | Delay-bin AoA + SVD + corner constraints + mirror fix (`multitarget.py`, `hardware_localize.py`) | Triangulation + fingerprinting + **depth model** | Multistatic fusion + Kalman pose tracker | LoFi 2D tag (separate) | Not in reference (presence only) |
| **Multinode fusion** | `fuse_hardware_targets` + RSSI blend + `OccupancyConfirmFilter` | `PositionFuser` / Kalman 3D | `fuse_multi_node_features` | Single-link demos | Per-peer FSM channels |
| **People count** | `estimate_person_count` heuristics + conservative `consensus_target_count` (cap 8) | Zone-level survivor list | Up to 4 (documented) | Population estimation (pending) | Presence binary per channel |
| **Vitals — respiration** | scipy bandpass + PSD on phase PCs (`vitals.py`) | `BreathingDetector` dedicated | Goertzel 0.1–0.5 Hz band | `breath_detection.py` | Indirect via wander (not BPM) |
| **Vitals — heartbeat** | Bandpass 0.7–2.0 Hz + PSD | Micro-Doppler `HeartbeatDetector` | Bandpass BPM/HR | Limited in demo | **Not in esp-csi reference** |
| **Classification / triage** | Motion + confidence only; **no START triage** | **START triage** (`TriageCalculator`) | Fall flag + pose class | Fall / action ML | ACTIVE/INACTIVE |
| **Tracking** | `FieldTracker` EMA + trails (`hardware_tracker.py`) | Survivor entity state | 17-keypoint pose + ID | N/A | FSM per channel |
| **Alerts / output** | `field_live.py` matplotlib; DM Console separate (`disaster_alert/`) | Alert dispatcher + protocols | MQTT + WebSocket | Desktop UI only | LED + serial |
| **Human approval** | **DM pending → approve → broadcast** | Auto alert generation in MAT design | MQTT push (auto) | N/A | N/A |

### AURA strengths to preserve

- Integrated **Phase 1 alerts** (USGS/Open-Meteo) + **Phase 2 CSI rescue** in one product story
- **Offline hotspot** deployment (`AURA_HUB`) with documented field config
- **Multinode corner geometry** already wired in `config.yaml`
- **Conservative count = map markers** policy (post-rescue-hardening)
- **WiMANS simulation lab** for demo/training without hardware

### AURA gaps (where references are ahead)

1. No **ensemble vitals** scorer combining resp + HR + movement quality  
2. No **fall / collapse / distress** event detector  
3. No **START-compatible triage** surfaced to operators  
4. No **AGC/FFT gain normalization** on ESP32 CSI streams  
5. No **MQTT / dispatch interoperability** layer  
6. No **learned classifiers** for pose/fall (heuristics only on live path)  
7. **3D / depth-through-rubble** not attempted  
8. CSI sensing results **not bridged** to DM Console (by design today — opportunity)

---

## C. Proposed AURA-specific reimplementation (design only)

All new code should live under `simulation/aura_processor/sensing_v2/` with adapters into `LiveFieldEngine`, and cite sources in module docstrings: *"Informed by techniques described in [project], reimplemented for ESP32 CSI in AURA."*

### C.1 Target architecture (v2 layered on v1)

```
ESP32 (unchanged firmware)
    │ UDP :5555 AURA protocol
    ▼
WirelessReceiver (wireless.py)
    ▼
┌─────────────────────────────────────────────────────────┐
│  sensing_v2/preprocess.py                               │
│  • AGC/FFT gain compensation (informed by esp-csi)      │
│  • SRCC + Hampel outlier rejection (new)                │
│  • Subcarrier importance weights (informed by spatial-ai)│
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  sensing_v2/motion.py                                   │
│  • esp32_motion_score v2 (wander/jitter-inspired)       │
│  • Per-node baseline EMA + debounce FSM (esp-csi)       │
│  • SceneCalibrator v2 (occupied-scene guard — keep)       │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  sensing_v2/localize.py                                 │
│  • Existing multitarget AoA + corner fix (keep)         │
│  • RSSI trilateration refinement (keep)                 │
│  • Optional depth *estimate* layer (MAT-inspired)     │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  sensing_v2/vitals_ensemble.py                          │
│  • Parallel estimators: Goertzel resp, PSD resp,        │
│    micro-Doppler HR proxy, movement periodicity           │
│  • Ensemble score + confidence (MAT DetectionPipeline)  │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  sensing_v2/events.py                                   │
│  • Fall/collapse signature detector (WiFall-inspired)   │
│  • Distress: resp irregularity + prolonged stillness    │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  sensing_v2/triage.py                                   │
│  • START mapping: Immediate/Delayed/Minor/Deceased        │
│  • Output = *suggested* triage only                     │
└───────────────────────────┬─────────────────────────────┘
                            ▼
LiveFieldEngine (hardware_live.py) — fusion, tracker, confirm
                            ▼
Outputs:
  • field_live.py (map, count, vitals, events, triage badge)
  • Optional mqtt_bridge.py (local broker, no cloud)
  • Optional dm_bridge.py → enqueue *pending* DM item (human approve)
```

**Integration principle:** `sensing_v2` produces enriched per-target `SurvivorObservation` structs; `LiveFieldEngine` remains orchestrator. Feature flag: `hardware.sensing_engine: v1 | v2` in `simulation/config.yaml`.

---

### C.2 START-protocol triage → DM Console (human-in-the-loop)

**Informed by:** wifi-densepose-mat ADR-001 `TriageCalculator`, START table in WiFi-Mat user guide.

**AURA adaptation:**

| START status | Suggested CSI criteria (ESP32, conservative) | DM Console behavior |
|--------------|-----------------------------------------------|---------------------|
| **Immediate (Red)** | Confirmed presence + abnormal resp (10–29 BPM or irregular) OR fall event within 60 s + weak movement afterward | Create **pending** alert: "Possible immediate survivor — Zone X" |
| **Delayed (Yellow)** | Stable resp 8–20 BPM, low movement, multinode confidence ≥ 0.5 | Pending alert, lower priority |
| **Minor (Green)** | Walking signature (velocity > 0.3 m/s sustained) | Informational pending only |
| **Deceased (Black)** | **Never auto-classify** on CSI alone | Requires operator label; CSI may only suggest "no vitals detected" |

**Critical constraint:** Triage output is **`suggested_triage`** with confidence. `dm_bridge` calls `DisasterManagementQueue.enqueue()` — same path as USGS alerts. **No auto-approve, no auto-broadcast.**

DM Console UI addition (future): survivor card shows map position, vitals, suggested START color, Approve/Reject/Edit — mirrors existing hazard approval UX.

---

### C.3 Ensemble vitals classifier

**Informed by:** wifi-densepose-mat `DetectionPipeline` ensemble; spatial-ai Goertzel breathing; AURA existing `vitals.py`.

**Design:**

```text
Inputs per target (window ≥ 5 s @ 20 Hz):
  E1: Goertzel respiration peak (0.1–0.5 Hz)     — spatial-ai technique
  E2: Welch PSD respiration band (AURA vitals)   — existing
  E3: Phase PCA dominant periodicity             — existing
  E4: HR band energy ratio (0.8–2.0 Hz)          — MAT heartbeat proxy
  E5: Movement periodicity score (autocorr)      — distinguishes resp vs motion
  E6: Signal quality (SNR, subcarrier coherence) — esp-csi wander stability

Ensemble:
  resp_bpm  = weighted median(E1, E2, E3) with weights from E6
  hr_bpm    = report only if E4 > threshold AND E5 < threshold (subject still)
  confidence = f(E6, agreement across E1–E3)

Output: VitalsEstimate { resp_bpm, hr_bpm, resp_confidence, hr_confidence, quality }
```

**ESP32 note:** Heartbeat confidence should default **low** at 20 Hz; UI shows "HR: low confidence" unless window ≥ 10 s and subject still.

---

### C.4 Fall / distress event detection

**Informed by:** ESP32-Realtime-System / WiFall collapse signatures; spatial-ai fall flag; MAT `MovementType` (Gross → None transition).

**AURA reimplementation (heuristic + optional tiny classifier later):**

1. **Collapse signature (time-domain):**  
   - 0.5–2 s burst of high motion score (> 2× baseline)  
   - Followed by > 3 s low motion (< 0.3× baseline)  
   - Optional: spectral burst in 2–6 Hz band (impact)  

2. **Distress signature:**  
   - Irregular respiration (coefficient of variation > threshold)  
   - OR prolonged stillness with initial high motion (possible unconsciousness)  

3. **Output:** `DistressEvent { type: fall|collapse|irregular_breathing, timestamp, target_id, confidence }`  
   - Surfaces in `field_live.py` event log + optional DM pending alert  

**Phase 2 (needs field validation):** Train lightweight classifier on WiFall-format data exported from AURA field captures — **not** copy RS2002 weights.

---

### C.5 Localization: 2D improvements and 3D feasibility

**Informed by:** wifi-densepose-mat `Triangulator` + `DepthEstimator`; spatial-ai multistatic fusion; AURA `hardware_localize.py`.

#### 2D (feasible with 4–5 ESP32 nodes)

- Keep corner-based CSI AoA + multinode fusion (current)  
- Add **RSSI trilateration seed** per target before CSI refine (already partial)  
- Add **subcarrier importance weighting** before AoA (spatial-ai)  
- Add **Kalman filter** on fused position (replace pure EMA in `FieldTracker` for position only)  
- Expected improvement: **0.5–1.5 m typical error** in 10 m cell (needs field validation)

#### 3D / depth-through-rubble

| Question | Assessment |
|----------|------------|
| Minimum nodes for 3D? | Literature and MAT docs assume **≥3 coplanar + height diversity** or **≥4 non-coplanar** anchors. Corner nodes at **same height** give weak Z observability |
| With 4 corner ESP32 on ground? | **2D strong, Z weak** — depth is **needs field validation** |
| MAT depth model on ESP32? | Material attenuation model is **not transferable without calibration** per rubble type |
| AURA proposal | Ship **2D XY** as primary; optional **depth band** `{surface, shallow (<1m), deep (>1m)}` as **low-confidence heuristic** from RSSI loss + multipath spread — label clearly as estimate |

**Do not claim sub-meter 3D through rubble on ESP32 without measured benchmarks.**

---

### C.6 MQTT output (optional, offline-local)

**Informed by:** spatial-ai MQTT / Home Assistant integration pattern.

**Design:**

- New module: `disaster_alert/notify/mqtt_bridge.py` (or `tools/mqtt_bridge.py`)  
- Publishes to **local Mosquitto** on laptop (`localhost:1883`) — no cloud broker required  
- Topics (example):

```text
aura/sensing/zone/{id}/count          → JSON { count, timestamp }
aura/sensing/target/{id}/position     → JSON { x_m, y_m, confidence }
aura/sensing/target/{id}/vitals       → JSON { resp_bpm, hr_bpm, confidence }
aura/sensing/target/{id}/triage       → JSON { suggested: "immediate", confidence }
aura/sensing/events/fall              → JSON { target_id, timestamp, confidence }
```

- **Disabled by default** (`hardware.mqtt_enabled: false`)  
- **Never auto-publish triage as fact** — prefix with `suggested_`  
- Does not replace DM approval for public alerts

---

### C.7 Firmware alignment (minimal, optional phase)

**Informed by:** esp-csi gain compensation and CSI config best practices.

Optional firmware v2 (non-blocking for sensing_v2 laptop path):

- Record `agc_gain` / `fft_gain` in AURA header (extend `aura_protocol.h` v2 — backward compatible)  
- Align CSI config with esp-csi recommendations (LTF merge, HT20) — already largely done in `aura_rx/main.c`  
- Optional on-node **presence GPIO** using esp_wifi_sensing for LED pre-alert — does not replace laptop fusion

---

### C.8 Simulation path parity

WiMANS simulation (`pipeline.py`) should consume the same `sensing_v2` modules where possible, with adapter for 30 SC / 1000 Hz data. Keeps demo and field algorithm aligned.

---

## D. Honesty check — needs field validation

| Capability | ESP32 @ ~20 Hz SISO | Confidence | Notes |
|------------|---------------------|------------|-------|
| Presence / motion (multinode) | Feasible | **Medium–High** | Core AURA use case; tune per site |
| 2D XY (4 corners, 10 m) | Feasible | **Medium** | 0.5–2.5 m realistic |
| People count 1–4 | Feasible | **Medium** | Heuristic; cap at 8 fused |
| People count >4 with positions | Weak | **Low** | Count may exceed localized tracks |
| Respiration BPM | Feasible when still | **Medium** | ±2–4 BPM at 5–10 s window |
| Heartbeat BPM | Difficult | **Low** | Needs long still window; often unreliable at 20 Hz |
| Fall detection (heuristic) | Possible | **Low–Medium** | High false positive risk in rubble |
| Fall detection (trained, WiFall-style) | Possible | **Medium** after AURA-specific training |
| 17-keypoint pose | Unlikely without ML + GPU | **Low** on laptop CPU at 20 Hz | spatial-ai uses trained NN — **needs field validation** on AURA CSI |
| 3D position / rubble depth | Weak with 4 coplanar nodes | **Low** | Do not demo as solved |
| Through-wall max range | Environment-dependent | **Low–Medium** | Debris type dominates |
| START triage automation | Suggest only | **Medium** for routing; **not** medical diagnosis | Operator must approve |
| Deceased detection via CSI | Not reliable | **Very Low** | Never auto-Black tag |

**Intel 5300 / Atheros techniques that do NOT transfer directly:**

- MIMO spatial multiplexing gains  
- 30+ subcarrier stable phase at 1 kHz+  
- Research-grade antenna arrays  
- WiMANS-exact annotation counts in live field  

---

## E. Prioritized implementation order

| Priority | Work item | Rationale | Depends on |
|----------|-----------|-----------|------------|
| **P0** | `sensing_v2/preprocess.py` — AGC gain + subcarrier weights | Foundational SNR improvement (esp-csi, spatial-ai) | None |
| **P0** | `sensing_v2/motion.py` — debounce FSM + wander/jitter features | Reduces false positives (esp-csi, spatial-ai) | P0 preprocess |
| **P0** | Wire `sensing_v2` behind `hardware.sensing_engine: v2` flag | Safe rollout | P0 modules |
| **P1** | `sensing_v2/vitals_ensemble.py` | Better resp; honest HR confidence (MAT, spatial-ai) | P0 |
| **P1** | `sensing_v2/events.py` — fall/collapse heuristic | Rescue differentiator (WiFall, spatial-ai) | P0 motion |
| **P1** | `field_live.py` — show events, vitals confidence, triage badge | Operator visibility | P1 modules |
| **P2** | `sensing_v2/triage.py` + `dm_bridge.py` → pending queue only | START + human approval (MAT ADR-001) | P1 vitals + events |
| **P2** | Kalman position filter in tracker | Smoother 2D tracks (MAT fusion) | P0 localize |
| **P2** | Optional depth band heuristic (surface/shallow/deep) | MAT-inspired; label as estimate | P1 |
| **P3** | `mqtt_bridge.py` local broker | Dispatch interoperability (spatial-ai) | P1 outputs |
| **P3** | Collect AURA field dataset + WiFall-format exporter | Training foundation | Field tests |
| **P4** | Tiny fall classifier (sklearn/TFLite) trained on AURA+WiFall | Better fall accuracy (RS2002) | P3 dataset |
| **P4** | Firmware header v2 for gain fields | esp-csi alignment | Hardware flash |
| **Deferred** | 17-keypoint pose NN | High cost, low ESP32 CSI fit | Large labeled dataset |
| **Deferred** | Full Rust server migration | Breaks AURA integration | N/A — not recommended |

**Estimated scope (engineering complexity, not calendar time):**

- P0–P1: Core engine upgrade — moderate invasive change to `hardware_sensing.py` call chain  
- P2: Product integration — DM UI + bridge  
- P3–P4: Interop + ML — optional follow-ons  

---

## F. Configuration additions (proposed)

```yaml
hardware:
  sensing_engine: v2          # v1 = current, v2 = sensing_v2 package
  sensing_v2:
    gain_compensation: true
    subcarrier_weighting: true
    motion_debounce_frames: 3
    vitals_ensemble: true
    fall_detection: true
    triage_suggestions: true
    depth_band_estimate: false  # enable only after field validation
  mqtt:
    enabled: false
    broker: "mqtt://127.0.0.1:1883"
    topic_prefix: "aura/sensing"
  dm_bridge:
    enabled: false            # enqueue suggested triage to pending queue
    min_confidence: 0.55
```

---

## G. Testing strategy (design)

| Layer | Method |
|-------|--------|
| Unit | Synthetic CSI injectors with known sine motion + resp |
| Regression | Extend `simulation/tests/test_hardware_accuracy.py` for ensemble + triage mapping |
| Replay | Recorded ESP32 UDP captures (`tools/record_session.py`) played into `LiveFieldEngine` |
| Field | Empty-room cal → 1 walker → 2 walkers → still vitals → scripted fall (mattress) |
| SIH demo | WiMANS simulation for annotation truth + field_live for hardware |

---

## H. What we are NOT doing

- Copying Rust code from spatial-ai / wifi-densepose into AURA  
- Replacing AURA firmware with spatial-ai ESP32-S3 firmware  
- Auto-publishing survivor alerts without DM approval  
- Claiming medical-grade triage or deceased detection from CSI alone  
- Cloud-dependent inference or model hosting  

---

## References

| Project | URL | License | Notes |
|---------|-----|---------|-------|
| **AURA** (this repo) | https://github.com/iam-pradeepkumar/AURA | *(verify LICENSE in repo)* | Baseline system |
| **wifi-densepose / RuView** | https://github.com/ruvnet/ruview | **MIT** | wifi-densepose-mat, ADR-001 |
| **wifi-densepose-mat docs** | https://docs.rs/wifi-densepose-mat | **MIT** (crate) | MAT API reference |
| **xnetsc/wifi-densepose** | https://github.com/xnetsc/wifi-densepose | **MIT** (expected same lineage) | User-cited fork; verify LICENSE on clone |
| **spatial-ai (RescueSense)** | https://github.com/arjxnt/spatial-ai | **MIT** | Based on RuView; Rust server |
| **ESP32-Realtime-System** | https://github.com/RS2002/ESP32-Realtime-System | **Unknown — no LICENSE found** | Do not copy code until confirmed |
| **WiFall dataset** | https://huggingface.co/datasets/RS2002/WiFall | Dataset terms on HF | ESP32-S3 CSI falls |
| **CSI-BERT2** | https://github.com/RS2002/CSI-BERT2 | *(verify LICENSE)* | Related RS2002 research |
| **espressif/esp-csi** | https://github.com/espressif/esp-csi | **Apache-2.0** | Gain comp, esp-radar, esp_wifi_sensing |
| **esp_wifi_sensing component** | https://components.espressif.com/components/espressif/esp_wifi_sensing | **Apache-2.0** | On-device FSM reference |

---

## Approval checklist (for maintainers)

Before implementation starts, confirm:

- [ ] Accept `sensing_v2/` package approach vs monolithic edit  
- [ ] Accept START suggestions → DM **pending** only (no auto-broadcast)  
- [ ] Accept 2D-primary localization; defer 3D claims  
- [ ] Accept MQTT as optional P3  
- [ ] Prioritize P0–P1 for SIH field demo vs P2+ post-demo  

---

*Document version: 1.0 — 2026-09-26. For questions, see `docs/HARDWARE_FIELD_DEPLOYMENT.md` and `simulation/aura_processor/hardware_live.py`.*
