#!/usr/bin/env bash
set -euo pipefail

# One-command robot-side installation, run FROM the laptop.
#
# Prerequisites on the robot (Unitree Go2 Jetson, reachable over ssh):
#   - Docker + NVIDIA container toolkit installed
#   - jetson-containers cloned and installed (JETSON_CONTAINERS_DIR in .env)
#   - Internet access through the router
#
# What it does (idempotent — safe to re-run):
#   1. Installs your ssh key on the robot (first run asks for the password once).
#   2. Clones/updates this repo on the robot with only the submodules the
#      robot needs (piper-ros2-dls). GitHub access from
#      the robot uses ssh agent forwarding (-A), so your laptop's key is used.
#   3. Copies docker/jetson/.env to the robot.
#   4. Builds the jetson-containers ros:jazzy-ros-base base image if missing.
#   5. Builds the locoman-vla-jetson image, starts the container, and builds
#      the ROS 2 workspaces inside it.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Missing $ENV_FILE" >&2
    echo "Create it with: cp $SCRIPT_DIR/jetson.env.example $ENV_FILE" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

ROBOT_HOST="${ROBOT_HOST:-192.168.123.18}"
ROBOT_USER="${ROBOT_USER:-unitree}"
ROBOT_WORKSPACE="${ROBOT_WORKSPACE:-/home/$ROBOT_USER/locoman_vla_deploy}"
CONTAINER_NAME="${CONTAINER_NAME:-locoman_vla_jetson}"
BASE_IMAGE="${BASE_IMAGE:-ros:jazzy-ros-base}"
JETSON_CONTAINERS_DIR="${JETSON_CONTAINERS_DIR:-/home/$ROBOT_USER/jetson-containers}"

REMOTE="$ROBOT_USER@$ROBOT_HOST"
REPO_URL="$(git -C "$SCRIPT_DIR" remote get-url origin)"
REPO_BRANCH="$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD)"

# The robot clones from origin, so it can only ever receive what has been
# pushed. Refuse to install from a laptop checkout that origin doesn't have —
# that silently deploys stale code (wrong submodule pins, missing scripts).
echo "==> [0/5] check that origin/$REPO_BRANCH matches this checkout"
git -C "$SCRIPT_DIR" fetch origin "$REPO_BRANCH"
LOCAL_HEAD="$(git -C "$SCRIPT_DIR" rev-parse HEAD)"
REMOTE_HEAD="$(git -C "$SCRIPT_DIR" rev-parse "origin/$REPO_BRANCH")"
if [[ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]]; then
    echo "Local $REPO_BRANCH ($LOCAL_HEAD) differs from origin/$REPO_BRANCH ($REMOTE_HEAD)." >&2
    echo "Commit and push first — the robot installs from origin, not from this working tree." >&2
    exit 1
fi
if [[ -n "$(git -C "$SCRIPT_DIR" status --porcelain --untracked-files=no)" ]]; then
    echo "Warning: this working tree has uncommitted changes; the robot will get origin/$REPO_BRANCH without them." >&2
fi

echo "==> [1/5] ssh key setup ($REMOTE)"
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$REMOTE" true 2>/dev/null; then
    echo "Key-based login not working yet; installing your public key."
    echo "(You will be asked for the robot password once — default: 123)"
    ssh-copy-id "$REMOTE"
fi

echo "==> [2/5] clone/update the repo on the robot"
ssh -A "$REMOTE" \
    REPO_URL="$REPO_URL" \
    REPO_BRANCH="$REPO_BRANCH" \
    ROBOT_WORKSPACE="$ROBOT_WORKSPACE" \
    'bash -s' <<'REMOTE_CLONE'
set -euo pipefail
if [[ ! -d "$ROBOT_WORKSPACE/.git" ]]; then
    git clone --branch "$REPO_BRANCH" "$REPO_URL" "$ROBOT_WORKSPACE"
else
    git -C "$ROBOT_WORKSPACE" fetch origin
    git -C "$ROBOT_WORKSPACE" checkout "$REPO_BRANCH"
    git -C "$ROBOT_WORKSPACE" pull --ff-only origin "$REPO_BRANCH"
fi
# Only the submodules the robot needs; the sim/locomotion ones stay on the laptop.
git -C "$ROBOT_WORKSPACE" submodule sync piper-ros2-dls
git -C "$ROBOT_WORKSPACE" submodule update --init --recursive piper-ros2-dls
REMOTE_CLONE

echo "==> [3/5] copy .env to the robot"
ssh "$REMOTE" mkdir -p "$ROBOT_WORKSPACE/docker/jetson"
scp -q "$ENV_FILE" "$REMOTE:$ROBOT_WORKSPACE/docker/jetson/.env"

echo "==> [4/5] jetson-containers base image ($BASE_IMAGE)"
ssh "$REMOTE" \
    BASE_IMAGE="$BASE_IMAGE" \
    JETSON_CONTAINERS_DIR="$JETSON_CONTAINERS_DIR" \
    'bash -s' <<'REMOTE_BASE'
set -euo pipefail
if docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
    echo "Base image already present: $BASE_IMAGE"
else
    if [[ ! -d "$JETSON_CONTAINERS_DIR" ]]; then
        echo "jetson-containers not found at $JETSON_CONTAINERS_DIR" >&2
        echo "Install it first: https://github.com/dusty-nv/jetson-containers" >&2
        exit 1
    fi
    cd "$JETSON_CONTAINERS_DIR"
    ./jetson-containers build ros:jazzy-ros-base
fi
REMOTE_BASE

echo "==> [5/5] build the jetson image, start the container, build workspaces"
ssh "$REMOTE" \
    ROBOT_WORKSPACE="$ROBOT_WORKSPACE" \
    CONTAINER_NAME="$CONTAINER_NAME" \
    IMAGE_NAME="$IMAGE_NAME" \
    CONTAINER_WORKSPACE="${CONTAINER_WORKSPACE:-/workspace/locoman_vla_deploy}" \
    'bash -s' <<'REMOTE_BUILD'
set -euo pipefail
"$ROBOT_WORKSPACE/docker/jetson/build-image.sh"
# Recreate the container when it predates the freshly built image (or when
# .env changes were copied above), so reruns actually apply image updates.
if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    container_image="$(docker inspect -f '{{.Image}}' "$CONTAINER_NAME")"
    image_id="$(docker image inspect -f '{{.Id}}' "$IMAGE_NAME")"
    if [[ "$container_image" != "$image_id" ]]; then
        echo "Recreating container $CONTAINER_NAME (image changed)"
        docker rm -f "$CONTAINER_NAME" >/dev/null
    fi
fi
"$ROBOT_WORKSPACE/docker/jetson/start.sh"
# From the mounted repo, not the baked copy, so script fixes apply on rerun
# without an image rebuild.
docker exec "$CONTAINER_NAME" \
    bash "$CONTAINER_WORKSPACE/docker/jetson/docker/build-jetson-workspaces"
REMOTE_BUILD

echo
echo "Robot installation complete."
echo "Deploy the teleop stack with: $SCRIPT_DIR/deploy-robot.sh"
