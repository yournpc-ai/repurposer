# Repurposer API (FastAPI + uv). The same image also runs the queue worker —
# see docker-compose.yml (the worker just overrides `command`).
#
# Build context is ./apps/api (self-contained uv project with its own uv.lock).
FROM python:3.11-slim

# ctranslate2 (pulled in by faster-whisper) dlopen's the OpenMP runtime at
# import time; it's the one system lib the manylinux wheels don't bundle.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# uv: reproducible installs straight from the committed uv.lock.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /repo/apps/api

# Install dependencies first (cached layer) from just the lock + manifest.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Then the app code.
COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/repo/apps/api/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
