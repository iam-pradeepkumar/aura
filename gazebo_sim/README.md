# AURA Gazebo / ROS 2 Mobile SAR Simulation

Autonomous ground rover + aerial drone patrol a marked disaster zone. CSI is **faked** using a distance-to-victim model and fed into the **real** `aura_processor` `sensing_v2` pipeline (not a parallel rewrite).

## Quick start (no Gazebo — kinematic sim)

```bash
# Verify build steps 1–5
python3 gazebo_sim/standalone/verify_build_steps.py

# Full mission (~3 min)
python3 gazebo_sim/standalone/run_mission.py

# Dashboard live view
python3 dashboard/run.py
# Open http://127.0.0.1:8847/ → assign units, mark zone, Start Rescue
```

## ROS 2 + Gazebo (local machine with ROS 2 Humble + Gazebo Garden)

```bash
cd gazebo_sim/ros_ws
colcon build --symlink-install
source install/setup.bash
ros2 launch aura_bringup mobile_mission.launch.py
```

Set `hardware.mode: mobile` in `simulation/config.yaml` when using this path.

## Packages

| Package | Role |
|---------|------|
| `aura_sim_core/` | Shared Python: world, fake CSI, coverage, mission (no ROS) |
| `aura_world` | SDF world + zone YAML (ament install) |
| `aura_coverage_planner` | Polygon → ground Nav2-style + drone lawnmower paths |
| `aura_robot_behavior` | Autonomous patrol + hold-for-vitals mission FSM |
| `aura_fake_csi` | Distance-to-victim CSI → real `aura_processor` pipeline |
| `aura_mobile_bridge` | Integrated mission+CSI node (standalone `ros2 run`) |
| `aura_bringup` | One launch: planner + behavior + fake CSI + WS relay (+ optional Gazebo) |
| `standalone/` | Kinematic sim, verify script, WebSocket bridge |

## What this simulates vs. what it fakes

| Simulated | Faked / simplified |
|-----------|-------------------|
| Autonomous patrol + hold-for-vitals behavior | Real WiFi CSI — uses distance-to-victim amplitude/phase model |
| Stationary vitals gating (3 s still before resp modulation in CSI) | Multipath, NLOS, rubble penetration |
| Coverage % from visited grid cells | True RF sensing range |
| START triage suggestions via `sensing_v2` | Medical triage accuracy |
| 2D obstacle avoidance (greedy Nav2 stand-in) | Full Nav2 costmaps + SLAM |
| Drone lawnmower aerial coverage | Real drone dynamics / wind |
| Ground-truth odometry + noise | GPS, SLAM, or Intel 5300 hardware |
| Single ground CSI node (rover) | Four static corner receivers |
| Drone = coverage metric + relay only (no vitals CSI) | Mesh networking |

## WebSocket schema

See [WEBSOCKET_SCHEMA.md](WEBSOCKET_SCHEMA.md).

## Integration with aura_processor

- **Reused:** `sensing_v2` preprocess, motion FSM, ensemble vitals, Kalman tracker, fusion, triage enricher
- **New:** `mobile_field.py`, `synthetic_receiver.py`, `mobile_positions.py`, `gazebo_sim/aura_sim_core/*`
- **Refactored:** `NodePipelineState` reads runtime positions via `NodePositionStore`

## Build verification order

1. Ground rover → hardcoded waypoint (`verify_build_steps.py` step 1)
2. Fake CSI → aura_processor (`step 2`)
3. Polygon coverage planner (`step 3`)
4. Drone waypoints (`step 4`)
5. Full mission (`step 5`)
