#!/usr/bin/env bash
# Run on every boot: starts the existing container (created by docker-setup.sh).
set -euo pipefail
cd "$(dirname "$0")"

set -a
# shellcheck disable=SC1091
source .env
set +a

CONTAINER_NAME="${CONTAINER_NAME:-ein}"

if ! docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  echo "Container '$CONTAINER_NAME' not found. Run ./docker-setup.sh first." >&2
  exit 1
fi

docker start "$CONTAINER_NAME"
