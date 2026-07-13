#!/usr/bin/env bash
set -e

# shellcheck disable=SC1091
source /usr/local/bin/dls-env
exec "$@"
