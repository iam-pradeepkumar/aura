# AURA Disaster SAR in NVIDIA Isaac Sim + Isaac Lab

This document describes how to evolve the current **kinematic dashboard sim** and **Gazebo ROS 2 stack** into a **photorealistic disaster environment** with spiderbots and drones in **NVIDIA Isaac Sim**, trained/orchestrated with **Isaac Lab**, while keeping the **same AURA dashboard** and `aura_processor` CSI pipeline.

## Target architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  AURA Dashboard (existing)                                       │
│  geocode → polygon → place survivors → start mission             │
│  WebSocket /ws/command ← same command_sensing schema             │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP start + YAML active_mission
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Isaac Bridge Node (new ROS 2 package: aura_isaac_bridge)        │
│  - reads active_mission.yaml (zone, survivors, units)            │
│  - spawns USD robots + rubble scene                              │
│  - publishes /aura/unit_pose, /aura/csi_packets                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ ROS 2 topics
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Isaac Sim 4.x + Isaac Lab                                       │
│  - Disaster USD stage (collapsible building, rubble, victims)      │
│  - Spiderbot articulation (wheeled / legged)                     │
│  - Quadrotor drone                                               │
│  - RTX sensors optional (camera, lidar) — CSI still faked        │
└────────────────────────────┬────────────────────────────────────┘
                             │ fake CSI + positions
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  aura_processor mobile_field (existing — no fork)                │
│  sensing_v2 → fusion → survivors on map                          │
└─────────────────────────────────────────────────────────────────┘
```

**Principle:** Isaac replaces **physics + visuals + odometry**; AURA keeps **mission logic, CSI model, processor, dashboard**.

---

## Phase 1 — Workstation setup (Ubuntu 22.04)

### Hardware
- NVIDIA RTX GPU (3060+; 4080+ recommended)
- 32 GB RAM, 100 GB free disk
- Driver ≥ 535, CUDA 12.x

### Install Isaac Sim
1. Install [Omniverse Launcher](https://www.nvidia.com/en-us/omniverse/) or use NGC container.
2. Install **Isaac Sim 4.2+** from Exchange.
3. Verify: `./isaac-sim.sh` opens the app.

### Install Isaac Lab
```bash
git clone https://github.com/isaac-sim/IsaacLab.git
cd IsaacLab
./isaaclab.sh --install
```

Isaac Lab provides RL/env templates, articulation controllers, and multi-agent scenes — use it for **policy training** and **standardized robot APIs**, not to replace the dashboard.

### ROS 2 bridge
Isaac Sim ships **ROS 2 Humble** bridge extension:
- Enable `isaacsim.ros2.bridge` in Extension Manager.
- Publish `geometry_msgs/PoseStamped`, `nav_msgs/Odometry`, `sensor_msgs/Image`.

---

## Phase 2 — Disaster environment (USD stage)

### 2.1 Scene composition
Create `isaac_sim/assets/disaster_zone.usd`:

| Layer | Content | Notes |
|-------|---------|-------|
| Ground | DEM or flat plane + debris materials | Match `area_size_m` from mission YAML |
| Structures | Damaged building facades, collapsed walls | NVIDIA assets or KitBash |
| Obstacles | Rubble piles as static colliders | Map from `obstacles: [x,y,r]` in YAML |
| Victims | Human mannequins (static) | Positions from `survivors_geo` / local `victims` |
| Lighting | Overcast HDRI | Consistent RTX shadows |

### 2.2 Geo anchoring (same as dashboard)
Reuse `gazebo_sim/aura_sim_core/geo.py`:
- Dashboard sends `zone_polygon_geo` + `survivors_geo`.
- Bridge converts to Isaac world frame (meters, Z-up).
- Spawn zone boundary as debug mesh (yellow) matching map polygon.

### 2.3 Procedural option (Isaac Lab)
Isaac Lab `InteractiveScene` can randomize:
- Rubble count / layout inside polygon
- Victim positions (seeded from admin-placed survivors)
- Smoke/dust particles (visual only)

Keep **admin-placed survivors** as ground truth — randomization only adds clutter, not victim count.

---

## Phase 3 — Robot assets

### Spiderbot (ground CSI node)
**Option A — Wheeled rover (faster)**
- Base: Carter / Jetbot USD + custom mesh
- Physics: `WheeledRobot` articulation
- Controller: differential drive velocity commands

**Option B — Legged spider (showcase)**
- Unitree Go2 or custom quadruped USD
- Isaac Lab locomotion policy (pre-trained) + waypoint follower
- Slower but dramatic for demos

CSI is **not simulated in RF** — attach a virtual `csi_link` frame; bridge calls `FakeCsiGenerator` from `aura_sim_core` using rover `(x,y)` and velocity.

### Drone (coverage)
- Quadrotor USD (Crazyflie or 3DR Iris mesh)
- `Multirotor` or thrust-based articulation
- Isaac Lab trajectory tracking → lawnmower waypoints from `CoveragePlanner.drone_lawnmower()`

### Spawn from mission roster
```yaml
units:
  - {id: spider-01, type: spiderbot, node_id: 1}
  - {id: drone-alpha, type: drone, node_id: 2}
```
Bridge spawns one articulation per enabled unit at polygon centroid + offsets (same as `MobileMissionController._init_units`).

---

## Phase 4 — ROS 2 packages (new)

Suggested layout under `gazebo_sim/` (parallel to existing `ros_ws`):

```
isaac_sim/
  assets/           # USD, textures, robots
  ros_ws/
    src/
      aura_isaac_bridge/     # mission YAML → spawn + telemetry
      aura_isaac_teleop/     # optional manual override
  scripts/
    launch_isaac_mission.py  # Isaac Lab env entry
```

### `aura_isaac_bridge` responsibilities
1. Subscribe `/aura/mission_start` (or watch `active_mission.yaml`).
2. Call Isaac Sim Python API to load stage + spawn robots.
3. Run patrol FSM — **reuse `MobileMissionController`** from `aura_sim_core` (same as dashboard kinematic sim).
4. Step physics; read poses; feed `FakeCsiGenerator` → `MobileFieldEngine`.
5. Publish `command_sensing` JSON on `/aura/telemetry` (or run existing `ws_bridge_server.py`).

This avoids rewriting mission logic in Isaac — Isaac only provides **poses and visuals**.

---

## Phase 5 — Isaac Lab integration

Use Isaac Lab for:

| Task | Isaac Lab module |
|------|------------------|
| Legged spider locomotion | `isaaclab.envs.ManagerBasedRLEnv` + locomotion template |
| Drone waypoint follow | `isaaclab.controllers` / custom PD to waypoints |
| Multi-agent patrol | `DirectMARLEnv` with 1 spider + 1 drone |
| Domain randomization | Rubble friction, lighting, sensor noise |

**Training** (optional): RL policy for obstacle avoidance inside polygon; export ONNX → run in bridge as velocity command.

**Demo path** (recommended first): No RL — kinematic waypoint follower inside Isaac (same math as `GroundRover.step_toward`) applied to articulation root — matches dashboard speeds after `sim_tuning.py`.

---

## Phase 6 — Dashboard integration

1. Add operation mode **Isaac Sim** (alongside Simulation / Gazebo / Live HW).
2. `POST /api/command/start` with `mode: "isaac"` writes `active_mission.yaml` and POSTs to Isaac bridge REST endpoint (or ROS service).
3. WebSocket unchanged — same `command_sensing` messages.
4. Map markers use the same `lat/lon` enrichment from `GeoAnchor`.

---

## Phase 7 — Suggested build order

1. **Static disaster USD** — empty zone, manual camera fly-through.
2. **YAML → spawn victims** as mannequins at `victims[]` local coords.
3. **Single wheeled spider** — waypoint patrol in Isaac, poses to ROS.
4. **Wire fake CSI + aura_processor** — survivor turns red on map.
5. **Add drone** — lawnmower path, green marker.
6. **Replace Gazebo launch** with Isaac launch for demos.
7. **Isaac Lab RL** — optional legged locomotion polish.

---

## Honest scope notes

| Real in Isaac | Still faked (same as today) |
|---------------|----------------------------|
| Physics, collisions, visuals | WiFi CSI RF propagation |
| Robot articulation / cameras | Medical triage accuracy |
| RTX lidar/camera (optional) | ESP32 hardware packets |

---

## References

- [Isaac Sim documentation](https://docs.isaacsim.omniverse.nvidia.com/)
- [Isaac Lab](https://isaac-sim.github.io/IsaacLab/)
- [Isaac ROS](https://nvidia-isaac-ros.github.io/)
- AURA existing: `gazebo_sim/aura_sim_core/`, `GAZEBO_UBUNTU.md`, `WEBSOCKET_SCHEMA.md`

---

## Next repo tasks (when you start implementation)

1. Create `isaac_sim/assets/disaster_zone.usd` placeholder.
2. Add `aura_isaac_bridge` ROS 2 package wrapping `MobileMissionController`.
3. Dashboard chip: **Isaac Sim** mode → `mode: "isaac"` in start API.
4. Document GPU + Isaac Sim version in `ISAAC_SIM.md` header once pinned.
