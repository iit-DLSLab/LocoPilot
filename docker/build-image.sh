#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

IMAGE_NAME="${IMAGE_NAME:-locoman-vla-jazzy:latest}"
BASE_IMAGE="${BASE_IMAGE:-osrf/ros:jazzy-desktop}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}"

exec docker build \
    --build-arg "BASE_IMAGE=$BASE_IMAGE" \
    --build-arg "TORCH_INDEX_URL=$TORCH_INDEX_URL" \
    -t "$IMAGE_NAME" \
    "$SCRIPT_DIR"
