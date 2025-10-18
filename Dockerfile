FROM python:3.13-alpine

LABEL org.opencontainers.image.source="https://github.com/KingPin/PingPanda"
LABEL org.opencontainers.image.authors="KingPin"
LABEL org.opencontainers.image.description="A Python-based network monitoring tool that checks ping, DNS resolution, website availability, and SSL certificate expiry"
LABEL org.opencontainers.image.url="https://github.com/KingPin/PingPanda/pkgs/container/pingpanda"

# Global Python runtime tweaks
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies (runtime and build-time separated)
RUN apk add --no-cache \
    bind-tools \
    iputils \
    curl \
    openssl && \
    apk add --no-cache --virtual .build-deps \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev

# Create the logs directory and stats directory for advanced statistics
RUN mkdir -p /logs /stats

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY pingpanda.py ./
COPY pingpanda_core/ ./pingpanda_core/

# Make the script executable
RUN chmod +x pingpanda.py

# Remove build dependencies to keep the image slim
RUN apk del .build-deps

# Create non-root user and adjust ownership
RUN adduser -D pingpanda && \
    mkdir -p /logs /stats && \
    chown -R pingpanda:pingpanda /app /logs /stats

USER pingpanda

# Add to your Dockerfile
EXPOSE 9090

# Set the entrypoint to run the Python script
ENTRYPOINT ["python", "/app/pingpanda.py"]
