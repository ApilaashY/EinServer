#!/usr/bin/env bash
# First-time setup: builds the image, creates the container and runs it.
# FOLDER and DOWNLOADED_FILE from .env are the HOST paths that get mounted.
set -euo pipefail
cd "$(dirname "$0")"

set -a
# shellcheck disable=SC1091
source .env
set +a

FOLDER="${FOLDER:-movies}"
DOWNLOADED_FILE="${DOWNLOADED_FILE:-downloaded}"
CONTAINER_NAME="${CONTAINER_NAME:-ein}"
DOCKER_CPUS="${DOCKER_CPUS:-2}"
DOCKER_CPU_SHARES="${DOCKER_CPU_SHARES:-256}"
DOCKER_MEMORY="${DOCKER_MEMORY:-1280m}"

mkdir -p "$FOLDER"
mkdir -p "$(dirname "$DOWNLOADED_FILE")"
# A failed earlier run can leave an empty directory here; Docker can't bind it onto a file
if [ -d "$DOWNLOADED_FILE" ]; then
  rmdir "$DOWNLOADED_FILE" || { echo "$DOWNLOADED_FILE is a non-empty directory; remove it and rerun." >&2; exit 1; }
fi
touch "$DOWNLOADED_FILE"

# Docker needs absolute host paths for bind mounts
HOST_MOVIES="$(cd "$FOLDER" && pwd)"
HOST_DOWNLOADED="$(cd "$(dirname "$DOWNLOADED_FILE")" && pwd)/$(basename "$DOWNLOADED_FILE")"

docker build -t ein .

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

# -e flags come after --env-file so the in-container paths override the host paths
docker run -d --name "$CONTAINER_NAME" --restart no \
  --cpus "$DOCKER_CPUS" \
  --cpu-shares "$DOCKER_CPU_SHARES" \
  --memory "$DOCKER_MEMORY" --memory-swap "$DOCKER_MEMORY" \
  --env-file .env \
  -e FOLDER=/movie \
  -e DOWNLOADED_FILE=/data/downloaded \
  -v "$HOST_MOVIES":/movie \
  -v "$HOST_DOWNLOADED":/data/downloaded \
  ein

echo "Container '$CONTAINER_NAME' started. Logs: docker logs -f $CONTAINER_NAME"
