#!/usr/bin/env sh
set -eu

IMAGE="${1:-}"
case "${IMAGE}" in
  *@sha256:*)
    echo "[base] Using digest-pinned image: ${IMAGE}"
    ;;
  *)
    echo "[FATAL] PYTHON_IMAGE not digest-pinned (${IMAGE}). Pass --build-arg PYTHON_IMAGE=image@sha256:<digest>" >&2
    exit 1
    ;;
esac
