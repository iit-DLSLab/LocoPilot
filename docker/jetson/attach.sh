#!/usr/bin/env bash
set -euo pipefail

# Open an interactive shell in the Jetson teleoperation container.
# Run ON the robot; from the laptop use:
#   ssh -t unitree@<robot> locoman_vla_deploy/docker/jetson/attach.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

CONTAINER_NAME="${CONTAINER_NAME:-locoman_vla_jetson}"
CONTAINER_WORKSPACE="${CONTAINER_WORKSPACE:-/workspace/locoman_vla_deploy}"

exec docker exec -it \
    -w "$CONTAINER_WORKSPACE" \
    "$CONTAINER_NAME" \
    bash -lc 'source /usr/local/bin/dls-env && exec bash'
