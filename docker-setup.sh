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
URL_DOWNLOADS_FILE="${URL_DOWNLOADS_FILE:-url_downloads}"
CONTAINER_NAME="${CONTAINER_NAME:-ein}"
DOCKER_CPUS="${DOCKER_CPUS:-2}"
DOCKER_CPU_SHARES="${DOCKER_CPU_SHARES:-256}"
DOCKER_MEMORY="${DOCKER_MEMORY:-1280m}"
API_PORT="${API_PORT:-0}"
PORT_ARGS=()
# Inside the container "localhost" is the container itself, so point at the Docker host
CONTAINER_JELLYFIN_ADDR="${JELLYFINADDR:-}"
case "$CONTAINER_JELLYFIN_ADDR" in
  localhost*|127.0.0.1*|"") CONTAINER_JELLYFIN_ADDR="host.docker.internal" ;;
esac

[ "$API_PORT" != "0" ] && PORT_ARGS=(-p "$API_PORT:$API_PORT")

mkdir -p "$FOLDER"

# Docker can only bind-mount a file onto a file, so make sure each state file exists as one
prepare_file() {
  mkdir -p "$(dirname "$1")"
  # A failed earlier run can leave an empty directory here
  if [ -d "$1" ]; then
    rmdir "$1" || { echo "$1 is a non-empty directory; remove it and rerun." >&2; exit 1; }
  fi
  touch "$1"
}
prepare_file "$DOWNLOADED_FILE"
prepare_file "$URL_DOWNLOADS_FILE"

# Docker needs absolute host paths for bind mounts
HOST_MOVIES="$(cd "$FOLDER" && pwd)"
HOST_DOWNLOADED="$(cd "$(dirname "$DOWNLOADED_FILE")" && pwd)/$(basename "$DOWNLOADED_FILE")"
HOST_URL_DOWNLOADS="$(cd "$(dirname "$URL_DOWNLOADS_FILE")" && pwd)/$(basename "$URL_DOWNLOADS_FILE")"

docker build -t ein .

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

# -e flags come after --env-file so the in-container paths override the host paths
docker run -d --name "$CONTAINER_NAME" --restart no \
  --cpus "$DOCKER_CPUS" \
  --cpu-shares "$DOCKER_CPU_SHARES" \
  --memory "$DOCKER_MEMORY" --memory-swap "$DOCKER_MEMORY" \
  ${PORT_ARGS[@]+"${PORT_ARGS[@]}"} \
  --env-file .env \
  --add-host host.docker.internal:host-gateway \
  -e JELLYFINADDR="$CONTAINER_JELLYFIN_ADDR" \
  -e FOLDER=/movie \
  -e DOWNLOADED_FILE=/data/downloaded \
  -e URL_DOWNLOADS_FILE=/data/url_downloads \
  -v "$HOST_MOVIES":/movie \
  -v "$HOST_DOWNLOADED":/data/downloaded \
  -v "$HOST_URL_DOWNLOADS":/data/url_downloads \
  ein

echo "Container '$CONTAINER_NAME' started. Logs: docker logs -f $CONTAINER_NAME"
