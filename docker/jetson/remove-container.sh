#!/usr/bin/env bash
set -euo pipefail

# Remove the Jetson teleoperation container (run ON the robot). Needed after
# changing .env values baked into the container environment (camera serials,
# ROS_DOMAIN_ID, ...); recreate it with start.sh.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

CONTAINER_NAME="${CONTAINER_NAME:-locoman_vla_jetson}"
exec docker rm -f "$CONTAINER_NAME"
