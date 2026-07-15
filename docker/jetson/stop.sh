#!/usr/bin/env bash
set -euo pipefail

# Stop the Jetson teleoperation container. Run ON the robot (or via ssh).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

CONTAINER_NAME="${CONTAINER_NAME:-locoman_vla_jetson}"

docker stop "$CONTAINER_NAME"
echo "Stopped $CONTAINER_NAME (container persists; restart with start.sh)"
