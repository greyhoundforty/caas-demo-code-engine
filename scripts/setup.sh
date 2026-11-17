#!/usr/bin/env bash
# Create or update everything the demo needs in the Code Engine project.
# Requires: RESOURCE_GROUP CE_PROJECT COS_INSTANCE BUCKET REGION IMAGE_PREFIX
# (images must already be pushed and publicly pullable: see scripts/build-push.sh;
# optional IMAGE_TAG, default latest).
# Set SHOW_SECRETS=1 to print the generated webhook secret (first run only).
source "$(dirname "$0")/lib.sh"
require_env IMAGE_PREFIX
ce_context
tag="${IMAGE_TAG:-latest}"

created_secret=0
if exists ibmcloud ce secret get --name "$SECRET"; then
  echo "secret ${SECRET}: exists, reusing"
else
  INGEST_TOKEN="$(openssl rand -hex 24)"
  WEBHOOK_SECRET="$(openssl rand -hex 24)"
  ibmcloud ce secret create --name "$SECRET" \
    --from-literal "INGEST_TOKEN=${INGEST_TOKEN}" \
    --from-literal "WEBHOOK_SECRET=${WEBHOOK_SECRET}" >/dev/null
  created_secret=1
  echo "secret ${SECRET}: created"
fi

app_args=(
  --name "$APP"
  --image "${IMAGE_PREFIX}-app:${tag}"
  --port 8080
  --min-scale 1
  --max-scale 1
  --cpu 0.25
  --memory 0.5G
  --env-from-secret "$SECRET"
)
if exists ibmcloud ce app get --name "$APP"; then
  echo "app ${APP}: updating"
  ibmcloud ce app update "${app_args[@]}"
else
  echo "app ${APP}: creating"
  ibmcloud ce app create "${app_args[@]}"
fi

ingest_url="$(app_local_url)/api/events"
job_args=(
  --name "$JOB"
  --image "${IMAGE_PREFIX}-job:${tag}"
  --cpu 0.25
  --memory 0.5G
  --retrylimit 2
  --maxexecutiontime 120
  --env "INGEST_URL=${ingest_url}"
  --env "COS_ENDPOINT=https://s3.direct.${REGION}.cloud-object-storage.appdomain.cloud"
  --env-from-secret "$SECRET"
)
if exists ibmcloud ce job get --name "$JOB"; then
  echo "job ${JOB}: updating"
  ibmcloud ce job update "${job_args[@]}"
else
  echo "job ${JOB}: creating"
  ibmcloud ce job create "${job_args[@]}"
fi

# COS access for the job: a Reader-only service credential scoped to the demo
# instance, stored in a Code Engine secret (COS_APIKEY, COS_RESOURCE_INSTANCE_ID).
# (A Code Engine service binding would do this, but needs permission to create a
# binding service ID.) The key never touches the terminal.
if exists ibmcloud ce secret get --name "$COS_SECRET"; then
  echo "secret ${COS_SECRET}: exists, reusing"
else
  envfile="$(mktemp)"
  trap 'rm -f "$envfile"' EXIT
  if ! exists ibmcloud resource service-key "$COS_KEY"; then
    ibmcloud resource service-key-create "$COS_KEY" Reader \
      --instance-name "$COS_INSTANCE" >/dev/null
  fi
  ibmcloud resource service-key "$COS_KEY" --output JSON |
    python3 -c '
import json, sys
creds = json.load(sys.stdin)[0]["credentials"]
print("COS_APIKEY=" + creds["apikey"])
print("COS_RESOURCE_INSTANCE_ID=" + creds["resource_instance_id"])
' >"$envfile"
  ibmcloud ce secret create --name "$COS_SECRET" --from-env-file "$envfile" >/dev/null
  echo "secret ${COS_SECRET}: created"
fi
ibmcloud ce job update --name "$JOB" --env-from-secret "$COS_SECRET" >/dev/null

if exists ibmcloud ce subscription cos get --name "$SUB"; then
  echo "subscription ${SUB}: exists"
else
  ibmcloud ce subscription cos create --name "$SUB" \
    --destination-type job --destination "$JOB" \
    --bucket "$BUCKET" --event-type write \
    --prefix incoming/ --suffix .json
fi

url="$(app_url)"
echo
echo "Feed:            ${url}"
echo "Webhook payload: ${url}/webhook/github  (content type application/json, push events)"
if [[ "$created_secret" -eq 1 && "${SHOW_SECRETS:-0}" == "1" ]]; then
  echo "Webhook secret:  ${WEBHOOK_SECRET}"
else
  echo "Webhook secret:  ibmcloud ce secret get --name ${SECRET} --decode"
fi
