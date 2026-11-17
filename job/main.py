"""Code Engine job: handle one COS write event and post it to the feed app."""

import json
import os
import sys
from collections.abc import Mapping

import httpx
import ibm_boto3
from ibm_botocore.client import Config

from job.build_result import Rejected, decode, enrich, validate

DEFAULT_COS_ENDPOINT = "https://s3.direct.ca-tor.cloud-object-storage.appdomain.cloud"
IAM_ENDPOINT = "https://iam.cloud.ibm.com/identity/token"
MAX_OBJECT_BYTES = 65536
WRITE_OPERATION = "Object:Write"


def parse_ce_data(env: Mapping[str, str]) -> tuple[str, str, str, str]:
    """Return (event_id, operation, bucket, key) from the CE_ID / CE_DATA vars."""
    data = json.loads(env["CE_DATA"])
    return env["CE_ID"], data["operation"], data["bucket"], data["key"]


def cos_credentials(env: Mapping[str, str]) -> tuple[str, str]:
    """Return (apikey, resource_instance_id) from the service binding or plain env.

    A Code Engine service binding exposes credentials as JSON in CE_SERVICES; the
    explicit COS_APIKEY / COS_RESOURCE_INSTANCE_ID variables are the fallback.
    """
    if "CE_SERVICES" in env:
        for entry in json.loads(env["CE_SERVICES"]).get("cloud-object-storage", []):
            creds = entry.get("credentials", {})
            if "apikey" in creds and "resource_instance_id" in creds:
                return creds["apikey"], creds["resource_instance_id"]
    if "COS_APIKEY" in env and "COS_RESOURCE_INSTANCE_ID" in env:
        return env["COS_APIKEY"], env["COS_RESOURCE_INSTANCE_ID"]
    raise RuntimeError("no COS credentials in CE_SERVICES or COS_* environment")


def make_cos(env: Mapping[str, str]):
    """Build a COS client from the service-binding variables."""
    apikey, instance_id = cos_credentials(env)
    return ibm_boto3.client(
        "s3",
        ibm_api_key_id=apikey,
        ibm_service_instance_id=instance_id,
        ibm_auth_endpoint=IAM_ENDPOINT,
        config=Config(signature_version="oauth"),
        endpoint_url=env.get("COS_ENDPOINT", DEFAULT_COS_ENDPOINT),
    )


def fetch_object(
    cos, bucket: str, key: str, limit: int = MAX_OBJECT_BYTES
) -> tuple[bytes, int]:
    """Read an object, refusing anything over `limit` bytes without loading it."""
    too_big = Rejected("object larger than 64 KiB")
    resp = cos.get_object(Bucket=bucket, Key=key)
    if resp.get("ContentLength", 0) > limit:
        raise too_big
    data = resp["Body"].read(limit + 1)
    if len(data) > limit:
        raise too_big
    return data, len(data)


def build_event(event_id: str, key: str, raw: bytes, size: int) -> dict:
    """Turn raw object bytes into a feed event (enriched or rejected)."""
    try:
        event = enrich(validate(decode(raw)), key, size)
    except Rejected as exc:
        return {"kind": "rejected", "key": key, "reason": str(exc), "id": event_id}
    event["id"] = event_id
    return event


def post_event(event: dict, url: str, token: str, client: httpx.Client) -> None:
    resp = client.post(url, json=event, headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()


def main(env: Mapping[str, str] = os.environ, cos=None, client=None) -> int:
    event_id, operation, bucket, key = parse_ce_data(env)
    if operation != WRITE_OPERATION:
        print(f"ignoring {operation} for {key}")
        return 0
    cos = cos or make_cos(env)
    client = client or httpx.Client(timeout=10)
    try:
        raw, size = fetch_object(cos, bucket, key)
        event = build_event(event_id, key, raw, size)
    except Rejected as exc:
        event = {"kind": "rejected", "key": key, "reason": str(exc), "id": event_id}
    try:
        post_event(event, env["INGEST_URL"], env["INGEST_TOKEN"], client)
    except httpx.HTTPError as exc:
        print(f"posting event failed: {exc}", file=sys.stderr)
        return 1
    print(f"posted {event['kind']} event for {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
