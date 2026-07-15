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

Set the host interface connected to the Unitree/robot network:

```dotenv
ROBOT_NET_IFACE=enp98s0   # find with: ip -br addr
```

Sanity-check reachability before going further:

```bash
ip route get 192.168.123.18   # Go2 default IP
ping -c 3 192.168.123.18
```

## 3. Build and start the container

```bash
./build-image.sh
./start.sh
./build-workspaces.sh --clean   # first build; drop --clean for incremental rebuilds
```

Build order: Unitree SDK workspace (`unitree_ros2/cyclonedds_ws` — messages/IDL only; the folder name is inherited from upstream and does not dictate the runtime RMW, which is Fast DDS, see §6) → `unitree-ros2-dls/ros2_ws` → `muse/muse_ws` → `piper-ros2-dls/ros2_ws` → `ros2_ws` (dls_ros2_manipulation packages) → anything in `EXTRA_ROS_WORKSPACES`. Details (duplicate-package handling, per-package build quirks): below.

```bash
./attach.sh              # open a container shell — every deploy terminal starts here
./check.sh                # validate installs, imports, and (with --topics) live ROS topics
./stop.sh / ./start.sh    # stop/resume, container persists
./remove-container.sh && ./start.sh   # recreate after changing .env or mounts
```

## 4. Standalone MuJoCo test

Runs the policy directly in MuJoCo, no ROS 2 simulator process.

```bash
./attach.sh
cd /workspace/locoman_vla_deploy/locomanipulation-teleop-isaaclab
python3 deploy/play_mujoco.py
```

In the console: `ictp` for keyboard control (`w`/`s` forward-back, `a`/`d` strafe, `q`/`e` yaw, `0` zero). Do not run this alongside `run_simulator_ros2.py`.

## 5. ROS 2 MuJoCo sim-to-sim

Two attached terminals:

```bash
# Terminal 1 — simulator
source deploy/ros2_localhost_connect.sh
python3 deploy/run_simulator_ros2.py

# Terminal 2 — controller
source deploy/ros2_localhost_connect.sh
python3 deploy/run_controller_ros2.py
```

Controller console: `goUp` → `activateRL` → `ictp`.

```text
simulator  --/blind_state, /base_state, /arm_state-->  controller
controller --/trajectory_generator, /arm_trajectory_generator-->  simulator
```

`ros2_localhost_connect.sh` is sim-only — never source it for physical-robot deployment.

## 6. Physical robot deployment

`attach.sh` already sets `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`, unsets `ROS_LOCALHOST_ONLY`, and pins Fast DDS's transport to `ROBOT_NET_IFACE`'s IP address via a generated `FASTRTPS_DEFAULT_PROFILES_FILE` (Fast DDS whitelists by IP, not interface name, unlike CycloneDDS). This matches the Go2's own native DDS stack — CycloneDDS is no longer used anywhere in this deployment. One attached terminal per process; keep the robot supported for the first test.

**Terminal 1 — Go2 HAL**
```bash
./attach.sh
run-go2-hal   # ≈ python3 unitree-ros2-dls/launch_go2_hal.py
```

**Terminal 2 — MUSE state estimator**
```bash
./attach.sh
run-muse   # ≈ ros2 launch state_estimator state_estimator.launch.py
```

**Verify the state pipeline** (`/lowstate → go2_hal → /blind_state → MUSE → /base_state`) before going further — `ros2 topic list` is slow on the Unitree DDS graph, so check known topics directly:

```bash
timeout 15 ros2 topic echo /blind_state dls2_interface/msg/BlindState --once --qos-reliability best_effort
timeout 15 ros2 topic echo /base_state  dls2_interface/msg/BaseState  --once --qos-reliability best_effort
timeout 10 ros2 topic hz /blind_state --qos-reliability best_effort
timeout 10 ros2 topic hz /base_state  --qos-reliability best_effort
```

Don't start the controller until both topics carry finite, plausible values.

**Terminal 3 — policy controller**
```bash
./attach.sh
run-controller   # ≈ python3 locomanipulation-teleop-isaaclab/deploy/run_controller_ros2.py
```
`goUp` first — check joint directions, symmetry, smooth motion. Then, with zero velocity commanded, `activateRL`. Let it stand under policy control before commanding locomotion.

**Terminal 4 — joystick**
```bash
./attach.sh
run-joy   # ≈ ros2 launch teleop_twist_joy teleop-launch.py joy_config:=xbox
```
Verify with `ros2 topic echo /joy sensor_msgs/msg/Joy`.

| Control | Action |
|---|---|
| D-pad up / down | `goUp` / `goDown` |
| `+` | Toggle RL policy |
| Left stick | Forward/back, strafe |
| Right stick horizontal | Yaw |

Press D-pad up once and let the stand-up interpolation finish before toggling RL.

## 7. Arm teleoperation

The Piper HAL (`piper-ros2-dls`) is built automatically — no `EXTRA_ROS_WORKSPACES` entry needed. Real-hardware teleoperation needs three processes: one on the **host** (CAN activation), two inside the **container**.

### One-command leader–follower deploy

Two machines, two images: the **laptop image** (`locoman-vla-jazzy`, this directory) runs the leader stack; the **jetson image** (`locoman-vla-jetson`, [`jetson/`](./jetson/)) runs the follower stack on the Go2's Jetson.

```bash
# One-time robot install (from the laptop; Jetson needs Docker + NVIDIA
# container toolkit + jetson-containers preinstalled):
cd jetson && cp jetson.env.example .env   # TODO: set RealSense camera serials
./install-robot.sh

# Deploy (each attaches to a tmux session, one window per launch; C-b d detaches):
jetson/deploy-robot.sh   # follower: arm ctrl + PD+g + two RealSense cameras (over ssh)
./deploy-leader.sh       # leader:   arm ctrl + PD+g + p2p_teleoperation
```

Details:
- `install-robot.sh` is idempotent: ssh key setup (`ssh-copy-id`, default password `123`) → clone/update this repo on the robot with only the `piper-ros2-dls` and `dls_ros2_manipulation` submodules → copy `.env` → `jetson-containers build ros:jazzy-ros-base` if the base image is missing → `jetson/build-image.sh` → `jetson/start.sh` → `build-jetson-workspaces` in the container. GitHub access from the robot uses ssh agent forwarding, so your laptop's key must be loaded (`ssh-add -l`).
- The jetson image builds only the follower packages (`piper_sdk`, `agx_arm_msgs`, `agx_arm_description`, `agx_arm_ctrl`, `agx_arm_pd_g_controller`, plus the `dls_ros2_manipulation` packages) — no MoveIt or dls2 bridge. rviz2 is installed because `display.launch.py` hard-requires it; headless it simply exits while the arm nodes keep running.
- CAN activation runs inside the privileged container (`docker exec <name> can-activate`) on both sides — no host `sudo`. Re-run it (or just re-run the deploy script) after power-cycling an arm.
- `teleop-session <leader|robot>` (in both images) creates the tmux session; re-running attaches to it. Kill everything with `C-b : kill-session`, or `jetson/stop.sh` / `./stop.sh`.
- Camera serial numbers come from `GRIPPER_CAMERA_SERIAL` / `WORLD_CAMERA_SERIAL` in `jetson/.env` (TODO: fill in; find them with `rs-enumerate-devices -s` on the robot). They are baked into the container environment — after changing them run `jetson/remove-container.sh` then `jetson/start.sh` (or re-run `install-robot.sh`).
- `haptic_teleoperation` and `manipulation_demo_recorder` come from `dls_ros2_manipulation`, pinned to `feature/p2p_haptic_teleoperation` @ `95f1493` and built through the top-level `ros2_ws` (its `src/dls_ros2_manipulation` symlink keeps colcon artifacts out of the submodule). TODO: merge that branch into `main` upstream and re-pin.

The manual equivalents follow.

**Host — activate the CAN interface** (requires `sudo`, physical CAN adapter plugged in):
```bash
cd piper-ros2-dls/ros2_ws/src/agx_arm_ros/scripts
sudo bash ./can_activate.sh
```
Brings `can0` up at 1 Mbit/s. The container shares the host network (`--network host`), so it's visible immediately. Re-run any time the arm is power-cycled or the interface drops.

**Terminal 1 — arm controller**
```bash
./attach.sh
ros2 launch agx_arm_ctrl start_single_agx_arm_rviz.launch.py \
    namespace:=follower tcp_offset:='[0.0, 0.0, 0.14, 0.0, 0.0, 0.0]' \
    arm_type:=piper_l effector_type:=agx_gripper
```

**Terminal 2 — gravity-compensated PD controller**
```bash
./attach.sh
ros2 launch agx_arm_pd_g_controller pd_g_controller.launch.py \
    namespace:=follower enable_gravity_compensation:=true use_gripper:=true
```

This is the path `run_controller_ros2.py`/`joystick.py` actually use on real hardware: feedback on `/feedback/joint_states`, arm commands on `/arm_trajectory_generator`/`/arm_control_signal`, gripper commands on `/gripper_controller/joint_trajectory`. Verify with `ros2 topic echo /feedback/joint_states --once` / `ros2 topic hz /feedback/joint_states`.

`run-piper-hal` (`dls2_piper_bridge` → `/arm_state`) is a separate, optional blind-state path used by the MuJoCo sim-to-sim controller (§5) — not required here, and its self-contained in-container CAN activation hasn't proven reliable; prefer the host-side step above for real hardware.

For any other arm package, wire it through `EXTRA_ROS_WORKSPACES` (`docker/.env`) and launch normally: `ros2 launch <arm_package> <launch_file>.launch.py`. Keep arm motion disabled during the first locomotion-only test unless the controller requires it.

## 8. Common issues

**`'localhost_only' is enabled` warning** — the shell inherited sim config. `unset ROS_LOCALHOST_ONLY ROS_STATIC_PEERS; export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET`, then relaunch (or just re-run `attach.sh`, which sets this correctly).

**`ros2 topic list` hangs** — was slow under the old CycloneDDS setup on the Go2's large native DDS graph. Under Fast DDS (current default) this has been confirmed fast/clean on the real robot; if it still hangs, check for a stale `RMW_IMPLEMENTATION` in the shell first. Fallback: check known topics directly (see §6).

**`Failed to parse type hash for topic ... USER_DATA '(null)'`** — seen under CycloneDDS; native Unitree DDS endpoints lack Jazzy type-hash metadata. Noisy but harmless, didn't block `/lowstate`, `/blind_state`, `/base_state`. Not observed under Fast DDS.

**`/lowstate` works but `/blind_state` doesn't** — the Go2 HAL subscription must use `rclcpp::SensorDataQoS()`. Already patched in the pinned `jazzy-deploy` submodule.

Container/build-level issues (image build, workspace build failures, Piper's stub `dls2_interface`, `piper_sdk` symlink-install, permissions, joystick device mounts) are in `docker/README.md`.

## 9. Updating

```bash
git pull
git submodule sync --recursive
git submodule update --init --recursive
```

After pushing a change inside a submodule, commit its new pointer in the parent repo too:

```bash
cd <submodule> && git add . && git commit -m "..." && git push
cd .. && git add <submodule> && git commit -m "Update <submodule>" && git push
```

Never commit generated `build/`, `install/`, `log/`, `docker/.env`, or exported image archives.

## 10. Validated launch order

```text
1. Start the Docker container
2. run-go2-hal
3. run-muse
4. Verify /blind_state and /base_state
5. run-controller
6. goUp
7. activateRL with zero velocity
8. run-joy
9. Test one axis at a time
10. Start arm teleoperation only after locomotion is stable
```
