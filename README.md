# Locomanipulation VLA Deployment

Dockerized ROS 2 Jazzy deployment stack for Unitree Go2 locomotion and AgileX Piper arm teleoperation.

| Submodule | Role | Pinned to |
|---|---|---|
| [`locomanipulation-teleop-isaaclab`](./locomanipulation-teleop-isaaclab) | RL policy, MuJoCo sim, ROS 2 controller/joystick | `jazzy-deploy` |
| [`muse`](./muse) | Base-state estimation | `jazzy-deploy` |
| [`unitree-ros2-dls`](./unitree-ros2-dls) | Go2 HAL, shared DLS ROS 2 messages | `jazzy-deploy` |
| [`piper-ros2-dls`](./piper-ros2-dls) | AgileX Piper arm HAL | `main` |
| [`dls_ros2_manipulation`](./dls_ros2_manipulation) | Haptic teleoperation + demo recorder/cameras, built via the top-level `ros2_ws` | `feature/p2p_haptic_teleoperation` @ `95f1493` (TODO: merge upstream) |

`docker/` (Dockerfile + helper scripts) is tracked directly in this repo, not a submodule.

> **Safety:** physical-robot commands move the legs and arm. Keep the robot supported, keep the e-stop ready, and verify state topics before enabling the policy.

## 1. Clone

```bash
git clone --recurse-submodules https://github.com/iit-DLSLab/locoman_vla_deploy.git
cd locoman_vla_deploy
```

Existing clone: `git submodule sync --recursive && git submodule update --init --recursive` — this also initializes nested submodules (e.g. `unitree-ros2-dls/unitree_ros2`). No manual branch switching is needed inside any submodule.

## 2. Configure Docker

```bash
cd docker
cp .env.example .env
```

Customize `.env` and set the host network interface connected to the Unitree network:

```dotenv
HOST_WORKSPACE=/home/gdessy-iit.local/locoman_vla_deploy
CONTAINER_WORKSPACE=/workspace/locoman_vla_deploy
ROBOT_NET_IFACE=enp98s0
ROS_DOMAIN_ID=42
```

<details>
<summary><b>Configuration details</b></summary>

Find the interface name with:

```bash
ip -br addr
nmcli device status
```

For the tested Go2 setup:

```text
PC:    192.168.123.99/24
Robot: 192.168.123.18
NIC:   enp98s0
```

Sanity-check reachability before going further:

```bash
ip route get 192.168.123.18   # Go2 default IP
ping -c 3 192.168.123.18
```

</details>

## 3. Build and start the container

```bash
cd docker
./build-image.sh
./start.sh
./build-workspaces.sh --clean   # first build; drop --clean for incremental rebuilds
```

Build order: Unitree SDK workspace (`unitree_ros2/cyclonedds_ws` — messages/IDL only; the folder name is inherited from upstream and does not dictate the runtime RMW, which is Fast DDS, see §9) → `unitree-ros2-dls/ros2_ws` → `muse/muse_ws` → `piper-ros2-dls/ros2_ws` → `ros2_ws` (dls_ros2_manipulation packages) → anything in `EXTRA_ROS_WORKSPACES`. Details (duplicate-package handling, per-package build quirks): `docker/README.md`.

```bash
./attach.sh              # open a container shell — every deploy terminal starts here
./check.sh                # validate installs, imports, and (with --topics) live ROS topics
./stop.sh / ./start.sh    # stop/resume, container persists
./remove-container.sh && ./start.sh   # recreate after changing .env or mounts
```

## 4. ROS 2 robot environment

All physical-robot terminals must use Fast DDS (`rmw_fastrtps_cpp`) on the robot-facing interface — this matches the Go2's own native DDS stack (see §9).

Inside the container this is already configured automatically: `attach.sh` opens a shell with `dls-env` sourced, which sets `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`, sets `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET` (the Jazzy replacement for `ROS_LOCALHOST_ONLY`, which is unset), and generates a `FASTRTPS_DEFAULT_PROFILES_FILE` that pins Fast DDS's UDP transport to `ROBOT_NET_IFACE`'s IP address (Fast DDS whitelists by **IP address**, not interface name, unlike CycloneDDS).

Verify before launching robot processes:

```bash
echo "$RMW_IMPLEMENTATION"
echo "$ROS_DOMAIN_ID"
echo "$ROS_AUTOMATIC_DISCOVERY_RANGE"
echo "$FASTRTPS_DEFAULT_PROFILES_FILE"
cat "$FASTRTPS_DEFAULT_PROFILES_FILE"
env | grep ROS_LOCALHOST_ONLY
```

Expected:

```text
rmw_fastrtps_cpp
42
SUBNET
```

The profiles file should exist and its `<interfaceWhiteList><address>` should match `ROBOT_NET_IFACE`'s IP, and `ROS_LOCALHOST_ONLY` must not be set (deprecated since Iron; `ROS_AUTOMATIC_DISCOVERY_RANGE` replaces it).

<details>
<summary><b>Manual / outside-container setup</b></summary>

Running components directly on the host without the Docker wrapper is uncommon, but if needed, source the workspaces and export the same variables by hand:

```bash
source /opt/ros/jazzy/setup.bash
source /workspace/locoman_vla_deploy/unitree-ros2-dls/unitree_ros2/cyclonedds_ws/install/setup.bash   # messages/IDL only, not the RMW
source /workspace/locoman_vla_deploy/unitree-ros2-dls/unitree_ros2_connect.bash
source /workspace/locoman_vla_deploy/unitree-ros2-dls/ros2_ws/install/setup.bash
source /workspace/locoman_vla_deploy/muse/muse_ws/install/setup.bash

unset ROS_LOCALHOST_ONLY
unset ROS_STATIC_PEERS
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

Then generate a Fast DDS profile XML whitelisting your interface's IP address and export `FASTRTPS_DEFAULT_PROFILES_FILE` to point at it — see `docker/docker/dls-env` for the exact XML generated automatically inside the container.

</details>

## 5. Standalone MuJoCo test

This test runs the policy directly in MuJoCo without the ROS 2 simulator interface.

```bash
cd docker
./attach.sh

cd /workspace/locoman_vla_deploy/locomanipulation-teleop-isaaclab
python3 deploy/play_mujoco.py
```

In the controller console:

```text
ictp
```

Keyboard commands:

```text
w / s    forward / backward
a / d    lateral motion
q / e    yaw
0        zero velocity command
```

Do not run this process together with `run_simulator_ros2.py`.

## 6. ROS 2 MuJoCo sim-to-sim

Use two attached terminals.

### Terminal 1 — simulator

```bash
./attach.sh
cd /workspace/locoman_vla_deploy/locomanipulation-teleop-isaaclab
source deploy/ros2_localhost_connect.sh
python3 deploy/run_simulator_ros2.py
```

### Terminal 2 — controller

```bash
./attach.sh
cd /workspace/locoman_vla_deploy/locomanipulation-teleop-isaaclab
source deploy/ros2_localhost_connect.sh
python3 deploy/run_controller_ros2.py
```

Controller sequence:

```text
goUp
activateRL
ictp
```

Expected topic flow:

```text
MuJoCo simulator
 ├── /blind_state ───────────────► controller
 ├── /base_state ────────────────► controller
 └── /arm_state ─────────────────► controller

Controller
 ├── /trajectory_generator ──────► simulator
 └── /arm_trajectory_generator ──► simulator
```

Do not source `ros2_localhost_connect.sh` for physical-robot deployment.

## 7. Physical robot deployment

Use a separate attached terminal for each process. Keep the robot supported for the first test.

### Terminal 1 — Unitree Go2 HAL

```bash
cd /home/gdessy-iit.local/locoman_vla_deploy/docker
./attach.sh
run-go2-hal
```

Equivalent direct command:

```bash
cd /workspace/locoman_vla_deploy/unitree-ros2-dls
python3 launch_go2_hal.py
```

### Terminal 2 — MUSE state estimator

```bash
./attach.sh
run-muse
```

Equivalent direct command:

```bash
ros2 launch state_estimator state_estimator.launch.py
```

### Verify the state pipeline

The required pipeline is:

```text
Robot /lowstate
    → go2_hal
    → /blind_state
    → MUSE
    → /base_state
```

Check explicit topics instead of relying on a full `ros2 topic list`, which can be slow on the Unitree DDS graph:

```bash
timeout 15 ros2 topic echo \
  /blind_state \
  dls2_interface/msg/BlindState \
  --once \
  --qos-reliability best_effort

timeout 15 ros2 topic echo \
  /base_state \
  dls2_interface/msg/BaseState \
  --once \
  --qos-reliability best_effort
```

Check rates:

```bash
timeout 10 ros2 topic hz /blind_state --qos-reliability best_effort
timeout 10 ros2 topic hz /base_state --qos-reliability best_effort
```

Do not start the controller until both messages contain finite and plausible values.

### Terminal 3 — policy controller

```bash
./attach.sh
run-controller
```

Equivalent direct command:

```bash
cd /workspace/locoman_vla_deploy/locomanipulation-teleop-isaaclab
python3 deploy/run_controller_ros2.py
```

First physical test:

```text
goUp
```

Verify correct joint directions, symmetry, and smooth motion. Then, with zero velocity commands:

```text
activateRL
```

Let the robot stand with the policy active before commanding locomotion.

### Terminal 4 — joystick

```bash
./attach.sh
run-joy
```

Verify joystick input:

```bash
ros2 topic echo /joy sensor_msgs/msg/Joy
```

Tested joystick controls:

```text
D-pad Up                goUp
D-pad Down              goDown
+ button                toggle RL policy
Left stick vertical     forward/backward
Left stick horizontal   lateral motion
Right stick horizontal  yaw
```

Press D-pad Up once and wait for the standing interpolation to finish before toggling RL.

## 8. Arm teleoperation

The AgileX Piper arm HAL (`piper-ros2-dls`) is built automatically by `build-workspaces.sh` — it does not need an `EXTRA_ROS_WORKSPACES` entry. Real-hardware teleoperation needs three processes: one on the **host** (CAN bus activation) and two inside the **container** (arm controller + gravity-compensated PD controller).

### One-command leader–follower deploy

Leader–follower teleoperation runs on two machines, each with its own image:

| Side | Machine | Image | Processes |
|---|---|---|---|
| **Leader** | Laptop (leader arm's CAN adapter attached) | `locoman-vla-jazzy` (the **laptop image**, this repo's default) | leader arm controller, PD+gravity controller, `p2p_teleoperation`, joy joint controller |
| **Follower** | Unitree Go2 Jetson (`unitree@192.168.123.18`) | `locoman-vla-jetson` (the **jetson image**, `docker/jetson/`) | follower arm controller, PD+gravity controller, two RealSense cameras |

**Robot installation** (one-time, run from the laptop; prerequisites on the Jetson: Docker + NVIDIA container toolkit + [jetson-containers](https://github.com/dusty-nv/jetson-containers) installed, internet through the router):

```bash
cd docker/jetson
cp jetson.env.example .env    # TODO: set the RealSense camera serial numbers here
./install-robot.sh            # ssh key setup → clone repo → base + jetson image → workspaces
```

**Deploy** (each command activates CAN and attaches to a tmux session with one window per launch — detach with `C-b d`, switch windows with `C-b <number>` or the mouse, kill everything with `C-b : kill-session`):

```bash
docker/jetson/deploy-robot.sh   # follower stack on the Jetson (handles ssh)
docker/deploy-leader.sh         # leader stack on this laptop
```

Both wrap `teleop-session <leader|robot>` inside the respective container; re-running re-attaches to the existing session. CAN activation now runs *inside* the privileged container (`can-activate`), so no host `sudo` is needed on either side. `haptic_teleoperation` comes from the `dls_ros2_manipulation` submodule, pinned to `feature/p2p_haptic_teleoperation` (`95f1493`) and built into the top-level `ros2_ws` (TODO: merge that branch into `main` upstream and re-pin).

### One-command VLA deploy

To run the robot-side stack a VLA policy drives (instead of teleoperation), use:

```bash
docker/jetson/deploy-vla.sh      # VLA robot stack on the Jetson (handles ssh)
```

This wraps `vla-session` inside the Jetson container (same CAN activation and tmux conventions as above; re-running re-attaches). It launches, in one window each:

| Window | Processes |
|---|---|
| `arm-ctrl` | follower arm controller (`start_single_agx_arm_rviz.launch.py`, namespace `follower`) — same as the teleop robot |
| `controllers` | `ros2_control_node` + `/arm_controller` and `/gripper_controller` joint trajectory controllers + `joint_state_broadcaster` (JTC config from the `agx_arm_ros` MoveIt launch) |
| `cameras` | gripper + world RealSense cameras — same as the teleop robot |

Unlike teleop, there is **no PD+gravity controller**: the VLA commands the arm through the `/arm_controller` and `/gripper_controller` trajectory controllers. Their `ros2_control_node` runs `mock_components/GenericSystem` hardware and publishes joint state on `follower/control/joint_states`, which the arm controller node forwards to the real arm over CAN — the same wiring MoveIt uses.

`launch/vla_arm_controllers.launch.py` builds its `robot_description` by running `xacro` on `agx_arm_moveit`'s ros2_control URDF (`agx_arm.urdf.xacro`). `agx_arm_moveit` is built on the Jetson for its `config/`/`launch/` files only — its MoveIt/rviz/warehouse exec_depends are skipped in `rosdep install` since `move_group`, rviz, and the warehouse DB are never launched on the robot.

The manual equivalents of each step are below.

### Host — activate the CAN interface

Run on the host, *before* attaching to the container (requires `sudo`, and the physical CAN adapter plugged in):

```bash
cd piper-ros2-dls/ros2_ws/src/agx_arm_ros/scripts
sudo bash ./can_activate.sh
```

This brings `can0` up at 1 Mbit/s. The container runs with `--network host`, so the interface is visible inside it immediately — re-run this on the host any time the arm is power-cycled or the CAN interface drops. Equivalent, without host `sudo` (the container is privileged and shares the host network namespace): `docker exec locoman_vla_jazzy can-activate` — this is what the deploy scripts use.

### Terminal 1 — arm controller

```bash
./attach.sh
ros2 launch agx_arm_ctrl start_single_agx_arm_rviz.launch.py \
    namespace:=follower \
    tcp_offset:='[0.0, 0.0, 0.14, 0.0, 0.0, 0.0]' \
    arm_type:=piper_l \
    effector_type:=agx_gripper
```

### Terminal 2 — gravity-compensated PD controller

```bash
./attach.sh
ros2 launch agx_arm_pd_g_controller pd_g_controller.launch.py \
    namespace:=follower \
    enable_gravity_compensation:=true \
    use_gripper:=true
```

This is the path `run_controller_ros2.py` and `joystick.py` actually talk to on real hardware: arm/gripper feedback arrives on `/feedback/joint_states`, arm commands go out on `/arm_trajectory_generator`/`/arm_control_signal`, and gripper commands go out on `/gripper_controller/joint_trajectory`.

Verify the feedback input:

```bash
ros2 topic echo /feedback/joint_states --once
ros2 topic hz /feedback/joint_states
```

Keep arm motion disabled during the first locomotion-only robot test unless the controller explicitly requires it.

<details>
<summary>DLS2 blind-state bridge (<code>run-piper-hal</code>) — separate, optional path</summary>

`run-piper-hal` launches `dls2_piper_bridge` (`piper_hal.py`), which activates CAN itself and publishes an `ArmState` message on `/arm_state`. That's the blind-state feed used by the MuJoCo sim-to-sim controller path (§6) and by policy-only pipelines that don't need `/feedback/joint_states`. It is not required for the AgileX-native teleoperation path above, and its self-contained in-container CAN activation has not proven reliable — prefer the host-side `can_activate.sh` step above for real-hardware runs.

```bash
./attach.sh
run-piper-hal
```
</details>

For any *other* arm/teleoperation package not covered above, build or source it through `EXTRA_ROS_WORKSPACES` in `docker/.env`, then launch its node in another attached terminal:

```bash
ros2 launch <arm_package> <arm_launch_file>.launch.py
```

If that package lives in a workspace not yet listed in `.env`, build it manually inside the container first:

```bash
build-extra-workspace /workspace/locoman_vla_deploy/<workspace_name>
```

## 9. Middleware

The validated robot stack uses Fast DDS (`rmw_fastrtps_cpp`) end-to-end, including the Go2 HAL — this matches the robot's own native Fast-DDS-based stack, so there is no cross-RMW boundary to manage:

```bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

Fast DDS pins its transport by IP address, not interface name (unlike CycloneDDS's `<NetworkInterface name=...>`). Inside the container this is handled automatically by `dls-env` via a generated `FASTRTPS_DEFAULT_PROFILES_FILE` (built from `ROBOT_NET_IFACE`, see §4). Confirm with:

```bash
echo "$RMW_IMPLEMENTATION"
echo "$FASTRTPS_DEFAULT_PROFILES_FILE"
ros2 doctor --report | grep -i middleware
```

CycloneDDS is no longer used anywhere in this stack — an earlier version of this deployment used it for the Go2 HAL, but Fast DDS across the board has proven simpler and more reliable (no interop workarounds, no `CYCLONEDDS_URI` XML to hand-write) and has been confirmed end-to-end against the real robot (`/lowstate` → `go2_hal` → `/blind_state` → MUSE → `/base_state`, all flowing cleanly). If you need to test a different RMW for a non-robot-facing process, validate cross-RMW communication, QoS, latency, and command safety before touching hardware.

## 10. Common issues

### `ROS_LOCALHOST_ONLY` is enabled

Physical robot terminals must not use localhost-only discovery:

```bash
unset ROS_LOCALHOST_ONLY
unset ROS_STATIC_PEERS
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
```

A warning containing this text means the shell inherited the simulation configuration:

```text
'localhost_only' is enabled
```

Stop the process, fix the environment, and relaunch it.

### `ros2 topic list` appears to hang

Under CycloneDDS this used to be slow against the Unitree robot's large native DDS graph. Under Fast DDS (current default, see §9), `ros2 topic list` has been confirmed fast and clean against the real robot — if it still hangs, suspect a stale/mismatched `RMW_IMPLEMENTATION` in the shell rather than the DDS graph size. If you do need to sidestep it, test known topics directly:

```bash
timeout 15 ros2 topic echo /blind_state dls2_interface/msg/BlindState --once --qos-reliability best_effort
timeout 15 ros2 topic echo /base_state dls2_interface/msg/BaseState --once --qos-reliability best_effort
```

### `Failed to parse type hash`

Messages such as:

```text
Failed to parse type hash for topic ... from USER_DATA '(null)'
```

were observed under CycloneDDS, caused by native Unitree DDS endpoints without ROS 2 Jazzy type-hash metadata. They were noisy but did not prevent `/lowstate`, `/blind_state`, and `/base_state` communication. Not observed under Fast DDS on the real robot — if it resurfaces, it's still harmless.

### `/lowstate` works but `/blind_state` does not

The Go2 HAL subscription must use sensor-data QoS:

```cpp
rclcpp::SensorDataQoS()
```

The tested `jazzy-deploy` submodule already includes this patch.

### MUSE cannot find Pinocchio headers

The tested MUSE submodule uses the imported target:

```cmake
find_package(pinocchio REQUIRED)
target_link_libraries(state_estimator_plugins pinocchio::pinocchio)
target_link_libraries(state_estimator_node pinocchio::pinocchio)
```

The Docker image also requires:

```text
liburdfdom-headers-dev
```

### ROS setup file fails with `AMENT_TRACE_SETUP_FILES: unbound variable`

Scripts that source ROS setup files must not use `set -u`. Use:

```bash
set -eo pipefail
```

rather than:

```bash
set -euo pipefail
```

### Joystick not visible

```bash
ls -l /dev/input
ros2 run joy joy_enumerate_devices
```

Recreate the container after connecting the device if `/dev/input` was not mounted.

### Root-owned build artifacts

The container runs as root. To restore host ownership after stopping all processes:

```bash
sudo chown -R "$(id -u):$(id -g)" \
  /home/gdessy-iit.local/locoman_vla_deploy
```

## 11. Updating the repository

Update all submodules to the commits pinned by the parent repository:

```bash
git pull
git submodule sync --recursive
git submodule update --init --recursive
```

After pushing a change inside a submodule, update the parent pointer:

```bash
cd <submodule>
git add .
git commit -m "Describe the change"
git push

cd ..
git add <submodule>
git commit -m "Update <submodule>"
git push
```

Do not commit generated `build/`, `install/`, or `log/` directories, `docker/.env`, or exported Docker image archives.

## 12. Validated launch order

```text
1. Start the Docker container
2. run-go2-hal
3. run-muse
4. Verify /blind_state and /base_state
5. run-controller
6. goUp
7. activateRL with zero velocity
8. run-joy
9. Test small commands one axis at a time
10. Start arm teleoperation
```
