"""Launch AURA mobile SAR mission — planner, behavior, fake CSI, optional Gazebo."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os


def _gz_sim(world_path: str):
    return ExecuteProcess(
        cmd=["gz", "sim", "-r", world_path],
        output="screen",
        condition=IfCondition(LaunchConfiguration("use_gazebo")),
    )


def generate_launch_description():
    pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    zone_default = os.path.join(pkg_root, "config", "disaster_zone.yaml")
    aura_cfg = os.path.abspath(os.path.join(pkg_root, "..", "..", "simulation", "config.yaml"))
    world_sdf = os.path.join(pkg_root, "worlds", "disaster_zone.sdf")
    ws_bridge = os.path.join(pkg_root, "standalone", "ws_bridge_server.py")

    zone = LaunchConfiguration("zone_config")
    aura = LaunchConfiguration("aura_config")

    planner = Node(
        package="aura_coverage_planner",
        executable="planner_node",
        name="aura_coverage_planner",
        parameters=[{"zone_config": zone}],
        output="screen",
    )

    behavior = Node(
        package="aura_robot_behavior",
        executable="behavior_node",
        name="aura_robot_behavior",
        parameters=[{"zone_config": zone}],
        output="screen",
    )

    fake_csi = Node(
        package="aura_fake_csi",
        executable="fake_csi_node",
        name="aura_fake_csi",
        parameters=[{"zone_config": zone, "aura_config": aura}],
        output="screen",
    )

    ws = ExecuteProcess(
        cmd=["python3", ws_bridge, "--port", "8766", "--zone", zone_default, "--config", aura_cfg, "--ros-topic"],
        output="screen",
    )

    gazebo = _gz_sim(world_sdf)

    return LaunchDescription([
        DeclareLaunchArgument("use_gazebo", default_value="false"),
        DeclareLaunchArgument("zone_config", default_value=zone_default),
        DeclareLaunchArgument("aura_config", default_value=aura_cfg),
        planner,
        behavior,
        fake_csi,
        ws,
        gazebo,
    ])
