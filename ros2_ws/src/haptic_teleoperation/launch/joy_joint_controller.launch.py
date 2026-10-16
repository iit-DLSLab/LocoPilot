from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Launch the joystick driver and joystick joint controller."""
    package_share = FindPackageShare('haptic_teleoperation')
    params_file = LaunchConfiguration('params_file')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=PathJoinSubstitution([
                package_share,
                'config',
                'joy_joint_controller_params.yaml',
            ]),
            description='Joystick joint controller parameter file.',
        ),
        Node(
            package='joy',
            executable='joy_node',
            name='joy_node',
            output='screen',
            remappings=[('/joy', '/joycon')],  # Remap the joy topic to /joycon
        ),
        Node(
            package='haptic_teleoperation',
            executable='joy_joint_controller',
            name='joy_joint_controller',
            output='screen',
            parameters=[params_file],
        ),
    ])
