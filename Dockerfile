FROM python:3.13-alpine

LABEL org.opencontainers.image.source="https://github.com/KingPin/PingPanda"
LABEL org.opencontainers.image.authors="KingPin"
LABEL org.opencontainers.image.description="A Python-based network monitoring tool that checks ping, DNS resolution, website availability, and SSL certificate expiry"
LABEL org.opencontainers.image.url="https://github.com/KingPin/PingPanda/pkgs/container/pingpanda"

# Global Python runtime tweaks
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install runtime system dependencies
RUN apk add --no-cache \
    bind-tools \
    iputils \
    curl \
    openssl

# Create the logs directory
RUN mkdir -p /logs

# Set working directory
WORKDIR /app

# Install Python dependencies with build tools, then remove build tools in
# the same layer so they do not bloat the final image.
COPY requirements.txt .
RUN apk add --no-cache --virtual .build-deps \
        gcc \
        musl-dev \
        python3-dev \
        libffi-dev \
        openssl-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    apk del .build-deps

# Copy the application code
COPY pingpanda.py ./
COPY pingpanda_core/ ./pingpanda_core/

# Create non-root user and adjust ownership
RUN adduser -D pingpanda && \
    chown -R pingpanda:pingpanda /app /logs

USER pingpanda

# Add to your Dockerfile
EXPOSE 9090

# Set the entrypoint to run the Python script
ENTRYPOINT ["python", "/app/pingpanda.py"]
