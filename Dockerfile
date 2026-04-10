FROM python:3.12-slim AS base

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy everything needed for install (hatchling needs source to build)
COPY pyproject.toml README.md ./
COPY clanker/ clanker/

# Install package + dependencies
RUN uv pip install --system --no-cache .

# Create data directories
RUN mkdir -p data config/memory

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "clanker.main"]
