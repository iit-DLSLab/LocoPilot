#!/usr/bin/env bash
set -euo pipefail

# One-command robot-side deploy, run FROM the laptop. Ensures the container
# is running on the Jetson, activates the arm's CAN interface inside it, then
# attaches to the teleop tmux session (follower arm controller +
# gravity-compensated PD controller + RealSense cameras).
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

REMOTE="$ROBOT_USER@$ROBOT_HOST"

echo "==> Starting container and activating CAN on $REMOTE"
ssh "$REMOTE" \
    ROBOT_WORKSPACE="$ROBOT_WORKSPACE" \
    CONTAINER_NAME="$CONTAINER_NAME" \
    'bash -s' <<'REMOTE_PREP'
set -euo pipefail
"$ROBOT_WORKSPACE/docker/jetson/start.sh"
docker exec "$CONTAINER_NAME" can-activate
REMOTE_PREP

echo "==> Attaching to the teleop session (detach with C-b d)"
exec ssh -t "$REMOTE" docker exec -it "$CONTAINER_NAME" teleop-session robot
