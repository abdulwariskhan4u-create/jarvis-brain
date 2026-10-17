#!/usr/bin/env bash
# Fail before building (while production still runs) instead of crashing the runner.
set -euo pipefail
minimum_gib="${DEPLOY_MIN_FREE_GIB:-30}"
if [[ ! "$minimum_gib" =~ ^[1-9][0-9]*$ ]]; then
  echo '::error::DEPLOY_MIN_FREE_GIB must be a positive integer' >&2
  exit 1
fi
minimum_kib=$((minimum_gib * 1024 * 1024))
docker_root=$(docker info --format '{{.DockerRootDir}}')
[[ -d "$docker_root" ]] || { echo '::error::Docker storage directory unavailable' >&2; exit 1; }
workspace="${GITHUB_WORKSPACE:-$PWD}"
# Both paths matter if Docker storage and runner workspace are on different disks.
needs_cleanup=0
for path in "$docker_root" "$workspace"; do
  available=$(df -Pk "$path" | awk 'NR == 2 {print $4}')
  [[ "$available" =~ ^[0-9]+$ ]] || { echo '::error::Cannot measure free disk' >&2; exit 1; }
  echo "Pre-build free space: $path = $available KiB; required $minimum_kib KiB"
  if ((available < minimum_kib)); then needs_cleanup=1; fi
 done
if ((needs_cleanup)); then
  # Only unused build cache. Never delete images, containers, or persistent volumes.
  docker builder prune -af
fi
for path in "$docker_root" "$workspace"; do
  available=$(df -Pk "$path" | awk 'NR == 2 {print $4}')
  if [[ ! "$available" =~ ^[0-9]+$ ]] || ((available < minimum_kib)); then
    echo "::error::Insufficient disk at $path after build-cache cleanup; need ${minimum_gib} GiB. Build/deploy aborted before replacing production." >&2
    exit 1
  fi
 done
