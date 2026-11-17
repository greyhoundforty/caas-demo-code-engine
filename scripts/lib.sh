#!/usr/bin/env bash
# Shared helpers. Source this file; it is not meant to be run directly.
set -euo pipefail

APP=build-feed
JOB=build-processor
SUB=incoming-json
SECRET=demo-secrets

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require_env() {
  local missing=0 name
  for name in "$@"; do
    if [[ -z "${!name:-}" ]]; then
      echo "missing environment variable: ${name}" >&2
      missing=1
    fi
  done
  [[ "$missing" -eq 0 ]] || exit 1
}

# Point the IBM Cloud CLI at the demo's resource group, region and project.
ce_context() {
  require_env RESOURCE_GROUP CE_PROJECT COS_INSTANCE BUCKET REGION
  ibmcloud target -g "$RESOURCE_GROUP" -r "$REGION" >/dev/null
  ibmcloud ce project select --name "$CE_PROJECT" >/dev/null
}

exists() { "$@" >/dev/null 2>&1; }

app_url() { ibmcloud ce app get --name "$APP" --output url; }

# Cluster-local base URL of the app (reachable only inside the project).
app_local_url() {
  ibmcloud ce app get --name "$APP" | awk '/Cluster Local URL/ {print $NF}'
}
