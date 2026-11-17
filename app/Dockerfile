# Build context is the repository root: docker build -f app/Dockerfile .
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/greyhoundforty/caas-demo-code-engine"

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

COPY app app
USER 10001
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
