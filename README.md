# LocoPilot

Robot and teleoperation software for **LocoPilot: Single-Operator Bilateral Teleoperation for Loco-Manipulation Policy Learning**.

LocoPilot is a teleoperation and data-collection framework for an arm-equipped quadruped: a 12-DoF Unitree Go2 carrying a 6-DoF AgileX Piper L arm, an Intel RealSense D435 wrist camera and a D405 head camera. A single operator commands base velocity, body pitch, arm configuration and gripper through a second Piper L arm, used as a leader, and handheld controllers. Interaction forces at the follower are estimated without a force/torque sensor and reflected to the leader. The robot-side modules are the same during demonstration collection and policy deployment.

This repository contains the ROS 2 Jazzy stack, packaged as Docker images, for the workstation and for the robot's onboard Jetson.

> **Safety:** these commands move the legs and the arm. Keep the robot supported for first tests, keep the e-stop within reach, and check the state topics before enabling the locomotion policy.

## System overview

| Paper module | Implementation |
|---|---|
| Go2 hardware abstraction | [`unitree-ros2-dls`](https://github.com/Giovadess/unitree-ros2-dls) (`go2_hal`, `dls2_interface` messages) |
| State estimator (MUSE) | [`muse`](https://github.com/Giovadess/muse) |
| Locomotion policy | [`locomanipulation-teleop-isaaclab`](https://github.com/Giovadess/locomanipulation-teleop-isaaclab): RL policy training and the ROS 2 controller (`deploy/run_controller_ros2.py`) that tracks base velocity and body pitch references and observes the arm configuration |
| Arm control stack | [`piper-ros2-dls`](https://github.com/iit-DLSLab/piper-ros2-dls): `agx_arm_ctrl` CAN driver and `agx_arm_pd_g_controller` (joint PD with gravity compensation on identified Piper L models, plus a generalized-momentum observer publishing the external joint torque on `feedback/external_torque`) |
| Leader–follower teleoperation | [`ros2_ws/src/haptic_teleoperation`](ros2_ws/src/haptic_teleoperation): `p2p_teleoperation` (alignment before coupling, joint-space position channel, force reflection of the follower's torque estimate, hold on stale state) and `joy_joint_controller` (gripper from a controller button) |
| Camera nodes | [`launch/two_realsense_cameras.launch.py`](launch/two_realsense_cameras.launch.py): wrist D435 and head D405 RGB-D streams |
| Arm trajectory interface (deployment) | [`launch/vla_arm_controllers.launch.py`](launch/vla_arm_controllers.launch.py): joint trajectory controllers that interpolate policy joint references for the follower arm |
| Middleware | ROS 2 Jazzy with CycloneDDS |

Repository layout:

```text
docker/            workstation image, helper scripts and container-side commands
docker/jetson/     robot-side image and deployment scripts for the Go2 Jetson
launch/            camera and arm-trajectory launch files
ros2_ws/src/       haptic_teleoperation package
scripts/           offline utilities for recorded bags
<submodules>       see the table above
```

Image internals, environment variables and build details are in [docker/README.md](docker/README.md).

## Hardware and network

- Unitree Go2 with an AgileX Piper L arm and gripper, a RealSense D435 on the gripper and a D405 on the head.
- A second Piper L arm on the workstation as the leader. A USB-CAN adapter for each arm.
- Handheld controllers for base commands (`/joy`, started by `run-joy`) and for the gripper (`/joycon`, started by `joy_joint_controller.launch.py`), the latter mounted on the leader handle. Both drivers open joystick device 0 by default; set `device_id` when two controllers are connected to the same machine.
- A workstation running Ubuntu with Docker. The Go2 Jetson needs Docker, the NVIDIA container toolkit and [jetson-containers](https://github.com/dusty-nv/jetson-containers).
- Workstation and robot on the Go2 network (default `192.168.123.0/24`, robot at `192.168.123.18`). CycloneDDS uses multicast discovery, so the network must forward multicast on that subnet.

The defaults in the scripts (addresses, camera serial numbers, arm type) describe the reference setup. Change them in the `.env` files.

## 1. Clone

```bash
git clone --recurse-submodules https://github.com/iit-DLSLab/locoman_vla_deploy.git
cd locoman_vla_deploy
```

For an existing clone: `git submodule sync --recursive && git submodule update --init --recursive`.

## 2. Workstation setup

```bash
cd docker
cp .env.example .env
```

Set at least the interface connected to the robot network (find it with `ip -br addr`):

```dotenv
ROBOT_NET_IFACE=enp98s0
ROS_DOMAIN_ID=42
```

Check that the robot is reachable:

```bash
ping -c 3 192.168.123.18
```

Build the image, start the container and build the workspaces:

```bash
./build-image.sh
./start.sh
./build-workspaces.sh --clean   # drop --clean for incremental rebuilds
```

Every terminal below starts with `./attach.sh`, which opens a shell in the container with the environment sourced (`RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`, `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET`, and a generated `CYCLONEDDS_URI` bound to `CYCLONEDDS_SUBNET`). `./check.sh` validates the installation; add `--topics` to list live topics.

## 3. Robot setup

One-time installation, run from the workstation:

```bash
cd docker/jetson
cp jetson.env.example .env   # robot address, camera serials (rs-enumerate-devices -s)
./install-robot.sh
```

`install-robot.sh` installs your ssh key on the robot, clones this repository there with the `piper-ros2-dls` submodule, builds the base and robot images, starts the container and builds the workspaces. It is idempotent. It refuses to run if the local branch is not pushed, because the robot clones from `origin`.

## 4. Locomotion

Run the locomotion stack from the workstation container, one attached terminal per process.

```bash
run-go2-hal      # Go2 HAL: /lowstate -> /blind_state
run-muse         # MUSE: /blind_state -> /base_state
```

Before starting the controller, check that both state topics carry finite, plausible values:

```bash
timeout 15 ros2 topic echo /blind_state dls2_interface/msg/BlindState --once --qos-reliability best_effort
timeout 15 ros2 topic echo /base_state  dls2_interface/msg/BaseState  --once --qos-reliability best_effort
timeout 10 ros2 topic hz /base_state --qos-reliability best_effort
```

Then start the controller and the base controller driver:

```bash
run-controller   # locomotion policy (deploy/run_controller_ros2.py)
run-joy          # joystick driver on /joy
```

In the controller console, send `goUp` first and check joint directions and smooth motion. Then, with zero velocity commanded, send `activateRL` and let the robot stand under the policy before commanding motion.

| Control | Action |
|---|---|
| D-pad up / down | `goUp` / `goDown` |
| `+` | Toggle the RL policy |
| Left stick | Forward/backward and lateral velocity |
| Right stick horizontal | Yaw rate |

## 5. Leader–follower teleoperation

With the locomotion stack running, start the arm stacks. Each command activates the CAN interface inside the container and attaches to a tmux session with one window per process (detach with `C-b d`, stop everything with `C-b : kill-session`).

```bash
docker/jetson/deploy-robot.sh   # robot: follower arm driver, PD+gravity controller, cameras
docker/deploy-leader.sh         # workstation: leader arm driver, PD+gravity controller,
                                # p2p_teleoperation, joy_joint_controller
```

`p2p_teleoperation` waits for both robot descriptions and moves both arms to a common start configuration. Only then does it couple them: the follower tracks the leader's joint positions and velocities through its PD+gravity controller, and the leader receives the follower's filtered external-torque estimate scaled by `force_reflection.gain`. If either joint-state stream goes stale, both arms hold their position. The gripper follows the trigger of the controller mounted on the leader handle (`/joycon`). See the [package README](ros2_ws/src/haptic_teleoperation/README.md) for parameters.

<details>
<summary>Manual equivalent</summary>

```bash
can-activate   # inside the container, or piper-ros2-dls/.../scripts/can_activate.sh on the host with sudo

ros2 launch agx_arm_ctrl start_single_agx_arm_rviz.launch.py \
    namespace:=follower tcp_offset:='[0.0, 0.0, 0.14, 0.0, 0.0, 0.0]' \
    arm_type:=piper_l effector_type:=agx_gripper

ros2 launch agx_arm_pd_g_controller pd_g_controller.launch.py \
    namespace:=follower enable_gravity_compensation:=true use_gripper:=true

ros2 launch launch/two_realsense_cameras.launch.py
```

On the workstation, run the same arm commands with `namespace:=leader`, then:

```bash
ros2 launch haptic_teleoperation p2p_teleoperation.launch.py
ros2 launch haptic_teleoperation joy_joint_controller.launch.py
```

</details>

Camera topics are published under `/gripper_camera/realsense_camera_node/...` and `/world_camera/realsense_camera_node/...` with best-effort QoS. Record the session with `ros2 bag record` and export it as described in [Dataset export](#6-dataset-export).

## 6. Dataset export

[`scripts/export_lerobot.py`](scripts/export_lerobot.py) converts recorded teleoperation bags into a [LeRobot](https://github.com/huggingface/lerobot) dataset. It needs `lerobot[dataset]>=0.6`, `rosbags` and `opencv-python`, and runs outside the containers.

```bash
python scripts/export_lerobot.py <bag_dir> [<bag_dir> ...] \
    --repo-id <user>/<dataset> --root datasets/<dataset> \
    --task "Pick the red cube and place it on the blue base"
```

- **Episodes** are delimited by the handle controller (`/joycon`): button 3 starts an episode, button 2 ends it, and a second start before an end restarts it. `--dry-run` lists the episodes without writing anything.
- **Frames** are sampled at `--fps` (default 10) on the bag receive clock, holding the latest message of each stream. Header stamps are not used, because the machines' clocks are not synchronized.
- **`action`** is the 11-D command `[vx, vy, wz, pitch, joint1..joint6, gripper]`. The arm part is the follower command (`/follower/control/move_mit_joint_states`) and the gripper part is the `joy_joint_controller` reference. The base part is read from a recorded command topic if configured; otherwise it is replayed from `/joy` with the locomotion controller's filter.
- **`observation.state`** holds the follower joint and gripper positions, plus the base linear and angular velocity and orientation from MUSE.
- **`observation.images.*`** holds the wrist and head colour streams and depth in millimetres (`--no-depth` to skip depth).
- **Language:** `--task` sets one instruction for all episodes; `--tasks-file` maps bag names to an instruction or to a list with one entry per episode.

Topics and mappings can be overridden with `--config <file.yaml>` (see `DEFAULT_CONFIG` in the script). For example, to read body pitch from a joystick axis:

```yaml
base_command:
  pitch_axis: 4        # stick axis on /joy
  pitch_mode: rate     # rate: integrate the axis; absolute: map it directly
  pitch_scale: 0.5     # rad/s (rate) or rad (absolute) at full deflection
```

Bags recorded before the gripper moved to button 8 need `--gripper-button 7`.

## 7. Policy deployment

For autonomous operation, the operator-side stack is replaced by a policy. The robot-side session keeps the same arm driver and cameras, and swaps the PD+gravity teleoperation controller for joint trajectory controllers:

```bash
docker/jetson/deploy-vla.sh
```

| Window | Process |
|---|---|
| `arm-ctrl` | follower arm driver (`agx_arm_ctrl`, namespace `follower`) |
| `controllers` | `ros2_control_node` with `/follower/arm_controller` and `/follower/gripper_controller` joint trajectory controllers |
| `cameras` | wrist and head RealSense cameras |

A policy sends arm and gripper joint references as `trajectory_msgs/JointTrajectory` to these controllers. They interpolate the references at the controller rate and forward them to the arm. The locomotion stack of §4 is unchanged.

## 8. Simulation

The workstation image can also run the locomotion policy without hardware.

Standalone MuJoCo, with keyboard control after typing `ictp` in the console (`w`/`s`, `a`/`d`, `q`/`e`, `0` to stop):

```bash
cd /workspace/locoman_vla_deploy/locomanipulation-teleop-isaaclab
python3 deploy/play_mujoco.py
```

ROS 2 sim-to-sim, in two attached terminals:

```bash
cd /workspace/locoman_vla_deploy/locomanipulation-teleop-isaaclab
source deploy/ros2_localhost_connect.sh
python3 deploy/run_simulator_ros2.py    # terminal 1
python3 deploy/run_controller_ros2.py   # terminal 2: goUp, activateRL, ictp
```

`ros2_localhost_connect.sh` restricts discovery to localhost. Do not source it in robot terminals.

## Troubleshooting

**`'localhost_only' is enabled` warning.** The shell inherited the simulation environment. Open a new shell with `./attach.sh`.

**Topics from the robot are not visible.** Check that `ROS_DOMAIN_ID` matches on both machines, that `CYCLONEDDS_SUBNET` matches the robot network, and that multicast is forwarded on it. Test known topics directly with `ros2 topic echo <topic> --once` rather than `ros2 topic list`.

**`/lowstate` works but `/blind_state` does not.** The Go2 HAL must subscribe with `rclcpp::SensorDataQoS()`, as the pinned `unitree-ros2-dls` does. Make sure the submodule is at the pinned commit.

**`Failed to parse type hash for topic ...`.** Native Unitree DDS endpoints carry no ROS 2 type-hash metadata. The message is harmless.

**No force feedback on the leader.** Check that `/follower/feedback/external_torque` is published. It requires `external_torque_estimation.enable` in the follower's `agx_arm_pd_g_controller` configuration.

Container and build issues are covered in [docker/README.md](docker/README.md#troubleshooting).

## Updating

```bash
git pull
git submodule sync --recursive
git submodule update --init --recursive
```

After pushing a change inside a submodule, commit the new pointer in this repository (`git add <submodule> && git commit`).

## Citation

```bibtex
@misc{langella2026locopilot,
  title  = {LocoPilot: Single-Operator Bilateral Teleoperation for Loco-Manipulation Policy Learning},
  author = {Langella, Antonio and Minelli, Giovanni and Dessy, Giovanni B. and Amatucci, Lorenzo and
            Turrisi, Giulio and Barasuol, Victor and Semini, Claudio},
  year   = {2026},
  note   = {TODO: venue and link}
}
```

## License

This repository is released under the [MIT License](LICENSE). Submodules are distributed under their own licenses.
