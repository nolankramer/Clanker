ARG BUILD_FROM
FROM python:3.12-slim

WORKDIR /app

# Install system deps + uv
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Clone and install Clanker
RUN git clone --depth 1 https://github.com/nolankramer/clanker.git /tmp/clanker && \
    cp /tmp/clanker/pyproject.toml /tmp/clanker/README.md /app/ && \
    cp -r /tmp/clanker/clanker /app/clanker && \
    cp -r /tmp/clanker/ha_component /app/ha_component && \
    uv pip install --system --no-cache /app && \
    rm -rf /tmp/clanker

# Copy run script
COPY run.sh /run.sh
RUN chmod a+x /run.sh

RUN mkdir -p data config/memory

ENV PYTHONUNBUFFERED=1

CMD ["/run.sh"]
