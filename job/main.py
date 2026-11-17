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


def make_cos(env: Mapping[str, str]):
    """Build a COS client from the service-binding variables."""
    return ibm_boto3.client(
        "s3",
        ibm_api_key_id=env["COS_APIKEY"],
        ibm_service_instance_id=env["COS_RESOURCE_INSTANCE_ID"],
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
