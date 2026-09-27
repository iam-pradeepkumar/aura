# AURA — Adaptive Urban Rescue & Alert Array

**Mobile CSI search & rescue command center** with autonomous spiderbot and drone simulation, plus local paths for live ESP32 hardware and Gazebo / Isaac Sim.

---

## Command Center (main app)

Full-screen satellite map: mark a disaster zone, place survivors, start a mission, and watch units patrol with WiFi CSI homing until survivors are found.

```bash
pip install -r requirements.txt
python3 dashboard/run.py
# → http://127.0.0.1:8847
```

**Demo flow**

1. Search an address → **Locate**
2. **Mark disaster zone** → click corners → **Close polygon**
3. **Place survivors** → click inside the orange zone
4. **Start mission** → spiderbots and drones patrol; red pins appear when survivors are found

---

## Deploy on Render (auto-deploy on push)

This repo includes [`render.yaml`](render.yaml) for [Render](https://render.com).

1. Push to GitHub (`main`).
2. Render Dashboard → **New** → **Blueprint** → select repo → **Apply**.
3. Every future push to `main` redeploys automatically.

Full guide: [`docs/DEPLOY_RENDER.md`](docs/DEPLOY_RENDER.md)

---

## Project layout

```
├── dashboard/              # Command Center (FastAPI + static UI)
│   ├── app.py              # API + WebSocket (Render entrypoint)
│   ├── command_sim.py      # Mission orchestration
│   └── static/command.html # Map UI
├── gazebo_sim/             # Gazebo ROS 2 + Isaac Sim roadmap
│   ├── GAZEBO_UBUNTU.md    # Local Gazebo install
│   └── ISAAC_SIM.md        # NVIDIA Isaac Sim plan
├── simulation/             # CSI processor (aura_processor)
├── tools/                  # Live ESP32 field tools
├── firmware/               # ESP32 TX/RX/alert node
└── disaster_alert/         # Early-warning engine (local / optional)
```

---

## Local hardware (ESP32 CSI)

Live sensing runs on your laptop — not on Render.

```bash
pip install -r simulation/requirements.txt
python3 tools/field_live.py
```

See [`docs/HARDWARE_SETUP.md`](docs/HARDWARE_SETUP.md) and [`docs/HARDWARE_FIELD_DEPLOYMENT.md`](docs/HARDWARE_FIELD_DEPLOYMENT.md).

---

## Gazebo / Isaac Sim (local ROS 2)

- **Gazebo:** [`gazebo_sim/GAZEBO_UBUNTU.md`](gazebo_sim/GAZEBO_UBUNTU.md)
- **Isaac Sim + Isaac Lab:** [`gazebo_sim/ISAAC_SIM.md`](gazebo_sim/ISAAC_SIM.md)

The dashboard simulation engine matches the same mission YAML and WebSocket schema used by the ROS bridge.

---

## Requirements

| Environment | Install |
|-------------|---------|
| Command Center + Render | `pip install -r requirements.txt` |
| Full CSI + WiMANS replay | `pip install -r simulation/requirements.txt` |
| Gazebo ROS 2 | See `gazebo_sim/GAZEBO_UBUNTU.md` |

Python **3.10+** (3.12 recommended for Render).
