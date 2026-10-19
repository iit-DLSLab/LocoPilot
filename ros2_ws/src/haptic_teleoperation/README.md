# haptic_teleoperation

ROS 2 nodes for joint-space haptic teleoperation and joystick-driven discrete
joint references.

## Nodes

- `joy_joint_controller` maps joystick buttons to LOW/HIGH joint positions.
- `p2p_teleoperation` couples two kinematically identical arms in joint
  space, with either a position-position spring-damper coupling or force
  reflection of an external torque estimate.

## Joystick joint controller

`joy_joint_controller` subscribes to `sensor_msgs/msg/Joy` and publishes a
`sensor_msgs/msg/JointState` position reference. Every controlled joint can use
one of two button modes:

- `hold`: HIGH while the button is held, otherwise LOW.
- `trigger`: toggle between LOW and HIGH on each button press. Holding the
  button does not cause repeated toggles.

The published joint order is the order of the `joints` parameter. A Joy message
that does not contain a configured button index treats that button as released.

### Launch

The supplied launch file starts both the standard `joy/joy_node` driver and
`joy_joint_controller`:

```bash
ros2 launch haptic_teleoperation joy_joint_controller.launch.py
```

To use another configuration:

```bash
ros2 launch haptic_teleoperation joy_joint_controller.launch.py \
  params_file:=/path/to/joy_joint_controller_params.yaml
```

### Configuration

Parameters are declared with `generate_parameter_library_py`. The `joints`
array defines the controlled joints and drives the `mappings.__map_joints`
parameter map. Each joint then has its own button index, mode, LOW value, and
HIGH value:

```yaml
joy_joint_controller:
  ros__parameters:
    input_topic: /joy
    output_topic: /joint_reference
    joints: [gripper_joint, tool_joint]
    mappings:
      gripper_joint:
        button_index: 0
        mode: hold
        low_value: 0.0
        high_value: 0.04
      tool_joint:
        button_index: 1
        mode: trigger
        low_value: -1.0
        high_value: 1.0
```

The ready-to-use configuration is
[`config/joy_joint_controller_params.yaml`](./config/joy_joint_controller_params.yaml),
and the generated-parameter definition lives beside the node source in
[`haptic_teleoperation/nodes/joy_joint_controller_parameters.yaml`](./haptic_teleoperation/nodes/joy_joint_controller_parameters.yaml).

## P-P haptic teleoperation

`p2p_teleoperation` implements position-position bilateral teleoperation. Each
arm transmits its joint positions and velocities to the other, while a virtual
spring-damper couples each joint pair:

```text
tau_leader   = K (q_follower - q_leader)   + D (dq_follower - dq_leader)
tau_follower = K (q_leader   - q_follower) + D (dq_leader   - dq_follower)
```

The efforts are equal and opposite, allowing the operator to feel the
follower's tracking error. Each published `sensor_msgs/msg/JointState` contains:

- `position` and `velocity`: the other arm's tracked motion.
- `effort`: the spring-damper coupling effort, or the reflected torque when
  force reflection is enabled.

### Force reflection

With `force_reflection.enable: true` (the shipped configuration), the effort
sent to each arm is the other arm's external joint torque estimate scaled by
`force_reflection.gain`, instead of the spring-damper term:

```text
tau_leader   = Lambda * tau_ext_follower
tau_follower = Lambda * tau_ext_leader
```

The estimates are read from `leader.external_torque_topic` and
`follower.external_torque_topic` (`sensor_msgs/msg/JointState`, `effort`
field). On the Piper arms they are published by `agx_arm_pd_g_controller`'s
momentum observer. Tracking is unchanged: each arm's local controller still
follows the other arm's position and velocity. A stale estimate is replaced by
zero effort.

### Startup sequence

The node progresses through three phases:

1. **Description check** — wait for both robot descriptions and verify that
   every coupled joint exists and is movable on both arms. Joint-limit
   mismatches produce warnings; missing or incompatible joints stop the node.
2. **Homing** — move both arms to `start_configuration` using a minimum-jerk
   reference.
3. **Coupling** — start P-P coupling once both arms are within
   `homing.position_tolerance` of the start configuration.

If either state stream is older than `state_timeout_sec`, both arms hold their
last positions with zero effort until fresh states arrive.

### Launch

```bash
ros2 launch haptic_teleoperation p2p_teleoperation.launch.py
```

To use another configuration:

```bash
ros2 launch haptic_teleoperation p2p_teleoperation.launch.py \
  params_file:=/path/to/p2p_teleoperation_params.yaml
```

### Parameters

The generated-parameter definition is
[`haptic_teleoperation/nodes/p2p_teleoperation_parameters.yaml`](./haptic_teleoperation/nodes/p2p_teleoperation_parameters.yaml),
and the runtime configuration is
[`config/p2p_teleoperation_params.yaml`](./config/p2p_teleoperation_params.yaml).

| Parameter | Description |
| --- | --- |
| `leader.state_topic`, `follower.state_topic` | Joint state topics. |
| `leader.control_topic`, `follower.control_topic` | Joint command topics. |
| `leader.homing_control_topic`, `follower.homing_control_topic` | Optional command topics used only during homing; an empty value falls back to `control_topic`. |
| `leader.robot_description_topic`, `follower.robot_description_topic` | URDF topics using transient-local durability. |
| `leader.external_torque_topic`, `follower.external_torque_topic` | External torque estimates used by force reflection. |
| `coupled_joint_names` | Ordered joints coupled between the arms. |
| `coupling.stiffness`, `coupling.damping` | Per-joint spring-damper gains. |
| `force_reflection.enable`, `force_reflection.gain` | Select force reflection and its per-joint gain. |
| `start_configuration` | Shared initial joint positions. |
| `control_rate_hz` | Coupling control-loop rate. |
| `state_timeout_sec` | Maximum accepted joint-state age. |
| `homing.duration_sec`, `homing.position_tolerance` | Homing duration and completion tolerance. |

### Limitations and tuning

- The receiving controller must consume `JointState.effort` as feed-forward
  torque for `coupling.stiffness` and `coupling.damping` to affect the perceived
  coupling. A controller that only tracks position and velocity ignores these
  efforts.
- The implementation currently targets two identical arms. Scaled or
  dissimilar-kinematics teleoperation is out of scope.
- Tune stiffness and damping for the robot and transport delay. Large gains or
  delays can compromise passivity and stability.
