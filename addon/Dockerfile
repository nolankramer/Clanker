ARG BUILD_FROM
FROM ghcr.io/nolankramer/clanker:latest

# Copy add-on run script
COPY run.sh /run.sh
RUN chmod a+x /run.sh

# Create data directories
RUN mkdir -p /app/data /app/config/memory

ENV PYTHONUNBUFFERED=1

CMD ["/run.sh"]
