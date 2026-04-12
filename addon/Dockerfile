ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install Python and build tools
RUN apk add --no-cache python3 py3-pip git curl bash

# Remove the externally-managed marker so we can pip install
RUN rm -f /usr/lib/python3.*/EXTERNALLY-MANAGED

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Clone and install Clanker
RUN git clone --depth 1 https://github.com/nolankramer/clanker.git /tmp/clanker && \
    cp /tmp/clanker/pyproject.toml /tmp/clanker/README.md /app/ && \
    cp -r /tmp/clanker/clanker /app/clanker && \
    cp -r /tmp/clanker/ha_component /app/ha_component && \
    uv pip install --system --no-cache --index-strategy unsafe-best-match /app && \
    rm -rf /tmp/clanker

# Copy run script
COPY run.sh /run.sh
RUN chmod a+x /run.sh

# Create data directories
RUN mkdir -p data config/memory

ENV PYTHONUNBUFFERED=1

CMD ["/run.sh"]
