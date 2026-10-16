from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Launch the P-P haptic teleoperation node."""
    package_share = FindPackageShare('haptic_teleoperation')

    params_file = LaunchConfiguration('params_file')

    teleoperation_node = Node(
        package='haptic_teleoperation',
        executable='p2p_teleoperation',
        name='p2p_teleoperation',
        output='screen',
        parameters=[params_file],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=PathJoinSubstitution([
                package_share,
                'config',
                'p2p_teleoperation_params.yaml',
            ]),
            description='Parameter file for the P-P teleoperation node.',
        ),
        teleoperation_node,
    ])
