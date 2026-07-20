import sys
import tempfile
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace, SetRemap

# Reuse the exact robot_description built by the agx_arm_ros MoveIt config so
# the ros2_control joint/hardware definitions stay in lock-step with MoveIt
# and teleoperation. The launch dir (with _moveit_config_builder.py) is
# installed to share/agx_arm_moveit/launch by the package's CMakeLists.
_MOVEIT_LAUNCH_DIR = Path(get_package_share_directory("agx_arm_moveit")) / "launch"
sys.path.insert(0, str(_MOVEIT_LAUNCH_DIR))

from _moveit_config_builder import build_moveit_config  # noqa: E402


def _build_ros2_controllers_file(arm_type, namespace):
    """Write a ros2_controllers config to a temp YAML and return its path.

    Mirrors agx_arm_moveit/launch/demo.launch.py::_build_ros2_controllers_file
    (which reads config/ros2_controllers.yaml), restricted to the two JTCs the
    VLA deployment drives: /arm_controller and /gripper_controller, plus the
    joint_state_broadcaster that publishes the mock-hardware state which the
    arm control node forwards to the real arm.
    """
    arm_joints = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
    if arm_type == "nero":
        arm_joints.append("joint7")

    ns = namespace.strip("/")
    prefix = f"/{ns}" if ns else ""
    cm_node = f"{prefix}/controller_manager"

    jtc = {"type": "joint_trajectory_controller/JointTrajectoryController"}

    config = {
        cm_node: {
            "ros__parameters": {
                "update_rate": 200,
                "arm_controller": jtc,
                "gripper_controller": jtc,
                "joint_state_broadcaster": {
                    "type": "joint_state_broadcaster/JointStateBroadcaster",
                },
            },
        },
        f"{prefix}/arm_controller": {
            "ros__parameters": {
                "allow_nonzero_velocity_at_trajectory_end": False,
                "joints": arm_joints,
                "command_interfaces": ["position"],
                "state_interfaces": ["position", "velocity"],
            },
        },
        f"{prefix}/gripper_controller": {
            "ros__parameters": {
                "allow_nonzero_velocity_at_trajectory_end": False,
                "joints": ["gripper"],
                "command_interfaces": ["position"],
                "state_interfaces": ["position", "velocity"],
            },
        },
    }

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="vla_ros2_controllers_", delete=False
    )
    yaml.dump(config, tmp, default_flow_style=False)
    tmp.close()
    return tmp.name


def _launch(context):
    namespace = LaunchConfiguration("namespace").perform(context)
    arm_type = LaunchConfiguration("arm_type").perform(context)
    moveit_config = build_moveit_config(context)

    ros2_controllers_yaml = _build_ros2_controllers_file(arm_type, namespace)

    control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[moveit_config.robot_description, ros2_controllers_yaml],
        # The mock-hardware state the joint_state_broadcaster publishes on
        # `joint_states` is what the arm control node consumes as
        # control/joint_states to drive the real arm (same wiring as MoveIt).
        remappings=[("joint_states", LaunchConfiguration("control_topic"))],
        output="screen",
    )

    def spawner(controller):
        return Node(
            package="controller_manager",
            executable="spawner",
            arguments=[controller, "--controller-manager", "controller_manager"],
            output="screen",
        )

    return [
        GroupAction(
            actions=[
                PushRosNamespace(namespace),
                SetRemap(src="/robot_description", dst="robot_description"),
                control_node,
                spawner("joint_state_broadcaster"),
                spawner("arm_controller"),
                spawner("gripper_controller"),
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
                description="Arm type (feeds the MoveIt robot_description).",
            ),
            DeclareLaunchArgument(
                "effector_type",
                default_value="agx_gripper",
                choices=["none", "agx_gripper", "revo2"],
                description="End effector type (feeds the MoveIt "
                "robot_description).",
            ),
            DeclareLaunchArgument(
                "revo2_type",
                default_value="left",
                choices=["left", "right"],
                description="Revo2 side (used when effector_type is revo2); "
                "feeds the MoveIt robot_description.",
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
