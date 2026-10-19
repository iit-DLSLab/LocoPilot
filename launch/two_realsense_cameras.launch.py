import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, PythonExpression


def generate_launch_description():
    """Launch the gripper (D435) and world (D405) RealSense cameras.

    Includes realsense2_camera's rs_launch.py once per camera. Topics are
    published under /gripper_camera/realsense_camera_node/... and
    /world_camera/realsense_camera_node/...

    Configuration comes from environment variables (set in the container by
    docker/jetson/start.sh):

        GRIPPER_CAMERA_SERIAL      (default: reference setup)
        WORLD_CAMERA_SERIAL        (default: reference setup)
        WORLD_CAMERA_WIDTH/HEIGHT  (default 1280x720, colour and depth)

    The gripper camera runs at 640x480, both cameras at 30 fps. On the D405
    the colour sensor belongs to the depth module, so the world camera sets
    both rgb_camera.color_profile and depth_module.color_profile. The D405
    keeps auto exposure because colour and depth share one sensor.

    Parameters rs_launch.py does not expose as launch arguments (manual
    exposure, best-effort QoS) are passed through the per-camera YAML files
    next to this file.
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
    world_extra_params = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'world_camera_extra_params.yaml',
    )

    # Includes share the launch context, so every argument that differs
    # between the cameras must be set explicitly in both.
    common_arguments = [
        ('camera_name', 'realsense_camera_node'),
        ('enable_color', 'true'),
        ('enable_depth', 'true'),
        ('enable_sync', 'true'),
        ('enable_rgbd', 'true'),
        ('align_depth.enable', 'false'),
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
            ('config_file', world_extra_params),
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
