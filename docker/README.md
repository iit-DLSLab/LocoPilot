# ROS 2 Jazzy deployment container

This container is for deploying the policy from `locomanipulation-teleop-isaaclab` together with:

- MUSE state estimation, using the `unitree_sdk` branch;
- `unitree-ros2-dls` for the Unitree GO2 HAL and shared DLS messages;
- optional ROS 2 Jazzy workspaces for the arm/teleoperation stack.

It does **not** clone any repository and does **not** install Isaac Lab or the training stack. All source code remains in your existing host directory:

```text
/home/gdessy-iit.local/locoman_vla_deploy
```

The complete directory is mounted read/write at:

```text
/workspace/locoman_vla_deploy
```

The image contains ROS 2 Jazzy, build dependencies, deployment Python packages, CycloneDDS, RealSense support, PlotJuggler, MuJoCo, ONNX Runtime, PyTorch CPU, and Mink.

## 1. Expected host layout

```text
/home/gdessy-iit.local/locoman_vla_deploy/
├── locomanipulation-teleop-isaaclab/
├── muse/
├── unitree-ros2-dls/
└── docker/                         # this directory
```

Additional ROS workspaces may also live under the same parent directory, for example:

```text
├── piper_ws/
└── teleop_ws/
```

The directory names can be changed in `.env` when your local names differ.

## 2. Prepare the local repositories

The Docker build never modifies or replaces your Git repositories. Confirm that MUSE uses the Unitree branch and initialize the Unitree submodules:

```bash
cd /home/gdessy-iit.local/locoman_vla_deploy

git -C muse switch unitree_sdk
git -C unitree-ros2-dls submodule update --init --recursive
```

Check the repositories:

```bash
git -C locomanipulation-teleop-isaaclab status --short --branch
git -C muse status --short --branch
git -C unitree-ros2-dls status --short --branch
```

## 3. Configure Docker

```bash
cd /home/gdessy-iit.local/locoman_vla_deploy/docker
cp .env.example .env
ip -br address
nano .env
```

At minimum, set the host interface connected to the Unitree network or MikroTik router:

```dotenv
ROBOT_NET_IFACE=enp3s0
```

Use the interface name, not the robot IP address.

The host workspace is already configured as:

```dotenv
HOST_WORKSPACE=/home/gdessy-iit.local/locoman_vla_deploy
```

For an additional arm workspace, add its **container path** to `EXTRA_ROS_WORKSPACES`:

```dotenv
EXTRA_ROS_WORKSPACES=/workspace/locoman_vla_deploy/piper_ws
```

Multiple workspaces are colon-separated:

```dotenv
EXTRA_ROS_WORKSPACES=/workspace/locoman_vla_deploy/piper_ws:/workspace/locoman_vla_deploy/teleop_ws
```

## 4. Build the dependency image

```bash
./build-image.sh
```

The image installs dependencies only. It does not copy or clone the three repositories.

## 5. Start the persistent container

```bash
./start.sh
```

The container uses:

- host networking for ROS 2 and Unitree discovery;
- CycloneDDS bound to `ROBOT_NET_IFACE`;
- `/dev` access for robot, joystick, camera, and serial devices;
- X11 for the MuJoCo viewer currently enabled by `run_controller_ros2.py`;
- a read/write bind mount of the complete local workspace.

`start.sh` starts an existing stopped container rather than deleting it. This preserves any packages installed interactively in that container. To recreate it after changing `.env`, use:

```bash
./remove-container.sh
./start.sh
```

## 6. Build the mounted ROS workspaces

Run this once initially and again after source changes:

```bash
./build-workspaces.sh
```

The build order is:

1. `unitree-ros2-dls/unitree_ros2/cyclonedds_ws`;
2. `unitree-ros2-dls/ros2_ws`;
3. `muse/muse_ws`;
4. workspaces listed in `EXTRA_ROS_WORKSPACES`.

MUSE's duplicate `unitree_go` and `dls2_interface` packages are ignored. The canonical versions come from `unitree-ros2-dls`. MUSE Point-LIO is also omitted because this image targets the proprioceptive estimator needed for deployment.

To remove the generated core build folders before rebuilding:

```bash
./build-workspaces.sh --clean
```

The generated `build/`, `install/`, and `log/` directories remain in your host repositories because the source tree is bind-mounted. Do not reuse build folders created by a different ROS distribution. Use `--clean` when changing from Humble/Conda to Jazzy.

## 7. Validate the environment

```bash
./check.sh
```

After the robot-side nodes are running, also inspect visible topics:

```bash
./check.sh --topics
```

## 8. Open container terminals

Use a separate host terminal for each process:

```bash
cd /home/gdessy-iit.local/locoman_vla_deploy/docker
./attach.sh
```

`attach.sh` sources:

- `/opt/ros/jazzy/setup.bash`;
- the Unitree SDK workspace;
- the DLS HAL workspace;
- MUSE;
- the Python deployment virtual environment;
- all workspaces listed in `EXTRA_ROS_WORKSPACES`.

## 9. Deployment launch sequence

Keep the robot supported and the emergency stop available. Do not activate locomotion until the state topics are valid.

### Terminal 1: Unitree GO2 HAL

```bash
./attach.sh
run-go2-hal
```

### Terminal 2: MUSE

```bash
./attach.sh
run-muse
```

Equivalent command:

```bash
ros2 launch state_estimator state_estimator.launch.py
```

### Terminal 3: arm/teleoperation node

```bash
./attach.sh
ros2 launch <arm_package> <arm_launch_file>.launch.py
```

When the arm package is in an additional workspace not listed in `.env`, build it manually inside the container:

```bash
build-extra-workspace /workspace/locoman_vla_deploy/<workspace_name>
```

Then open a new attached shell.

### Verify controller inputs

```bash
ros2 topic hz /blind_state
ros2 topic hz /base_state
ros2 topic hz /arm_state
```

The current controller subscribes to these topics before publishing commands.

### Terminal 4: policy controller

```bash
./attach.sh
run-controller
```

The helper launches:

```bash
python deploy/run_controller_ros2.py
```

from the mounted `locomanipulation-teleop-isaaclab` checkout.

### Optional joystick

```bash
./attach.sh
run-joy
```

## 10. MuJoCo viewer and headless operation

The upstream `run_controller_ros2.py` currently sets:

```python
self.use_ik_visualizer = True
```

Therefore, the default is:

```dotenv
ENABLE_X11=1
```

For truly headless operation, change the controller to disable the visualizer and then set:

```dotenv
ENABLE_X11=0
```

Recreate the container after changing this setting:

```bash
./remove-container.sh
./start.sh
```

## 11. Network checks

On the host:

```bash
ip -br address
ping 192.168.123.18
```

Inside the container:

```bash
./attach.sh
ip -br address show "$ROBOT_NET_IFACE"
printenv RMW_IMPLEMENTATION ROS_DOMAIN_ID CYCLONEDDS_URI
ros2 topic list
```

The generated `CYCLONEDDS_URI` binds CycloneDDS to the host interface selected in `.env`. Because the container uses `--network host`, the interface has the same name inside and outside Docker.

## 12. Stop or remove the container

Stop while preserving it:

```bash
./stop.sh
```

Start it again:

```bash
./start.sh
```

Delete and recreate it:

```bash
./remove-container.sh
./start.sh
```

Deleting the container does not delete your repositories or ROS build folders because they are stored under the bind-mounted host workspace.

## Common issues

### `librmw_cyclonedds_cpp.so` not found

Always open terminals through `./attach.sh`, then verify:

```bash
ros2 pkg prefix rmw_cyclonedds_cpp
printenv RMW_IMPLEMENTATION
```

### Unitree submodule workspace not found

Run on the host:

```bash
git -C /home/gdessy-iit.local/locoman_vla_deploy/unitree-ros2-dls \
  submodule update --init --recursive
```

### Build folders contain Humble or Conda paths

Rebuild cleanly:

```bash
./build-workspaces.sh --clean
```

### No Unitree topics

Check that:

- the host can reach the robot network;
- `ROBOT_NET_IFACE` is the correct host interface;
- the container uses host networking;
- `run-go2-hal` is active;
- CycloneDDS is selected in every terminal.

### Controller tries to rebuild `deploy/ros2_ws`

`build-workspaces.sh` creates `deploy/ros2_ws/install` as a symlink to the canonical `unitree-ros2-dls/ros2_ws/install`. Re-run the workspace build when the link is missing.

### Permission or ownership of generated files

The container runs as root to simplify access to robot, serial, joystick, and camera devices. Consequently, generated `build/`, `install/`, and `log/` files may be owned by root on the host. To return ownership to your account:

```bash
sudo chown -R "$(id -u):$(id -g)" \
  /home/gdessy-iit.local/locoman_vla_deploy
```

Apply this only when no build or deployment process is running.
