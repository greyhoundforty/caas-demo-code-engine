#!/usr/bin/env bash
# Run before going on stage: checks the pieces and one end-to-end event.
# Requires: RESOURCE_GROUP CE_PROJECT COS_INSTANCE BUCKET REGION
source "$(dirname "$0")/lib.sh"
ce_context

url="$(app_url)"

if [[ "$(curl -s -o /dev/null -w '%{http_code}' "${url}/healthz")" != "200" ]]; then
  echo "FAIL: ${url}/healthz is not returning 200" >&2
  exit 1
fi
echo "ok: app is up at ${url}"

ready=0
for _ in $(seq 1 30); do
  if ibmcloud ce subscription cos get --name "$SUB" | grep -Eq '^Ready:[[:space:]]+true'; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" -ne 1 ]]; then
  echo "FAIL: subscription ${SUB} is not Ready after 60s" >&2
  exit 1
fi
echo "ok: subscription ${SUB} is Ready"

out="$("${ROOT}/scripts/demo.sh" good)"
commit="${out##*commit=}"
start=$SECONDS
while ((SECONDS - start < 60)); do
  feed="$(curl -sN --max-time 2 "${url}/events" || true)"
  if [[ "$feed" == *"$commit"* ]]; then
    echo "ok: event ${commit} reached the feed in $((SECONDS - start))s"
    exit 0
  fi
  sleep 1
done
echo "FAIL: event ${commit} did not reach the feed within 60s" >&2
exit 1
