# Locomanipulation VLA Deployment

Dockerized ROS 2 Jazzy deployment stack for Unitree Go2 locomotion and arm teleoperation.

This repository combines:

- [`locomanipulation-teleop-isaaclab`](./locomanipulation-teleop-isaaclab): policy deployment, MuJoCo simulation, ROS 2 controller and joystick interface;
- [`muse`](./muse): base-state estimation;
- [`unitree-ros2-dls`](./unitree-ros2-dls): Unitree Go2 HAL and DLS ROS 2 interfaces;
- [`docker`](./docker): ROS 2 Jazzy deployment container and helper scripts.

The three upstream projects are included as Git submodules. The Docker configuration is tracked directly in this repository.

> **Safety:** physical-robot commands can move the legs and arm. Keep the robot supported during the first tests, keep the emergency stop ready, clear the workspace, and verify all state topics before enabling the policy.

---

## 1. Clone

```bash
git clone --recurse-submodules \
  git@github.com:Giovadess/locoman_vla_deploy.git

cd locoman_vla_deploy
```

For an existing clone:

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

Expected layout:

```text
locoman_vla_deploy/
├── docker/
├── locomanipulation-teleop-isaaclab/
├── muse/
└── unitree-ros2-dls/
```

The submodules are pinned to the tested `jazzy-deploy` commits.

---

## 2. Configure Docker

```bash
cd docker
cp .env.example .env
```

Edit `.env` and set the host network interface connected to the Unitree network:

```dotenv
HOST_WORKSPACE=/home/gdessy-iit.local/locoman_vla_deploy
CONTAINER_WORKSPACE=/workspace/locoman_vla_deploy
ROBOT_NET_IFACE=enp98s0
ROS_DOMAIN_ID=0
```

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

Check the route:

```bash
ip route get 192.168.123.18
ping -c 3 192.168.123.18
```

---

## 3. Build and start the container

From `docker/`:

```bash
./build-image.sh
./start.sh
```

Build the mounted ROS 2 workspaces:

```bash
./build-workspaces.sh --clean
```

Use `--clean` for the first build, after changing ROS distributions, or after stale build artifacts. Normal incremental rebuilds can use:

```bash
./build-workspaces.sh
```

The build order is:

1. Unitree CycloneDDS workspace;
2. `unitree-ros2-dls/ros2_ws`;
3. `muse/muse_ws`;
4. optional additional ROS 2 workspaces configured in `.env`.

Open a new container shell with:

```bash
./attach.sh
```

Stop, restart, or recreate the container:

```bash
./stop.sh
./start.sh

# Recreate after changing mounts or .env
./remove-container.sh
./start.sh
```

---

## 4. ROS 2 robot environment

All physical-robot terminals must use CycloneDDS on the robot-facing interface.

The tested environment is:

```bash
unset ROS_LOCALHOST_ONLY
unset ROS_STATIC_PEERS

export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

source /opt/ros/jazzy/setup.bash
source /workspace/locoman_vla_deploy/unitree-ros2-dls/unitree_ros2/cyclonedds_ws/install/setup.bash
source /workspace/locoman_vla_deploy/unitree-ros2-dls/unitree_ros2_connect.bash
source /workspace/locoman_vla_deploy/unitree-ros2-dls/ros2_ws/install/setup.bash
source /workspace/locoman_vla_deploy/muse/muse_ws/install/setup.bash
```

If `/opt/dls/robot_env.bash` is installed by the Docker setup, the equivalent is:

```bash
source /opt/dls/robot_env.bash
```

Verify before launching robot processes:

```bash
echo "$RMW_IMPLEMENTATION"
echo "$ROS_DOMAIN_ID"
echo "$ROS_AUTOMATIC_DISCOVERY_RANGE"
echo "$CYCLONEDDS_URI"
env | grep ROS_LOCALHOST_ONLY
```

Expected:

```text
rmw_cyclonedds_cpp
0
SUBNET
```

`CYCLONEDDS_URI` must reference `enp98s0`, and `ROS_LOCALHOST_ONLY` must not be set.

---

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

---

## 6. ROS 2 MuJoCo sim-to-sim

Use two attached terminals.

### Terminal 1 — simulator

```bash
cd /workspace/locoman_vla_deploy/locomanipulation-teleop-isaaclab
source deploy/ros2_localhost_connect.sh
python3 deploy/run_simulator_ros2.py
```

### Terminal 2 — controller

```bash
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

---

## 7. Physical robot deployment

Use a separate attached terminal for each process. Keep the robot supported for the first test.

### Terminal 1 — Unitree Go2 HAL

```bash
cd /home/gdessy-iit.local/locoman_vla_deploy/docker
./attach.sh
source /opt/dls/robot_env.bash   # when available
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
source /opt/dls/robot_env.bash   # when available
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
source /opt/dls/robot_env.bash   # when available
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
source /opt/dls/robot_env.bash   # when available
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

---

## 8. Arm teleoperation

Build or source the additional arm workspace through `EXTRA_ROS_WORKSPACES` in `docker/.env`, then launch its node in another attached terminal:

```bash
ros2 launch <arm_package> <arm_launch_file>.launch.py
```

Verify the controller input:

```bash
ros2 topic echo /arm_state --once
ros2 topic hz /arm_state
```

Keep arm motion disabled during the first locomotion-only robot test unless the controller explicitly requires it.

---

## 9. Middleware

The tested robot stack uses CycloneDDS:

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
```

Confirm with:

```bash
echo "$RMW_IMPLEMENTATION"
ros2 doctor --report | grep -i middleware
```

Do not switch the Go2 HAL to Fast DDS. Unitree robot communication is validated with CycloneDDS. Other ROS 2 processes may be tested with Fast DDS separately, but cross-RMW communication, QoS, latency, and command safety must be validated before use on hardware.

---

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

The Unitree robot exposes a large native DDS graph. Jazzy may print many warnings while inspecting it. Test known topics directly:

```bash
timeout 15 ros2 topic echo /blind_state dls2_interface/msg/BlindState --once --qos-reliability best_effort
timeout 15 ros2 topic echo /base_state dls2_interface/msg/BaseState --once --qos-reliability best_effort
```

### `Failed to parse type hash`

Messages such as:

```text
Failed to parse type hash for topic ... from USER_DATA '(null)'
```

are caused by native Unitree DDS endpoints without ROS 2 Jazzy type-hash metadata. They are noisy but did not prevent the tested `/lowstate`, `/blind_state`, and `/base_state` communication.

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

---

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

---

## 12. Validated launch order

```text
1. Start the Docker container
2. Start go2_hal
3. Start MUSE
4. Verify /blind_state and /base_state
5. Start the policy controller
6. Run goUp
7. Activate RL with zero velocity
8. Start the joystick
9. Test small commands one axis at a time
10. Start arm teleoperation only after locomotion is stable
```
