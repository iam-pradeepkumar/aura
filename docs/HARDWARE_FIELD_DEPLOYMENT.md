# AURA Hardware Field Deployment — Step by Step

Complete guide to deploy **5 ESP32 boards** (1 TX + 4 RX at corners), detect people with **all sensing functions**, and view **live tracking with motion trails** on your laptop.

> Simulation (WiMANS upload) is separate and unchanged. This guide is **hardware only**.

---

## What you will get

| Function | Live output |
|----------|-------------|
| **Motion detection** | YES/NO on dashboard |
| **People count** | Fused count from 4 corner nodes |
| **Localization** | XY position on 10 m map |
| **Tracking** | Stable person IDs with **motion trails** |
| **Vitals** | Respiration + heartbeat BPM and waveforms |
| **Events** | "Target detected", "started moving", "stopped" |

**Two ways to view results:**
1. **Web dashboard** — browser map with trails (recommended)
2. **Matplotlib animation** — `python tools/field_live.py` with animated trails

---

## Your 5 ESP32 boards

| Board | Role | Firmware | NODE_ID |
|-------|------|----------|---------|
| Board A | **TX** probe | `firmware/aura_tx` | — |
| Board B | **RX** corner SW | `firmware/aura_rx` | **1** |
| Board C | **RX** corner SE | `firmware/aura_rx` | **2** |
| Board D | **RX** corner NE | `firmware/aura_rx` | **3** |
| Board E | **RX** corner NW | `firmware/aura_rx` | **4** |

---

## Phase 1 — Software on laptop (one time)

### Step 1.1 — Clone and install

```bash
git clone https://github.com/iam-pradeepkumar/aura.git
cd aura
pip install -r simulation/requirements.txt
pip install -r dashboard/requirements.txt
```

### Step 1.2 — Install ESP-IDF v5.1+

```bash
git clone -b v5.1.4 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf && ./install.sh esp32,esp32c6
. ./export.sh
idf.py --version   # should print v5.1.x
```

Run `. ./export.sh` in every new terminal before flashing.

### Step 1.3 — Configure search area

Edit `simulation/config.yaml` with your **measured** corner positions (meters):

```yaml
area_size_m: 10.0
motion_threshold: 0.02
max_people: 8

node_positions:
  1: [0.0, 0.0]      # Board B — southwest corner
  2: [10.0, 0.0]     # Board C — southeast
  3: [10.0, 10.0]    # Board D — northeast
  4: [0.0, 10.0]     # Board E — northwest

tx_position: [5.0, -2.0]   # Board A — outside south edge

hardware:
  min_packets: 80
  window_packets: 200
  refresh_every: 40
  motion_threshold_scale: 0.85
  link_timeout_sec: 5.0
  trail_length: 80
```

If your area is not exactly 10×10 m, scale the numbers proportionally.

---

## Phase 2 — Flash all 5 boards

### Step 2.1 — Flash TX (Board A)

```bash
cd aura/firmware/aura_tx
idf.py set-target esp32c6    # use esp32 if not C6
idf.py build flash -p /dev/ttyUSB0 monitor
```

**Windows:** use `COM3` instead of `/dev/ttyUSB0`.

Expected log: `AURA probe transmitter running`

Press `Ctrl+]` to exit monitor. Label board **TX**.

### Step 2.2 — Flash RX nodes (Boards B–E)

Repeat for each board with a **unique NODE_ID** (flash **one board at a time** on the same USB port):

```bash
cd ~/aura
git pull

. ~/esp/esp-idf/export.sh
cd ~/aura/firmware/aura_rx
idf.py set-target esp32    # use esp32c6 if you have C6 boards

# Board B — southwest (node 1)
AURA_NODE_ID=1 idf.py -b 115200 build flash -p /dev/ttyUSB0

# Board C — southeast (node 2)
AURA_NODE_ID=2 idf.py -b 115200 build flash -p /dev/ttyUSB0

# Board D — northeast (node 3)
AURA_NODE_ID=3 idf.py -b 115200 build flash -p /dev/ttyUSB0

# Board E — northwest (node 4)
AURA_NODE_ID=4 idf.py -b 115200 build flash -p /dev/ttyUSB0
```

> **Note:** Use the `AURA_NODE_ID=N` environment variable — **not** `-D CONFIG_AURA_NODE_ID=N` (CMake ignores that flag). Use `-b 115200` on classic ESP32 if flash fails at higher baud. Hold **BOOT** while connecting if you see `No serial data received`.

Label each board with permanent marker: **RX-1**, **RX-2**, **RX-3**, **RX-4**.

### Step 2.3 — Attach external antennas

Screw **external 2.4 GHz antennas** onto all 5 boards before field deployment. PCB antennas are too weak outdoors.

---

## Phase 3 — Physical placement

### Layout (top view)

```
     RX-4 (0,10) ─────────────── RX-3 (10,10)
          │                            │
          │      [  SEARCH AREA  ]     │
          │      walk here to test     │
          │                            │
     RX-1 (0,0) ──────────────── RX-2 (10,0)

              TX (5, -2)  ← 2 m south of center
```

### Placement checklist

- [ ] Mount each RX at **1–2 m height** on tripod or pole
- [ ] RX antennas **vertical**
- [ ] Measure corner positions → update `config.yaml`
- [ ] Place **TX** outside the square, 1–3 m from nearest RX
- [ ] Connect all boards to **USB power banks** (10,000 mAh+)
- [ ] Keep laptop inside vehicle or command post with hotspot

---

## Phase 4 — Laptop hotspot

### Step 4.1 — Create hotspot

| Setting | Value |
|---------|-------|
| SSID | `AURA_HUB` |
| Password | `aura2026` |
| Band | **2.4 GHz** (required for ESP32) |
| Gateway IP | `192.168.4.1` (note yours if different) |

**Linux example:**
```bash
# Verify gateway after starting hotspot
ip route | grep default
```

If gateway is not `192.168.4.1`, edit `firmware/common/aura_protocol.h`:
```c
#define AURA_HUB_IP "192.168.137.1"   // your actual gateway
```
Re-flash all 4 RX boards.

### Step 4.2 — Allow UDP port 5555

```bash
# Linux ufw example
sudo ufw allow 5555/udp
```

Windows: allow Python through firewall when prompted.

---

## Phase 5 — Power on sequence

**Order matters:**

1. ✅ Laptop hotspot **ON** (`AURA_HUB`)
2. ✅ Start dashboard (Step 6) — click **Start Live**
3. ✅ Power **TX** board (Board A)
4. ✅ Power **RX-1** (wait 5 s)
5. ✅ Power **RX-2** (wait 5 s)
6. ✅ Power **RX-3** (wait 5 s)
7. ✅ Power **RX-4**

Each RX joins WiFi and streams CSI at ~20 Hz. First detection needs **~4–10 seconds** of buffering per node.

---

## Phase 6 — View results on laptop dashboard

### Step 6.1 — Start dashboard

```bash
cd aura
python dashboard/run.py --port 8848
```

Open browser: **http://127.0.0.1:8848**

### Step 6.2 — Start live hardware

1. Click **Live Hardware** tab
2. Click **Start Live**
3. Status should change to **Live**

### Step 6.3 — Read the panels

| Panel | What to look for |
|-------|------------------|
| **Nodes** | 4 nodes → `active`, packet rate ~15–20 Hz, RSSI > -70 dBm |
| **Count** | Number of people detected |
| **Motion** | YES when someone moves in search area |
| **Live Map (trails)** | Red dots = moving, colored **trail lines** = path history |
| **Targets** | Per-person XY, velocity (m/s), respiration, heartbeat |
| **Respiration / Heartbeat** | Live waveforms for selected person |
| **Events** | "Target 1 detected", "started moving", etc. |

Click a **person on the map** or in the Targets list to view their individual vitals.

### Step 6.4 — Test walk-through

1. Stand in center of search area → count should show **1**
2. Walk slowly from corner to corner → **trail line** follows you on map
3. Stop moving → marker changes to static (triangle), velocity drops
4. Two people walk different paths → **two trails**, count = 2

---

## Phase 7 — Matplotlib animation (optional)

For a dedicated full-screen map with animated trails:

```bash
cd aura
python tools/field_live.py
```

Shows:
- Corner nodes (blue squares)
- Moving survivors with **colored trail lines**
- Live people count
- Respiration waveform
- Per-node link status

Press `Ctrl+C` to quit.

---

## Phase 8 — Verify all sensing functions

| Test | Action | Expected result |
|------|--------|-----------------|
| Motion | Wave arms in center | Motion = YES |
| Count | 1 person stands still | Count = 1 |
| Count | 2 people in area | Count = 2 |
| Localization | Stand at known corner | XY near that corner on map |
| Tracking | Walk across area | Trail line follows path |
| Vitals | Stand still 15+ s | Respiration 8–25 BPM appears |
| Multinode | Walk near RX-1 only | Position biased toward that corner, fused globally |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| 0 nodes active | Hotspot on? SSID/password correct? Re-power RX boards |
| Buffering forever | Power TX first; check external antenna |
| Count always 0 | Walk in center; wait 10 s; lower `motion_threshold` in config |
| Trails not showing | Click **Start Live** again; walk continuously for 5+ s |
| Wrong positions | Re-measure corners; update `node_positions` in config.yaml |
| Weak link / low Hz | Move laptop closer; reduce obstacles to hotspot |
| Only 1 node works | Each RX must have unique NODE_ID (1–4) |
| Dashboard old version | `git pull` → check `/api/version` shows `2026.08.31-27+` |

---

## Quick reference card

```
HOTSPOT:  AURA_HUB / aura2026
UDP:      port 5555
DASH:     python dashboard/run.py --port 8848
CLI:      python tools/field_live.py
CONFIG:   simulation/config.yaml
FLASH TX: firmware/aura_tx
FLASH RX: AURA_NODE_ID=1..4 idf.py -b 115200 build flash -p /dev/ttyUSB0
```

---

## Safety

- AURA is **not certified** life-detection equipment
- Use with standard SAR procedures (acoustic, canine, thermal)
- Get RF authorization in disaster zones where required

---

## Related docs

- [HARDWARE_SETUP.md](HARDWARE_SETUP.md) — components and protocol details
- [WIRELESS_AND_SIMULATION.md](WIRELESS_AND_SIMULATION.md) — technical reference
- [BENCHMARKS.md](BENCHMARKS.md) — expected accuracy
