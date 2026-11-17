#!/usr/bin/env bash
# Upload a sample build result to the bucket. Usage: demo.sh [good|failed|malformed]
# Requires: BUCKET REGION
source "$(dirname "$0")/lib.sh"
require_env BUCKET REGION

kind="${1:-good}"
sample="${ROOT}/samples/${kind}.json"
if [[ ! -f "$sample" ]]; then
  echo "usage: demo.sh [good|failed|malformed]" >&2
  exit 2
fi

commit="$(openssl rand -hex 4 | cut -c1-7)"
key="incoming/${kind}-$(date +%s).json"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
sed "s/__COMMIT__/${commit}/" "$sample" >"$tmp"

ibmcloud cos object-put --bucket "$BUCKET" --key "$key" --body "$tmp" \
  --region "$REGION" >/dev/null
echo "uploaded ${key} commit=${commit}"
