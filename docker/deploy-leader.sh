#!/usr/bin/env bash
set -euo pipefail

# One-command leader-side deploy: ensure the container is running, activate
# the CAN interface from inside it, then attach to the teleop tmux session
# (leader arm controller + gravity-compensated PD controller + p2p teleop).
#
# Prerequisites: image built (build-image.sh), workspaces built
# (build-workspaces.sh), leader arm's CAN adapter plugged into this machine.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

CONTAINER_NAME="${CONTAINER_NAME:-locoman_vla_jazzy}"
CONTAINER_WORKSPACE="${CONTAINER_WORKSPACE:-/workspace/locoman_vla_deploy}"

"$SCRIPT_DIR/start.sh"

# Run the helper scripts from the mounted repo, not the copies baked into the
# image, so fixes apply without an image rebuild.
echo "Activating CAN interface..."
docker exec "$CONTAINER_NAME" bash "$CONTAINER_WORKSPACE/docker/docker/can-activate"

exec docker exec -it "$CONTAINER_NAME" \
    bash "$CONTAINER_WORKSPACE/docker/docker/teleop-session" leader
