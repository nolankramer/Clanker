FROM python:3.12-slim AS base

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml ./

# Install dependencies
RUN uv pip install --system --no-cache .

# Copy application code
COPY clanker/ clanker/

# Create data directories
RUN mkdir -p data config/memory

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "clanker.main"]
