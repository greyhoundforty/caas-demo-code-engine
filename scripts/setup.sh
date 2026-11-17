#!/usr/bin/env bash
# Create or update everything the demo needs in the Code Engine project.
# Requires: RESOURCE_GROUP CE_PROJECT COS_INSTANCE BUCKET REGION
# Set SHOW_SECRETS=1 to print the generated webhook secret (first run only).
source "$(dirname "$0")/lib.sh"
ce_context

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
  --build-source "$ROOT"
  --build-strategy dockerfile
  --build-dockerfile app/Dockerfile
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
  --build-source "$ROOT"
  --build-strategy dockerfile
  --build-dockerfile job/Dockerfile
  --cpu 0.25
  --memory 0.5G
  --retrylimit 2
  --maxexecutiontime 120
  --env "INGEST_URL=${ingest_url}"
  --env-from-secret "$SECRET"
)
if exists ibmcloud ce job get --name "$JOB"; then
  echo "job ${JOB}: updating"
  ibmcloud ce job update "${job_args[@]}"
else
  echo "job ${JOB}: creating"
  ibmcloud ce job create "${job_args[@]}"
fi

if ibmcloud ce job get --name "$JOB" | grep -q "$COS_INSTANCE"; then
  echo "job ${JOB}: COS binding exists"
else
  ibmcloud ce job bind --name "$JOB" --service-instance "$COS_INSTANCE"
fi

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
