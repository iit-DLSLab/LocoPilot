import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, PythonExpression


def generate_launch_description():
    """Launch the gripper and world RealSense cameras.

    Repo-local replacement for manipulation_demo_recorder's
    two_realsense_cameras.launch.py so the submodule stays untouched.
    Includes realsense2_camera's rs_launch.py once per camera — the same
    thing rs_multi_camera_launch.py does internally, minus its
    camera1->camera2 static transform node, which crashes when both
    cameras share a node name (frame_id == child_frame_id). Both node
    names must stay 'realsense_camera_node' because the demo-recorder
    launches subscribe to /<namespace>/realsense_camera_node/... topics.

    Configuration comes from environment variables (injected into the
    container by docker/jetson/start.sh) instead of launch arguments,
    which rs_launch would warn about as unsupported:

        GRIPPER_CAMERA_SERIAL      (default 750612070733)
        WORLD_CAMERA_SERIAL        (default 130322270336)
        WORLD_CAMERA_WIDTH/HEIGHT  (default 1280x720, colour and depth)

    The gripper camera runs at 640x480, both cameras at 30 fps.

    The world camera's colour profile is set both as
    rgb_camera.color_profile and depth_module.color_profile: on the D405
    the colour sensor lives under the depth module, on other models
    under rgb_camera; the unused parameter is ignored.

    Manual white balance / exposure for the gripper camera comes from
    gripper_camera_extra_params.yaml next to this file (rs_launch has no
    arguments for those; it warns that they are unsupported but still
    forwards them to the node, which does support them). The D405 world
    camera keeps auto exposure: its colour and depth share one sensor,
    so a manual colour exposure would degrade depth.
    """
    gripper_serial = EnvironmentVariable(
        'GRIPPER_CAMERA_SERIAL', default_value='750612070733',
    )
    world_serial = EnvironmentVariable(
        'WORLD_CAMERA_SERIAL', default_value='130322270336',
    )
    world_width = EnvironmentVariable(
        'WORLD_CAMERA_WIDTH', default_value='1280',
    )
    world_height = EnvironmentVariable(
        'WORLD_CAMERA_HEIGHT', default_value='720',
    )

    world_profile = _profile(world_width, world_height, '30')

    rs_launch = os.path.join(
        get_package_share_directory('realsense2_camera'),
        'launch',
        'rs_launch.py',
    )
    gripper_extra_params = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'gripper_camera_extra_params.yaml',
    )

    # Launch configurations set by one include leak into the next
    # (includes share the launch context), so every argument that differs
    # between the cameras must be set explicitly in both.
    common_arguments = [
        ('camera_name', 'realsense_camera_node'),
        ('enable_color', 'true'),
        ('enable_depth', 'true'),
        ('enable_sync', 'true'),
        ('rgb_camera.color_qos', 'SENSOR_DATA'),
        ('rgb_camera.color_info_qos', 'SENSOR_DATA'),
        ('depth_module.depth_qos', 'SENSOR_DATA'),
        ('depth_module.depth_info_qos', 'SENSOR_DATA'),
        ('enable_rgbd', 'true'),
        ('align_depth.enable', 'true'),
    ]

    gripper_camera = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(rs_launch),
        launch_arguments=common_arguments + [
            ('camera_namespace', 'gripper_camera'),
            ('serial_no', _quoted(gripper_serial)),
            ('tf_prefix', 'gripper_'),
            ('rgb_camera.color_profile', '640,480,30'),
            ('rgb_camera.enable_auto_exposure', 'false'),
            ('depth_module.depth_profile', '640,480,30'),
            ('depth_module.color_profile', '0,0,0'),
            ('config_file', gripper_extra_params),
        ],
    )

    world_camera = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(rs_launch),
        launch_arguments=common_arguments + [
            ('camera_namespace', 'world_camera'),
            ('serial_no', _quoted(world_serial)),
            ('tf_prefix', 'world_'),
            ('rgb_camera.color_profile', world_profile),
            ('rgb_camera.enable_auto_exposure', 'true'),
            ('depth_module.color_profile', world_profile),
            ('depth_module.depth_profile', world_profile),
            ('config_file', "''"),
        ],
    )

    return LaunchDescription([gripper_camera, world_camera])


def _profile(width, height, fps):
    return PythonExpression(["'", width, ',', height, ',', fps, "'"])


def _quoted(substitution):
    # rs_launch expects serial numbers as quoted strings (its unset
    # default is "''"); without the quotes the digits would be parsed as
    # an int and rejected by the node's string parameter.
    return PythonExpression(['"\'" + "', substitution, '" + "\'"'])
