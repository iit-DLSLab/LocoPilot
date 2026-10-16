from pathlib import Path

from generate_parameter_library_py.generate_python_module import run
from setuptools import find_packages, setup
from setuptools.command.build_py import build_py

package_name = 'haptic_teleoperation'

package_root = Path(__file__).parent
parameter_definitions = {
    'joy_joint_controller_parameters.py': (
        package_root / package_name / 'nodes' /
        'joy_joint_controller_parameters.yaml'
    ),
    'p2p_teleoperation_parameters.py': (
        package_root / package_name / 'nodes' /
        'p2p_teleoperation_parameters.yaml'
    ),
}


class GenerateParametersBuildPy(build_py):
    """Generate the Python parameter listener during package build."""

    def run(self):
        """Build Python package files and generated parameter module."""
        output_path = Path(self.build_lib) / package_name
        for module_name, parameter_definition in parameter_definitions.items():
            output_file = output_path / module_name
            run(str(output_file), str(parameter_definition))
        super().run()


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch',
            [
                'launch/joy_joint_controller.launch.py',
                'launch/p2p_teleoperation.launch.py',
            ]),
        ('share/' + package_name + '/config',
            [
                'config/joy_joint_controller_params.yaml',
                'config/p2p_teleoperation_params.yaml',
            ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Antonio Langella',
    maintainer_email='antonio.langella@iit.it',
    description='Joint-space haptic teleoperation between two identical arms',
    license='MIT',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    cmdclass={'build_py': GenerateParametersBuildPy},
    entry_points={
        'console_scripts': [
            'joy_joint_controller = '
            'haptic_teleoperation.nodes.joy_joint_controller:main',
            'p2p_teleoperation = '
            'haptic_teleoperation.nodes.p2p_teleoperation:main',
        ],
    },
)
