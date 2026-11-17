#!/usr/bin/env bash
# Build both images for linux/amd64 (Code Engine's architecture) and push them.
# Requires: IMAGE_PREFIX, e.g. ghcr.io/<owner>/caas-demo  (images: <prefix>-app, <prefix>-job)
# Optional: IMAGE_TAG (default: short git sha). Also tags :latest.
# Log in to the registry first (for GHCR: gh auth refresh -s write:packages, then
# gh auth token | docker login ghcr.io -u <owner> --password-stdin).
source "$(dirname "$0")/lib.sh"
require_env IMAGE_PREFIX

tag="${IMAGE_TAG:-$(git -C "$ROOT" rev-parse --short HEAD)}"

for component in app job; do
  image="${IMAGE_PREFIX}-${component}"
  docker build --platform linux/amd64 -f "${ROOT}/${component}/Dockerfile" \
    -t "${image}:${tag}" -t "${image}:latest" "$ROOT"
  docker push "${image}:${tag}"
  docker push "${image}:latest"
  echo "pushed ${image}:${tag}"
done
echo "IMAGE_TAG=${tag}"
