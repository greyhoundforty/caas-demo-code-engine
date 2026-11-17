# Build context is the repository root: docker build -f job/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY job/requirements.txt job/requirements.txt
RUN pip install --no-cache-dir -r job/requirements.txt

COPY job job
USER 10001
CMD ["python", "-m", "job.main"]
