#!/usr/bin/env bash
set -euo pipefail

# One-command robot-side VLA deploy, run FROM the laptop. Ensures the container
# is running on the Jetson, activates the arm's CAN interface inside it, then
# attaches to the VLA tmux session (follower arm controller + /arm_controller
# and /gripper_controller joint trajectory controllers + RealSense cameras).
#
# Unlike deploy-robot.sh there is no PD+gravity controller: the VLA drives the
# arm through the joint trajectory controllers.
#
# Detach with C-b d (the launches keep running); re-run this script to
# re-attach. Stop everything with: C-b : kill-session  (or jetson/stop.sh).

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
CONTAINER_WORKSPACE="${CONTAINER_WORKSPACE:-/workspace/locoman_vla_deploy}"

REMOTE="$ROBOT_USER@$ROBOT_HOST"

# Helper scripts run from the mounted repo, not the baked image copies, so
# fixes apply without an image rebuild.
echo "==> Starting container and activating CAN on $REMOTE"
ssh "$REMOTE" \
    ROBOT_WORKSPACE="$ROBOT_WORKSPACE" \
    CONTAINER_NAME="$CONTAINER_NAME" \
    CONTAINER_WORKSPACE="$CONTAINER_WORKSPACE" \
    'bash -s' <<'REMOTE_PREP'
set -euo pipefail
"$ROBOT_WORKSPACE/docker/jetson/start.sh"
docker exec "$CONTAINER_NAME" bash "$CONTAINER_WORKSPACE/docker/docker/can-activate"
REMOTE_PREP

echo "==> Attaching to the VLA session (detach with C-b d)"
exec ssh -t "$REMOTE" docker exec -it "$CONTAINER_NAME" \
    bash "$CONTAINER_WORKSPACE/docker/docker/vla-session"
