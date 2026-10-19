# Docker images

Two images run the stack described in the [main README](../README.md):

| Image | Where | Base | Contents |
|---|---|---|---|
| `locoman-vla-jazzy` (this directory) | Workstation (x86_64) | `osrf/ros:jazzy-desktop` | Go2 HAL, MUSE, locomotion controller and simulator, Piper arm stack, `haptic_teleoperation` |
| `locoman-vla-jetson` ([`jetson/`](jetson/)) | Go2 Jetson (arm64) | `ros:jazzy-ros-base` from jetson-containers | Follower Piper arm stack, `haptic_teleoperation`, RealSense cameras, trajectory controllers for policy deployment |

Both containers run privileged with host networking. The repository is mounted at `/workspace/locoman_vla_deploy`, so workspaces are built from the mounted sources and persist across container restarts.

## Host scripts

Workstation (`docker/`):

| Script | Purpose |
|---|---|
| `build-image.sh` | Build the workstation image. |
| `start.sh` | Create or resume the container from `.env`. |
| `build-workspaces.sh [--clean]` | Build all ROS 2 workspaces inside the container. |
| `attach.sh` | Open a shell in the container with the environment sourced. |
| `check.sh [--topics]` | Check installs, Python imports and ROS packages. |
| `deploy-leader.sh` | Activate CAN and attach to the leader teleoperation session. |
| `stop.sh`, `remove-container.sh` | Stop, or remove the container (needed after changing `.env` or mounts). |

Robot (`docker/jetson/`). The first three run on the workstation and reach the robot over ssh; the others run on the robot.

| Script | Purpose |
|---|---|
| `install-robot.sh` | One-time installation: ssh key, clone, base and robot images, container, workspaces. |
| `deploy-robot.sh` | Activate CAN and attach to the follower teleoperation session. |
| `deploy-vla.sh` | Activate CAN and attach to the policy-deployment session. |
| `build-image.sh`, `start.sh`, `attach.sh`, `stop.sh`, `remove-container.sh` | Image and container management on the robot. |

## Container commands

Installed in `/usr/local/bin`. The session and deploy scripts run them from the mounted repository, so script changes apply without rebuilding the image.

| Command | Purpose |
|---|---|
| `dls-env` | Environment sourced by every shell: ROS overlays, CycloneDDS configuration, discovery range. |
| `build-dls-workspaces` / `build-jetson-workspaces` | Workspace builds for the workstation and robot images. |
| `build-extra-workspace <path>` | Build an additional workspace inside the mounted tree. |
| `run-go2-hal`, `run-muse`, `run-controller`, `run-joy` | Locomotion stack processes. |
| `run-piper-hal` | DLS2 arm bridge publishing `/arm_state` (used by the simulation controller path, not by teleoperation). |
| `can-activate [can_name] [bitrate]` | Bring up the arm CAN interface from inside the container. |
| `teleop-session <leader\|robot>` | tmux session with the leader or follower teleoperation stack. |
| `vla-session` | tmux session with the robot-side policy-deployment stack. |
| `check-stack` | Back end of `check.sh`. |

## Configuration

Copy `.env.example` to `.env` (workstation) and `jetson/jetson.env.example` to `jetson/.env` (robot).

| Variable | Image | Meaning |
|---|---|---|
| `HOST_WORKSPACE` | workstation | Host path of this repository; empty uses the current checkout. |
| `ROBOT_NET_IFACE` | both | Interface connected to the robot network. |
| `ROS_DOMAIN_ID` | both | Must match on both machines. |
| `CYCLONEDDS_SUBNET` | both | Subnet CycloneDDS binds to; empty means `192.168.123.0`. |
| `COLCON_JOBS` | both | Parallel colcon workers. |
| `ENABLE_X11` | workstation | Forward X11 for the MuJoCo viewer. |
| `EXTRA_ROS_WORKSPACES` | workstation | Colon-separated container paths of extra workspaces to build and source. |
| `CONTROLLER_RT_PRIORITY` | workstation | Real-time priority for `run-controller` (0 disables). |
| `ROBOT_HOST`, `ROBOT_USER`, `ROBOT_WORKSPACE` | robot | ssh target and clone location on the robot. |
| `JETSON_CONTAINERS_DIR`, `BASE_IMAGE` | robot | jetson-containers checkout and the base image it produces. |
| `GRIPPER_CAMERA_SERIAL`, `WORLD_CAMERA_SERIAL` | robot | RealSense serial numbers (`rs-enumerate-devices -s`). |

Variables are passed to the container when it is created. After editing `.env`, recreate it with `remove-container.sh && start.sh`; on the robot, re-running `install-robot.sh` does this too.

## Workspace build

`build-workspaces.sh` builds, in order:

1. `unitree-ros2-dls/unitree_ros2/cyclonedds_ws`: Unitree message definitions.
2. `unitree-ros2-dls/ros2_ws`: Go2 HAL and the canonical `dls2_interface`.
3. `muse/muse_ws`: MUSE, without its own copies of `unitree_go` and `dls2_interface`, and without Point-LIO.
4. `piper-ros2-dls/ros2_ws`: Piper arm packages. Its `dls2_interface` is an incomplete stub and is never built.
5. `ros2_ws`: `haptic_teleoperation`.
6. Each workspace in `EXTRA_ROS_WORKSPACES`.

`piper_sdk`, `agx_arm_pd_g_controller` and `haptic_teleoperation` are built without `--symlink-install`: the first points its package directory outside the package tree, and the other two generate a parameters module while `setup.py` runs.

The robot image builds only the follower packages (`piper_sdk`, `agx_arm_msgs`, `agx_arm_description`, `agx_arm_ctrl`, `agx_arm_pd_g_controller`, `agx_arm_moveit` for its configuration files) and `haptic_teleoperation`. rviz2 is installed because the arm launch file always declares it; without a display it exits and the arm nodes keep running.

## Robot installation details

- `install-robot.sh` uses the workstation's `origin` URL and current branch, and refuses to run if that branch is not pushed. With an ssh `origin`, GitHub access from the robot uses ssh agent forwarding, so your key must be loaded (`ssh-add -l`).
- The first run asks for the robot's ssh password once (Unitree default: `123`).
- Only the `piper-ros2-dls` submodule is initialized on the robot.

## Troubleshooting

**Root-owned build artifacts.** The containers run as root. To restore ownership on the host after stopping all processes: `sudo chown -R "$(id -u):$(id -g)" <repository>`.

**`AMENT_TRACE_SETUP_FILES: unbound variable`.** Scripts that source ROS setup files must use `set -eo pipefail`, not `set -u`.

**MUSE cannot find Pinocchio headers.** MUSE must link the imported `pinocchio::pinocchio` target, as the pinned submodule does. The image also needs `liburdfdom-headers-dev`.

**Joystick not visible.** Check `ls -l /dev/input` and `ros2 run joy joy_enumerate_devices`. Recreate the container if the device was connected after it started.

**`ModuleNotFoundError: ..._parameters`.** A package that uses `generate_parameter_library_py` was built with `--symlink-install`. Rebuild with `build-workspaces.sh --clean`.

**rosdep fails with missing apt packages.** The images remove the apt lists. `build-jetson-workspaces` refreshes them; elsewhere, run `apt-get update` in the container before rosdep.
