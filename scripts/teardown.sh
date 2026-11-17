#!/usr/bin/env bash
# Remove what setup.sh created. Never deletes the project, COS instance or bucket.
# Requires: RESOURCE_GROUP CE_PROJECT COS_INSTANCE BUCKET REGION
source "$(dirname "$0")/lib.sh"
ce_context

ibmcloud ce subscription cos delete --name "$SUB" --force || echo "subscription ${SUB}: not found"
ibmcloud ce job delete --name "$JOB" --force || echo "job ${JOB}: not found"
ibmcloud ce app delete --name "$APP" --force || echo "app ${APP}: not found"
ibmcloud ce secret delete --name "$SECRET" --force || echo "secret ${SECRET}: not found"
ibmcloud ce secret delete --name "$COS_SECRET" --force || echo "secret ${COS_SECRET}: not found"
ibmcloud resource service-key-delete "$COS_KEY" --force || echo "service key ${COS_KEY}: not found"

keys="$(ibmcloud cos objects --bucket "$BUCKET" --prefix incoming/ --region "$REGION" |
  awk '$1 ~ /^incoming\// {print $1}')"
for key in $keys; do
  ibmcloud cos object-delete --bucket "$BUCKET" --key "$key" --region "$REGION" --force >/dev/null
  echo "deleted ${key}"
done
