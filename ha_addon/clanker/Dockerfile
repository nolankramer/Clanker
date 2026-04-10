ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install Python and dependencies
RUN apk add --no-cache python3 py3-pip

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml ./

# Install dependencies
RUN uv pip install --system --no-cache .

# Copy application code
COPY clanker/ clanker/
COPY ha_component/custom_components/clanker/ /ha_custom_component/

# Copy add-on scripts
COPY ha_addon/clanker/run.sh /run.sh
RUN chmod a+x /run.sh

# Create data directories
RUN mkdir -p data config/memory

ENV PYTHONUNBUFFERED=1

CMD ["/run.sh"]
