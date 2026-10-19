"""Arm trajectory interface for policy deployment.

Starts a ros2_control_node with mock hardware and joint trajectory controllers
(/arm_controller, /gripper_controller) under the follower namespace. A policy
sends joint-position references to these controllers; they interpolate them,
and the joint_state_broadcaster output is remapped onto the topic the arm
control node forwards to the real arm.
"""

import sys
import tempfile
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace, SetRemap

# Reuse agx_arm_moveit's robot_description builder so the controllers see the
# same URDF as the agx_arm_moveit launch files.
sys.path.insert(0, str(Path(get_package_share_directory("agx_arm_moveit")) / "launch"))
from _moveit_config_builder import build_moveit_config  # noqa: E402


def _build_ros2_controllers_file(arm_type, effector_type, namespace):
    """Write a ros2_controllers config to a temp YAML and return its path.

    Same controller definitions as agx_arm_moveit/config/ros2_controllers.yaml,
    restricted to /arm_controller, /gripper_controller and the
    joint_state_broadcaster.
    """
    arm_joints = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
    if arm_type == "nero":
        arm_joints.append("joint7")

    ns = namespace.strip("/")
    prefix = f"/{ns}" if ns else ""
    cm_node = f"{prefix}/controller_manager"

    def jtc():
        return {"type": "joint_trajectory_controller/JointTrajectoryController"}

    cm_controllers = {
        "update_rate": 200,
        "arm_controller": jtc(),
        "joint_state_broadcaster": {
            "type": "joint_state_broadcaster/JointStateBroadcaster",
        },
    }
    config = {
        f"{prefix}/arm_controller": {
            "ros__parameters": {
                "allow_nonzero_velocity_at_trajectory_end": False,
                "joints": arm_joints,
                "command_interfaces": ["position"],
                "state_interfaces": ["position", "velocity"],
            },
        },
    }

    if effector_type == "agx_gripper":
        cm_controllers["gripper_controller"] = jtc()
        config[f"{prefix}/gripper_controller"] = {
            "ros__parameters": {
                "allow_nonzero_velocity_at_trajectory_end": False,
                "joints": ["gripper"],
                "command_interfaces": ["position"],
                "state_interfaces": ["position", "velocity"],
            },
        }

    config[cm_node] = {"ros__parameters": cm_controllers}

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="vla_ros2_controllers_", delete=False
    )
    yaml.dump(config, tmp, default_flow_style=False)
    tmp.close()
    return tmp.name


def _launch(context):
    namespace = LaunchConfiguration("namespace").perform(context)
    arm_type = LaunchConfiguration("arm_type").perform(context)
    effector_type = LaunchConfiguration("effector_type").perform(context)

    # build_moveit_config() reads arm_type, effector_type, revo2_type and
    # tcp_offset from the launch context; they are declared below.
    robot_description = build_moveit_config(context).robot_description
    ros2_controllers_yaml = _build_ros2_controllers_file(
        arm_type, effector_type, namespace
    )

    # Jazzy's controller_manager reads robot_description from a topic. The
    # arm control launch already publishes <namespace>/robot_description
    # without a <ros2_control> tag, so this pair uses a separate topic.
    robot_description_topic = "vla_controllers/robot_description"

    robot_state_publisher_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[robot_description],
        remappings=[("robot_description", robot_description_topic)],
        output="screen",
    )

    control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[ros2_controllers_yaml],
        # The arm control node forwards control/joint_states to the arm.
        remappings=[
            ("robot_description", robot_description_topic),
            ("joint_states", LaunchConfiguration("control_topic")),
        ],
        output="screen",
    )

    def spawner(controller):
        return Node(
            package="controller_manager",
            executable="spawner",
            arguments=[controller, "--controller-manager", "controller_manager"],
            output="screen",
        )

    controllers = ["joint_state_broadcaster", "arm_controller"]
    if effector_type == "agx_gripper":
        controllers.append("gripper_controller")

    return [
        GroupAction(
            actions=[
                PushRosNamespace(namespace),
                robot_state_publisher_node,
                control_node,
                *[spawner(c) for c in controllers],
            ]
        )
    ]


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "namespace",
                default_value="follower",
                description="ROS namespace for the arm instance (matches the "
                "arm control node namespace).",
            ),
            DeclareLaunchArgument(
                "arm_type",
                default_value="piper_l",
                choices=["piper", "piper_x", "piper_l", "piper_h", "nero"],
                description="Arm type (feeds the robot_description).",
            ),
            DeclareLaunchArgument(
                "effector_type",
                default_value="agx_gripper",
                choices=["none", "agx_gripper", "revo2"],
                description="End effector type (feeds the robot_description "
                "and decides whether /gripper_controller is spawned).",
            ),
            DeclareLaunchArgument(
                "revo2_type",
                default_value="left",
                choices=["left", "right"],
                description="Revo2 side (used when effector_type is revo2).",
            ),
            DeclareLaunchArgument(
                "tcp_offset",
                default_value="[0.0, 0.0, 0.14, 0.0, 0.0, 0.0]",
                description="TCP offset [x, y, z, rx, ry, rz] in "
                "meters/radians.",
            ),
            DeclareLaunchArgument(
                "control_topic",
                default_value="control/joint_states",
                description="Joint states topic the arm control node "
                "consumes; the ros2_control_node's joint_states output is "
                "remapped here.",
            ),
            OpaqueFunction(function=_launch),
        ]
    )
