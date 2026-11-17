# caas-demo-code-engine

Live demo for the "CaaS at IBM Cloud" talk. One IBM Cloud Code Engine project reacts to two real-world events and shows both on a live feed:

- a **git push**: GitHub calls a webhook on the **app**;
- a **build-result JSON file** dropped in a Cloud Object Storage bucket: a COS **event subscription** starts a **job run**, which validates and enriches the file and posts it to the app over the project's private endpoint.

```
 git push ──► GitHub webhook ───────────────► [ app: build-feed ] ◄── browser (SSE)
                                                      ▲
 JSON ► COS bucket (incoming/) ► subscription ► [ job: build-processor ]
                                                 posts to the app (cluster-local URL)
```

Bad files appear as an orange "rejected" card with the reason and position of the error.

## Layout

| Path | What |
| --- | --- |
| `app/` | Starlette app: feed page, SSE stream, `POST /api/events` (bearer token), `POST /webhook/github` (HMAC signature) |
| `job/` | One-shot Python job: reads `CE_DATA`, fetches the object from COS (max 64 KiB), posts the event |
| `samples/` | `good.json`, `failed.json`, `malformed.json` (`__COMMIT__` is replaced by `demo.sh`) |
| `scripts/` | `build-push.sh`, `setup.sh`, `preflight.sh`, `demo.sh`, `teardown.sh` |
| `tests/` | pytest suite (`pytest`), lint with `ruff check . && ruff format --check .` |

## Prerequisites

- IBM Cloud CLI with the `code-engine` and `cloud-object-storage` plugins, logged in.
- A Code Engine project, a COS instance and a **regional bucket in the same region as the project**.
- A service authorization from the Code Engine project to the COS instance with the **Notifications Manager** role (account admin).
- Docker, and a registry the project can pull from. This demo uses public GHCR images
  (`gh auth refresh -s write:packages`, then make each package public in the GitHub UI).
  Building from source in Code Engine (`--build-source`) also works if your account may create the registry service ID.

## Configuration

All scripts take their settings from the environment; nothing is baked in.

```bash
export RESOURCE_GROUP=<resource group>   # where the Code Engine project lives
export CE_PROJECT=<code engine project>
export COS_INSTANCE=<cos instance name>
export BUCKET=<regional bucket>
export REGION=<region, e.g. ca-tor>
export IMAGE_PREFIX=ghcr.io/<owner>/caas-demo   # images: <prefix>-app, <prefix>-job
```

## Deploy

```bash
scripts/build-push.sh            # builds linux/amd64, pushes :<git sha> and :latest
IMAGE_TAG=<printed tag> scripts/setup.sh
```

`setup.sh` is idempotent. It creates a secret with a random ingest token and webhook secret, the app (`min-scale 1`, `max-scale 1`),
the job, a **Reader-only COS service credential** stored as a secret for the job, and the COS subscription
(`write` events, prefix `incoming/`, suffix `.json`). It prints the feed URL and the webhook payload URL.
The webhook secret is not printed; read it with `ibmcloud ce secret get --name demo-secrets --decode`.

Create the GitHub webhook once: payload URL = `<feed url>/webhook/github`, content type `application/json`, the secret above, **push** events only.

## Before the talk

```bash
scripts/preflight.sh
```

Checks the app, waits for the subscription to be Ready, uploads one sample and asserts its card reaches the feed. Open the feed URL in a browser tab.

## Live

```bash
git commit --allow-empty -m "ship it" && git push   # push card
scripts/demo.sh good                                # green card
scripts/demo.sh failed                              # red card
scripts/demo.sh malformed                           # orange rejected card
```

Measured upload to card: **7 to 11 seconds** (average about 9 s, five runs, measured with a client that polls every ~2 s).
Start the upload, then keep talking.

### Fallback if COS or the network misbehaves

Post an event straight to the app (the token is in the `demo-secrets` secret):

```bash
curl -X POST "$FEED_URL/api/events" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{"kind":"build","status":"passed","repo":"caas-demo","branch":"main","commit":"abc1234","summary":"caas-demo@abc1234 passed in 74s (128/128 tests)","pass_rate":100.0,"builder":"tekton","key":"manual"}'
```

## Notes and limits

- The feed is in memory: redeploying the app clears it. The app is pinned to one instance so every viewer sees the same feed.
- Jobs started by a subscription are deleted by Code Engine after 10 minutes; logs last one hour.
- The job never writes under `incoming/`, so it cannot trigger itself.
- Code Engine service binding was not usable in the account this was built in (it needs permission to create a binding service ID),
  so the job reads `COS_APIKEY` and `COS_RESOURCE_INSTANCE_ID` from a secret. `job/main.py` also understands the `CE_SERVICES` variable a binding provides.

## Teardown

```bash
scripts/teardown.sh   # removes subscription, job, app, secrets, the service key and uploaded objects; never the project, instance or bucket
```
