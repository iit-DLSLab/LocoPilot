#!/usr/bin/env bash
set -euo pipefail

# Start (or resume) the Jetson teleoperation container. Run ON the robot.
# Mirrors docker/start.sh minus the X11/simulation options: the Jetson runs
# headless and only hosts the follower arm + camera stack.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

IMAGE_NAME="${IMAGE_NAME:-locoman-vla-jetson:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-locoman_vla_jetson}"
ROBOT_WORKSPACE="${ROBOT_WORKSPACE:-$HOME/locoman_vla_deploy}"
CONTAINER_WORKSPACE="${CONTAINER_WORKSPACE:-/workspace/locoman_vla_deploy}"
PIPER_DIR="${PIPER_DIR:-piper-ros2-dls}"
ROBOT_NET_IFACE="${ROBOT_NET_IFACE:-eth0}"
ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
COLCON_JOBS="${COLCON_JOBS:-4}"
GRIPPER_CAMERA_SERIAL="${GRIPPER_CAMERA_SERIAL:-}"
WORLD_CAMERA_SERIAL="${WORLD_CAMERA_SERIAL:-}"

for path in \
    "$ROBOT_WORKSPACE/$PIPER_DIR" \
    "$ROBOT_WORKSPACE/dls_ros2_manipulation" \
    "$ROBOT_WORKSPACE/ros2_ws"; do
    if [[ ! -d "$path" ]]; then
        echo "Required repository directory not found: $path" >&2
        echo "Run docker/jetson/install-robot.sh from the laptop first." >&2
        exit 1
    fi
done

if ! ip link show "$ROBOT_NET_IFACE" >/dev/null 2>&1; then
    echo "Robot interface does not exist: $ROBOT_NET_IFACE" >&2
    echo "Available interfaces:" >&2
    ip -br link >&2
    exit 1
fi

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    echo "Docker image not found: $IMAGE_NAME" >&2
    echo "Build it first with: $SCRIPT_DIR/build-image.sh" >&2
    exit 1
fi

if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    running="$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME")"
    if [[ "$running" != "true" ]]; then
        docker start "$CONTAINER_NAME" >/dev/null
    fi
    echo "Container is running: $CONTAINER_NAME"
    exit 0
fi

args=(
    run -d
    --name "$CONTAINER_NAME"
    --runtime nvidia
    --network host
    --ipc host
    --privileged
    --cap-add SYS_NICE
    --security-opt seccomp=unconfined
    --ulimit rtprio=99
    --ulimit memlock=-1
    -e "WORKSPACE_ROOT=$CONTAINER_WORKSPACE"
    -e "PIPER_DIR=$PIPER_DIR"
    -e "ROBOT_NET_IFACE=$ROBOT_NET_IFACE"
    -e "ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
    -e "RMW_IMPLEMENTATION=rmw_fastrtps_cpp"
    -e "ROS_LOCALHOST_ONLY=0"
    -e "COLCON_JOBS=$COLCON_JOBS"
    -e "GRIPPER_CAMERA_SERIAL=$GRIPPER_CAMERA_SERIAL"
    -e "WORLD_CAMERA_SERIAL=$WORLD_CAMERA_SERIAL"
    -v "$ROBOT_WORKSPACE:$CONTAINER_WORKSPACE:rw"
    -v /dev:/dev
    -v /sys:/sys:ro
    -v /etc/localtime:/etc/localtime:ro
    -w "$CONTAINER_WORKSPACE"
)

docker "${args[@]}" "$IMAGE_NAME" >/dev/null

echo "Started $CONTAINER_NAME"
echo "First build: docker exec -it $CONTAINER_NAME build-jetson-workspaces"
