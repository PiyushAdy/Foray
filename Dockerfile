# Foray: build the frontend, bundle it with the API, run as one process.
#
#   docker build -t foray .
#   docker run -p 7420:7420 -v foray-data:/data foray
#
# Demo mode (read-only showcase): pass FORAY_DEMO=1.

FROM node:24-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS backend
# git is required for shallow-cloning repositories added via URL
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml README.md ./
COPY foray/ ./foray/
COPY demo_repos.yaml ./
RUN uv venv /opt/venv && uv pip install --python /opt/venv/bin/python .

COPY --from=frontend /build/dist ./frontend/dist

ENV PATH="/opt/venv/bin:$PATH" \
    FORAY_HOME=/data \
    UV_NO_SYNC=1

VOLUME /data
EXPOSE 7420

CMD ["python", "-m", "foray.cli", "--host", "0.0.0.0", "--port", "7420", "--no-browser"]
