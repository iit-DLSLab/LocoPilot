"""Map joystick buttons to discrete joint position references."""

from dataclasses import dataclass
from typing import Sequence

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState, Joy


HOLD_MODE = 'hold'
TRIGGER_MODE = 'trigger'
SUPPORTED_MODES = (HOLD_MODE, TRIGGER_MODE)


@dataclass(frozen=True)
class ButtonMapping:
    """Configuration for one button-to-joint mapping."""

    button_index: int
    joint_name: str
    mode: str
    low_value: float
    high_value: float


class JoyJointMapper:
    """Stateful conversion from a Joy button vector to joint positions."""

    def __init__(self, mappings: Sequence[ButtonMapping]):
        self._mappings = tuple(mappings)
        self._previous_pressed = [False] * len(self._mappings)
        self._trigger_high = [False] * len(self._mappings)

    @property
    def joint_names(self) -> list[str]:
        """Return mapped joint names in configuration order."""
        return [mapping.joint_name for mapping in self._mappings]

    def update(self, buttons: Sequence[int]) -> list[float]:
        """Update button states and return the resulting joint positions."""
        positions = []
        for index, mapping in enumerate(self._mappings):
            pressed = (
                mapping.button_index < len(buttons)
                and bool(buttons[mapping.button_index])
            )
            if mapping.mode == HOLD_MODE:
                high = pressed
            else:
                rising_edge = pressed and not self._previous_pressed[index]
                if rising_edge:
                    self._trigger_high[index] = not self._trigger_high[index]
                high = self._trigger_high[index]
            self._previous_pressed[index] = pressed
            positions.append(
                mapping.high_value if high else mapping.low_value
            )
        return positions


class JoyJointControllerNode(Node):
    """Publish discrete joint references from joystick button states."""

    def __init__(self):
        super().__init__('joy_joint_controller')
        from haptic_teleoperation import joy_joint_controller_parameters

        listener = (
            joy_joint_controller_parameters.joy_joint_controller
            .ParamListener(self)
        )
        params = listener.get_params()
        mappings = _mappings_from_parameters(params)

        self._mapper = JoyJointMapper(mappings)
        self._publisher = self.create_publisher(
            JointState, params.output_topic, 10
        )
        self._subscription = self.create_subscription(
            Joy, params.input_topic, self._joy_callback, 10
        )

    def _joy_callback(self, message: Joy) -> None:
        reference = JointState()
        reference.header.stamp = self.get_clock().now().to_msg()
        reference.name = self._mapper.joint_names
        reference.position = self._mapper.update(message.buttons)
        self._publisher.publish(reference)


def _mappings_from_parameters(params) -> list[ButtonMapping]:
    """Validate the joint list and build its mapped configurations."""
    joint_names = list(params.joints)
    if not joint_names:
        raise ValueError('Parameter joints must not be empty')
    if any(not name for name in joint_names):
        raise ValueError('Parameter joints must not contain empty names')
    if len(set(joint_names)) != len(joint_names):
        raise ValueError('Parameter joints must be unique')

    mappings = []
    for joint_name in joint_names:
        joint_params = params.mappings.get_entry(joint_name)
        mappings.append(ButtonMapping(
            joint_params.button_index,
            joint_name,
            joint_params.mode,
            joint_params.low_value,
            joint_params.high_value,
        ))

    invalid_modes = sorted(
        {mapping.mode for mapping in mappings} - set(SUPPORTED_MODES)
    )
    if invalid_modes:
        raise ValueError(
            'Mapped parameter mode only supports hold and trigger; got '
            f'{invalid_modes}'
        )
    if any(mapping.button_index < 0 for mapping in mappings):
        raise ValueError('Mapped parameter button_index must be >= 0')
    return mappings


def main(args=None) -> int:
    """Run the joystick joint controller node."""
    rclpy.init(args=args)
    node = None
    exit_code = 0
    try:
        node = JoyJointControllerNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except (RuntimeError, ValueError) as exc:
        if node is not None:
            node.get_logger().error(str(exc))
        else:
            print(exc)
        exit_code = 1
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
