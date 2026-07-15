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

# -t requires a real terminal; drop it when stdin isn't one (e.g. CI, scripts,
# `docker exec -it` otherwise fails outright with "the input device is not a TTY").
docker_exec_flags=(-i)
if [[ -t 0 ]]; then
    docker_exec_flags+=(-t)
fi

# Run the build script from the mounted repo, not the copy baked into the
# image — script fixes then take effect without rebuilding the image.
exec docker exec "${docker_exec_flags[@]}" "$CONTAINER_NAME" \
    bash "$CONTAINER_WORKSPACE/docker/docker/build-dls-workspaces" "$@"
