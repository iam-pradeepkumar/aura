# Gazebo + ROS 2 on Ubuntu (AURA mobile SAR)

This guide installs **ROS 2 Humble** and **Gazebo Garden** on Ubuntu 22.04, then runs the AURA mobile search-and-rescue stack with the dashboard.

## 1. System prerequisites

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
  git curl wget gnupg lsb-release software-properties-common \
  python3-pip python3-venv build-essential cmake
```

## 2. Install ROS 2 Humble

```bash
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
  http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt update
sudo apt install -y ros-humble-desktop ros-dev-tools
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source /opt/ros/humble/setup.bash
```

## 3. Install Gazebo Garden

```bash
sudo wget https://packages.osrfoundation.org/gazebo.gpg \
  -O /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] \
  http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
sudo apt update
sudo apt install -y gz-garden
```

Verify:

```bash
gz sim --version
ros2 --help
```

## 4. Clone / open the AURA project

```bash
cd ~
git clone <your-aura-repo-url> aura
cd aura
```

## 5. Python dependencies (dashboard + simulation)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r dashboard/requirements.txt -r simulation/requirements.txt
```

Set mobile mode in `simulation/config.yaml`:

```yaml
hardware:
  mode: mobile
```

## 6. Build ROS workspace

```bash
cd gazebo_sim/ros_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y   # may skip optional deps
colcon build --symlink-install
source install/setup.bash
```

Export Gazebo model path (required for AURA rover/drone models):

```bash
export GZ_SIM_RESOURCE_PATH="$(pwd)/../../models:${GZ_SIM_RESOURCE_PATH}"
```

Add both lines to `~/.bashrc` for future shells.

## 7. Run — kinematic simulation (no Gazebo)

Fastest way to validate the full dashboard flow:

```bash
cd ~/aura
source .venv/bin/activate
python3 gazebo_sim/standalone/verify_build_steps.py
python3 dashboard/run.py --port 8847
```

Open **http://127.0.0.1:8847/**

1. Search a real address (e.g. your city block)
2. **Mark disaster zone** → click corners → **Close polygon**
3. **Place survivors** → click inside the yellow zone (at least one)
4. **Units** tab → enable Spider-01 + Drone-Alpha
5. **START RESCUE** (Simulation mode)

Spiderbots (blue) lawnmower-patrol the full zone; drones (green) cover from above. Survivors turn red when CSI-gated detection confirms them.

## 8. Run — Gazebo + ROS 2

Terminal A — dashboard (writes `gazebo_sim/config/active_mission.yaml` when you start a geo mission):

```bash
cd ~/aura && source .venv/bin/activate
python3 dashboard/run.py --port 8847
```

Terminal B — ROS/Gazebo stack:

```bash
cd ~/aura/gazebo_sim/ros_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
export GZ_SIM_RESOURCE_PATH="$(pwd)/../models:${GZ_SIM_RESOURCE_PATH}"
ros2 launch aura_bringup mobile_mission.launch.py use_gazebo:=true
```

In the dashboard, choose **Gazebo** mode before **START RESCUE**. The launch file reads `active_mission.yaml` for zone + survivors.

Optional standalone WebSocket bridge (without full ROS graph):

```bash
python3 gazebo_sim/standalone/ws_bridge_server.py --port 8766
```

## 9. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `gz: command not found` | Re-install `gz-garden`; open a new shell |
| Models missing in Gazebo | Set `GZ_SIM_RESOURCE_PATH` to `gazebo_sim/models` |
| Dashboard port in use | `python3 dashboard/run.py --port 8848` |
| No survivors detected | Place survivors inside closed polygon; wait for spiderbot to slow/hold near them (~10–20 s) |
| Units not moving | Hard-refresh dashboard (`Ctrl+Shift+R`); ensure zone has 3+ corners and mission is Simulation mode |
| `colcon build` fails | `source /opt/ros/humble/setup.bash` first; install missing packages with `rosdep` |

## 10. What is real vs simulated

| Real | Simulated |
|------|-----------|
| `aura_processor` sensing_v2 pipeline | WiFi CSI (distance-to-victim model) |
| Dashboard geocoding + map | RF multipath / rubble |
| Autonomous patrol + hold-for-vitals | Medical triage accuracy |
| Admin-placed survivor positions | GPS/SLAM on real robots |

See [README.md](README.md) and [WEBSOCKET_SCHEMA.md](WEBSOCKET_SCHEMA.md) for architecture details.
