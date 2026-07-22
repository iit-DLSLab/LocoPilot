import ast
import os
import tempfile

import xacro
import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace, SetRemap

# We run xacro on the agx_arm_moveit package's ros2_control URDF directly
# instead of going through moveit_configs_utils/move_group -- the VLA stack
# only needs the robot_description + ros2_control tags for the mock-hardware
# controller_manager, not planning/rviz.
_CONFIG_DIR = os.path.join(get_package_share_directory("agx_arm_moveit"), "config")
_URDF_XACRO = os.path.join(_CONFIG_DIR, "agx_arm.urdf.xacro")
_INITIAL_POSITIONS = os.path.join(_CONFIG_DIR, "initial_positions.yaml")


def _build_robot_description(arm_type, effector_type, revo2_type, tcp_offset):
    """Run xacro on the vendored URDF and return the {robot_description: xml} dict."""
    doc = xacro.process_file(
        _URDF_XACRO,
        mappings={
            "arm_type": arm_type,
            "effector_type": effector_type,
            "revo2_type": revo2_type,
            "initial_positions_file": _INITIAL_POSITIONS,
            "tcp_offset_xyz": f"{tcp_offset[0]} {tcp_offset[1]} {tcp_offset[2]}",
            "tcp_offset_rpy": f"{tcp_offset[3]} {tcp_offset[4]} {tcp_offset[5]}",
        },
    )
    return {"robot_description": doc.toxml()}


def _build_ros2_controllers_file(arm_type, effector_type, namespace):
    """Write a ros2_controllers config to a temp YAML and return its path.

    Same controller definitions as agx_arm_moveit/config/ros2_controllers.yaml
    (and demo.launch.py), restricted to the two JTCs the VLA deployment drives
    -- /arm_controller and /gripper_controller -- plus the
    joint_state_broadcaster that publishes the mock-hardware state the arm
    control node forwards to the real arm.
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
    revo2_type = LaunchConfiguration("revo2_type").perform(context)
    tcp_offset = ast.literal_eval(LaunchConfiguration("tcp_offset").perform(context))

    robot_description = _build_robot_description(
        arm_type, effector_type, revo2_type, tcp_offset
    )
    ros2_controllers_yaml = _build_ros2_controllers_file(
        arm_type, effector_type, namespace
    )

    control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[robot_description, ros2_controllers_yaml],
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

    controllers = ["joint_state_broadcaster", "arm_controller"]
    if effector_type == "agx_gripper":
        controllers.append("gripper_controller")

    return [
        GroupAction(
            actions=[
                PushRosNamespace(namespace),
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
