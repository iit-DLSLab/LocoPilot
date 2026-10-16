"""
Position-position (P-P) joint-space haptic teleoperation node.

Couples two kinematically identical arms: each arm is commanded with the
other arm's motion as reference (position_position channels), plus one of
two mutually exclusive effort channels selected by force_reflection.enable:
- disabled (default): the P-P coupling effort
  tau = K (q_other - q_self) + D (dq_other - dq_self);
- enabled: force_reflection.gain * (other arm's external torque estimate),
  cross-fed from each side's own gravity-model-based estimator instead of
  being derived from position error. This decouples how fast an arm tracks
  its reference (still governed by the position/velocity channels and the
  receiving side's own local controller) from how strongly contact is felt,
  which the pure position-error-based effort above cannot do.

After validating both robot descriptions, both arms are homed to a shared
start configuration before either effort channel is applied.
"""

import enum

from haptic_teleoperation.utils.coupling import (
    coupling_efforts,
    force_reflection_efforts,
)
from haptic_teleoperation.utils.urdf import check_coupled_joints
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from sensor_msgs.msg import JointState
from std_msgs.msg import String


LOG_THROTTLE_SEC = 2.0


class TeleoperationPhase(enum.Enum):
    """Lifecycle phases of the teleoperation node."""

    WAIT_FOR_DESCRIPTIONS = enum.auto()
    WAIT_FOR_STATES = enum.auto()
    HOMING = enum.auto()
    COUPLING = enum.auto()


class ArmEndpoint:
    """ROS interface and latest tracked state for one arm."""

    def __init__(
        self,
        node: Node,
        name: str,
        joint_names,
        state_topic: str,
        control_topic: str,
        robot_description_topic: str,
        homing_control_topic: str = '',
        external_torque_topic: str = '',
    ):
        self._node = node
        self.name = name
        self._joint_names = list(joint_names)
        self.robot_description = None
        self.positions = None
        self.velocities = None
        self._state_stamp = None
        self.external_torque = None
        self._external_torque_stamp = None

        description_qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._description_sub = node.create_subscription(
            String,
            robot_description_topic,
            self._description_callback,
            description_qos,
        )
        self._state_sub = node.create_subscription(
            JointState,
            state_topic,
            self._state_callback,
            10,
        )
        self._command_pub = node.create_publisher(
            JointState,
            control_topic,
            10,
        )
        self._homing_command_pub = (
            node.create_publisher(JointState, homing_control_topic, 10)
            if homing_control_topic
            else self._command_pub
        )
        self._external_torque_sub = (
            node.create_subscription(
                JointState,
                external_torque_topic,
                self._external_torque_callback,
                10,
            )
            if external_torque_topic
            else None
        )

    def has_fresh_state(self, timeout_sec: float) -> bool:
        """Return whether a full state was received within timeout_sec."""
        if self._state_stamp is None:
            return False
        age = self._node.get_clock().now() - self._state_stamp
        return age.nanoseconds * 1e-9 <= timeout_sec

    def has_fresh_external_torque(self, timeout_sec: float) -> bool:
        """Return whether a full external torque estimate was received within timeout_sec."""
        if self._external_torque_stamp is None:
            return False
        age = self._node.get_clock().now() - self._external_torque_stamp
        return age.nanoseconds * 1e-9 <= timeout_sec

    def publish_command(
        self, positions, velocities, efforts, homing: bool = False
    ) -> None:
        """Publish a JointState command for the coupled joints."""
        message = JointState()
        message.header.stamp = self._node.get_clock().now().to_msg()
        message.name = list(self._joint_names)
        message.position = [float(value) for value in positions]
        message.velocity = [float(value) for value in velocities]
        message.effort = [float(value) for value in efforts]
        publisher = self._homing_command_pub if homing else self._command_pub
        publisher.publish(message)

    def publish_hold_command(self) -> None:
        """Command the last known positions with zero velocity and effort."""
        if self.positions is None:
            return
        zeros = np.zeros(len(self._joint_names))
        self.publish_command(self.positions, zeros, zeros)

    def _description_callback(self, message: String) -> None:
        self.robot_description = message.data

    def _state_callback(self, message: JointState) -> None:
        index_by_name = {name: i for i, name in enumerate(message.name)}
        missing = [
            name for name in self._joint_names if name not in index_by_name
        ]
        if missing or len(message.position) != len(message.name):
            self._node.get_logger().warn(
                f'Ignoring incomplete {self.name} joint state '
                f'(missing joints: {missing})',
                throttle_duration_sec=LOG_THROTTLE_SEC,
            )
            return
        indices = [index_by_name[name] for name in self._joint_names]
        self.positions = np.array(
            [message.position[index] for index in indices]
        )
        if len(message.velocity) == len(message.name):
            self.velocities = np.array(
                [message.velocity[index] for index in indices]
            )
        else:
            self.velocities = np.zeros(len(self._joint_names))
        self._state_stamp = self._node.get_clock().now()

    def _external_torque_callback(self, message: JointState) -> None:
        index_by_name = {name: i for i, name in enumerate(message.name)}
        missing = [
            name for name in self._joint_names if name not in index_by_name
        ]
        if missing or len(message.effort) != len(message.name):
            self._node.get_logger().warn(
                f'Ignoring incomplete {self.name} external torque estimate '
                f'(missing joints: {missing})',
                throttle_duration_sec=LOG_THROTTLE_SEC,
            )
            return
        indices = [index_by_name[name] for name in self._joint_names]
        self.external_torque = np.array(
            [message.effort[index] for index in indices]
        )
        self._external_torque_stamp = self._node.get_clock().now()


class P2PTeleoperationNode(Node):
    """Node coupling a leader and a follower arm in joint space."""

    def __init__(self):
        super().__init__('p2p_teleoperation')
        from haptic_teleoperation import p2p_teleoperation_parameters

        param_listener = (
            p2p_teleoperation_parameters.p2p_teleoperation.ParamListener(self)
        )
        params = param_listener.get_params()
        _validate_parameters(params)

        self._joint_names = list(params.coupled_joint_names)
        self._stiffness = np.array(params.coupling.stiffness)
        self._damping = np.array(params.coupling.damping)
        self._force_reflection_enable = params.force_reflection.enable
        self._force_reflection_gain = np.array(params.force_reflection.gain)
        self._start_configuration = np.array(params.start_configuration)
        self._state_timeout_sec = params.state_timeout_sec
        self._homing_duration_sec = params.homing.duration_sec
        self._homing_position_tolerance = params.homing.position_tolerance

        self._leader = ArmEndpoint(
            self,
            'leader',
            self._joint_names,
            params.leader.state_topic,
            params.leader.control_topic,
            params.leader.robot_description_topic,
            params.leader.homing_control_topic,
            params.leader.external_torque_topic,
        )
        self._follower = ArmEndpoint(
            self,
            'follower',
            self._joint_names,
            params.follower.state_topic,
            params.follower.control_topic,
            params.follower.robot_description_topic,
            params.follower.homing_control_topic,
            params.follower.external_torque_topic,
        )
        self._arms = (self._leader, self._follower)

        self._phase = TeleoperationPhase.WAIT_FOR_DESCRIPTIONS
        self._homing_start_time = None
        self._homing_start_positions = {}

        self._control_timer = self.create_timer(
            1.0 / params.control_rate_hz,
            self._control_step,
        )

    def _control_step(self) -> None:
        if self._phase is TeleoperationPhase.WAIT_FOR_DESCRIPTIONS:
            self._wait_for_descriptions_step()
        elif self._phase is TeleoperationPhase.WAIT_FOR_STATES:
            self._wait_for_states_step()
        elif self._phase is TeleoperationPhase.HOMING:
            self._homing_step()
        else:
            self._coupling_step()

    def _wait_for_descriptions_step(self) -> None:
        if any(arm.robot_description is None for arm in self._arms):
            self.get_logger().info(
                'Waiting for leader and follower robot descriptions...',
                throttle_duration_sec=LOG_THROTTLE_SEC,
            )
            return
        errors, warnings = check_coupled_joints(
            self._leader.robot_description,
            self._follower.robot_description,
            self._joint_names,
        )
        for warning in warnings:
            self.get_logger().warn(warning)
        if errors:
            for error in errors:
                self.get_logger().error(error)
            raise RuntimeError(
                'Coupled joints are incompatible between the leader and '
                'follower robot descriptions'
            )
        self.get_logger().info(
            'Robot descriptions validated: all coupled joints match.'
        )
        self._phase = TeleoperationPhase.WAIT_FOR_STATES

    def _wait_for_states_step(self) -> None:
        if not self._all_states_fresh():
            self.get_logger().info(
                'Waiting for leader and follower joint states...',
                throttle_duration_sec=LOG_THROTTLE_SEC,
            )
            return
        self._homing_start_positions = {
            arm.name: arm.positions.copy() for arm in self._arms
        }
        self._homing_start_time = self.get_clock().now()
        self.get_logger().info(
            'Homing both arms to the start configuration in '
            f'{self._homing_duration_sec:.1f}s.'
        )
        self._phase = TeleoperationPhase.HOMING

    def _homing_step(self) -> None:
        elapsed = self.get_clock().now() - self._homing_start_time
        progress = min(
            elapsed.nanoseconds * 1e-9 / self._homing_duration_sec,
            1.0,
        )
        blend, blend_rate = _minimum_jerk(progress)
        for arm in self._arms:
            delta = (
                self._start_configuration
                - self._homing_start_positions[arm.name]
            )
            reference_positions = (
                self._homing_start_positions[arm.name] + blend * delta
            )
            reference_velocities = (
                blend_rate / self._homing_duration_sec * delta
            )
            arm.publish_command(
                reference_positions,
                reference_velocities,
                np.zeros(len(self._joint_names)),
                homing=True,
            )
        if progress < 1.0:
            return
        if self._all_states_fresh() and self._all_arms_at_start():
            self.get_logger().info(
                'Both arms reached the start configuration; '
                'starting P-P coupling.'
            )
            self._phase = TeleoperationPhase.COUPLING
        else:
            self.get_logger().warn(
                'Arms have not reached the start configuration yet; '
                'holding the homing reference.',
                throttle_duration_sec=LOG_THROTTLE_SEC,
            )

    def _coupling_step(self) -> None:
        if not self._all_states_fresh():
            self.get_logger().warn(
                'Stale joint states; commanding hold with zero effort.',
                throttle_duration_sec=LOG_THROTTLE_SEC,
            )
            for arm in self._arms:
                arm.publish_hold_command()
            return
        for arm, other in (
            (self._leader, self._follower),
            (self._follower, self._leader),
        ):
            if self._force_reflection_enable:
                if other.has_fresh_external_torque(self._state_timeout_sec):
                    efforts = force_reflection_efforts(
                        self._force_reflection_gain, other.external_torque
                    )
                else:
                    efforts = np.zeros(len(self._joint_names))
            else:
                efforts = coupling_efforts(
                    arm.positions,
                    arm.velocities,
                    other.positions,
                    other.velocities,
                    self._stiffness,
                    self._damping,
                )
            arm.publish_command(other.positions, other.velocities, efforts)

    def _all_states_fresh(self) -> bool:
        return all(
            arm.has_fresh_state(self._state_timeout_sec)
            for arm in self._arms
        )

    def _all_arms_at_start(self) -> bool:
        return all(
            np.max(np.abs(arm.positions - self._start_configuration))
            <= self._homing_position_tolerance
            for arm in self._arms
        )


def _minimum_jerk(progress: float) -> tuple[float, float]:
    """Return minimum-jerk blend value and rate for progress in [0, 1]."""
    blend = 10 * progress**3 - 15 * progress**4 + 6 * progress**5
    blend_rate = 30 * progress**2 - 60 * progress**3 + 30 * progress**4
    return blend, blend_rate


def _validate_parameters(params) -> None:
    joint_count = len(params.coupled_joint_names)
    if joint_count == 0:
        raise ValueError('Parameter coupled_joint_names must not be empty')
    if len(set(params.coupled_joint_names)) != joint_count:
        raise ValueError('Parameter coupled_joint_names must be unique')
    for name, values in (
        ('coupling.stiffness', params.coupling.stiffness),
        ('coupling.damping', params.coupling.damping),
        ('force_reflection.gain', params.force_reflection.gain),
        ('start_configuration', params.start_configuration),
    ):
        if len(values) != joint_count:
            raise ValueError(
                f'Parameter {name} must have one entry per coupled joint '
                f'({joint_count}), got {len(values)}'
            )
    for name, values in (
        ('coupling.stiffness', params.coupling.stiffness),
        ('coupling.damping', params.coupling.damping),
    ):
        if any(value < 0.0 for value in values):
            raise ValueError(f'Parameter {name} values must be >= 0')


def main(args=None) -> int:
    """Run the P-P haptic teleoperation node."""
    rclpy.init(args=args)
    node = None
    exit_code = 0
    try:
        node = P2PTeleoperationNode()
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
