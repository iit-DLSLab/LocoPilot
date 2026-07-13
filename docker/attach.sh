#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

CONTAINER_NAME="${CONTAINER_NAME:-locoman_vla_jazzy}"
CONTAINER_WORKSPACE="${CONTAINER_WORKSPACE:-/workspace/locoman_vla_deploy}"

exec docker exec -it \
    -w "$CONTAINER_WORKSPACE" \
    "$CONTAINER_NAME" \
    bash -lc 'source /usr/local/bin/dls-env && exec bash'
