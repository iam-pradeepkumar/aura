"""Launch AURA mobile SAR — Gazebo + planner + behavior + fake CSI + WS relay."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os


def generate_launch_description():
    pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    zone_default = os.path.join(pkg_root, "config", "active_mission.yaml")
    if not os.path.isfile(zone_default):
        zone_default = os.path.join(pkg_root, "config", "disaster_zone.yaml")
    aura_cfg = os.path.abspath(os.path.join(pkg_root, "..", "..", "simulation", "config.yaml"))
    world_sdf = os.path.join(pkg_root, "worlds", "disaster_zone.sdf")
    ws_bridge = os.path.join(pkg_root, "standalone", "ws_bridge_server.py")
    spawn_rover = os.path.join(pkg_root, "scripts", "spawn_rover.sh")
    spawn_drone = os.path.join(pkg_root, "scripts", "spawn_drone.sh")

    zone = LaunchConfiguration("zone_config")
    aura = LaunchConfiguration("aura_config")
    use_gazebo = LaunchConfiguration("use_gazebo")

    planner = Node(
        package="aura_coverage_planner",
        executable="planner_node",
        name="aura_coverage_planner",
        parameters=[{"zone_config": zone}],
        output="screen",
    )

    behavior = TimerAction(
        period=2.0,
        actions=[
            Node(
                package="aura_robot_behavior",
                executable="behavior_node",
                name="aura_robot_behavior",
                parameters=[{"zone_config": zone}],
                output="screen",
            )
        ],
    )

    fake_csi = TimerAction(
        period=3.0,
        actions=[
            Node(
                package="aura_fake_csi",
                executable="fake_csi_node",
                name="aura_fake_csi",
                parameters=[{"zone_config": zone, "aura_config": aura}],
                output="screen",
            )
        ],
    )

    ws = ExecuteProcess(
        cmd=["python3", ws_bridge, "--port", "8766", "--ros-topic"],
        output="screen",
    )

    gazebo = ExecuteProcess(
        cmd=["gz", "sim", "-r", world_sdf],
        output="screen",
        condition=IfCondition(use_gazebo),
    )

    spawn_r = ExecuteProcess(
        cmd=["bash", spawn_rover],
        output="screen",
        condition=IfCondition(use_gazebo),
    )

    spawn_d = ExecuteProcess(
        cmd=["bash", spawn_drone],
        output="screen",
        condition=IfCondition(use_gazebo),
    )

    return LaunchDescription([
        DeclareLaunchArgument("use_gazebo", default_value="true"),
        DeclareLaunchArgument("zone_config", default_value=zone_default),
        DeclareLaunchArgument("aura_config", default_value=aura_cfg),
        gazebo,
        TimerAction(period=5.0, actions=[spawn_r, spawn_d], condition=IfCondition(use_gazebo)),
        planner,
        behavior,
        fake_csi,
        ws,
    ])
