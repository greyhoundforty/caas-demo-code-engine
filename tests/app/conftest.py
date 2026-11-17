import os

# app.main builds its module-level app from the environment at import time.
os.environ.setdefault("INGEST_TOKEN", "test-ingest-token")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
