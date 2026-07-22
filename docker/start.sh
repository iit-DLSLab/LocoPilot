#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Missing $ENV_FILE" >&2
    echo "Create it with: cp $SCRIPT_DIR/.env.example $ENV_FILE" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

IMAGE_NAME="${IMAGE_NAME:-locoman-vla-jazzy:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-locoman_vla_jazzy}"
HOST_WORKSPACE="${HOST_WORKSPACE:-/home/gdessy-iit.local/locoman_vla_deploy}"
CONTAINER_WORKSPACE="${CONTAINER_WORKSPACE:-/workspace/locoman_vla_deploy}"
LOCOMANIP_DIR="${LOCOMANIP_DIR:-locomanipulation-teleop-isaaclab}"
MUSE_DIR="${MUSE_DIR:-muse}"
UNITREE_DLS_DIR="${UNITREE_DLS_DIR:-unitree-ros2-dls}"
PIPER_DIR="${PIPER_DIR:-piper-ros2-dls}"
ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
COLCON_JOBS="${COLCON_JOBS:-4}"
ENABLE_X11="${ENABLE_X11:-1}"
CONTROLLER_RT_PRIORITY="${CONTROLLER_RT_PRIORITY:-0}"
EXTRA_ROS_WORKSPACES="${EXTRA_ROS_WORKSPACES:-}"

for path in \
    "$HOST_WORKSPACE/$LOCOMANIP_DIR" \
    "$HOST_WORKSPACE/$MUSE_DIR" \
    "$HOST_WORKSPACE/$UNITREE_DLS_DIR" \
    "$HOST_WORKSPACE/$PIPER_DIR"; do
    if [[ ! -d "$path" ]]; then
        echo "Required repository directory not found: $path" >&2
        exit 1
    fi
done

if [[ -z "${ROBOT_NET_IFACE:-}" ]]; then
    echo "ROBOT_NET_IFACE is not set in $ENV_FILE" >&2
    exit 1
fi
if ! ip link show "$ROBOT_NET_IFACE" >/dev/null 2>&1; then
    echo "Host interface does not exist: $ROBOT_NET_IFACE" >&2
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
    echo "Attach with: $SCRIPT_DIR/attach.sh"
    exit 0
fi

args=(
    run -d
    --name "$CONTAINER_NAME"
    --network host
    --ipc host
    --privileged
    --cap-add SYS_NICE
    --security-opt seccomp=unconfined
    --ulimit rtprio=99
    --ulimit memlock=-1
    -e "WORKSPACE_ROOT=$CONTAINER_WORKSPACE"
    -e "LOCOMANIP_DIR=$LOCOMANIP_DIR"
    -e "MUSE_DIR=$MUSE_DIR"
    -e "UNITREE_DLS_DIR=$UNITREE_DLS_DIR"
    -e "PIPER_DIR=$PIPER_DIR"
    -e "ROBOT_NET_IFACE=$ROBOT_NET_IFACE"
    -e "ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
    -e "RMW_IMPLEMENTATION=rmw_cyclonedds_cpp"
    -e "ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET"
    -e "COLCON_JOBS=$COLCON_JOBS"
    -e "EXTRA_ROS_WORKSPACES=$EXTRA_ROS_WORKSPACES"
    -e "CONTROLLER_RT_PRIORITY=$CONTROLLER_RT_PRIORITY"
    -e "QT_X11_NO_MITSHM=1"
    -v "$HOST_WORKSPACE:$CONTAINER_WORKSPACE:rw"
    -v /dev:/dev
    -v /sys:/sys:ro
    -v /etc/localtime:/etc/localtime:ro
    -w "$CONTAINER_WORKSPACE"
)

if [[ "$ENABLE_X11" == "1" ]]; then
    if [[ -z "${DISPLAY:-}" ]]; then
        echo "ENABLE_X11=1 but DISPLAY is empty." >&2
        exit 1
    fi
    if command -v xhost >/dev/null 2>&1; then
        xhost +si:localuser:root >/dev/null
    fi
    args+=(
        -e "DISPLAY=$DISPLAY"
        -e "MUJOCO_GL=glfw"
        -v /tmp/.X11-unix:/tmp/.X11-unix:rw
    )
else
    args+=( -e "MUJOCO_GL=egl" )
fi

docker "${args[@]}" "$IMAGE_NAME" >/dev/null

echo "Started $CONTAINER_NAME"
echo "First build: $SCRIPT_DIR/build-workspaces.sh"
echo "Attach:      $SCRIPT_DIR/attach.sh"
