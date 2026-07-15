#!/usr/bin/env bash
set -euo pipefail

# Build the Jetson arm-teleoperation image. Run ON the robot (arm64), after
# jetson-containers has produced the ros:jazzy-ros-base base image.
# The build context is the parent docker/ directory so the in-container
# scripts shared with the laptop image (dls-env, entrypoint, can-activate,
# teleop-session) can be COPY'd.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

IMAGE_NAME="${IMAGE_NAME:-locoman-vla-jetson:latest}"
BASE_IMAGE="${BASE_IMAGE:-ros:jazzy-ros-base}"

if ! docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
    echo "Base image not found: $BASE_IMAGE" >&2
    echo "Build it with jetson-containers first:" >&2
    echo "  cd ~/jetson-containers && jetson-containers build ros:jazzy-ros-base" >&2
    exit 1
fi

exec docker build \
    --build-arg "BASE_IMAGE=$BASE_IMAGE" \
    -f "$SCRIPT_DIR/Dockerfile" \
    -t "$IMAGE_NAME" \
    "$SCRIPT_DIR/.."
