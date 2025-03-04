FROM python:alpine

LABEL org.opencontainers.image.source="https://github.com/KingPin/PingPanda"
LABEL org.opencontainers.image.authors="KingPin"
LABEL org.opencontainers.image.description="A Python-based network monitoring tool that checks ping, DNS resolution, website availability, and SSL certificate expiry"
LABEL org.opencontainers.image.url="https://github.com/KingPin/PingPanda/pkgs/container/pingpanda"

# Install system dependencies (needed for both runtime and building some Python packages)
RUN apk add --no-cache \
    bind-tools \
    iputils \
    curl \
    openssl \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev

# Create the logs directory
RUN mkdir -p /logs

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python application
COPY pingpanda.py .

# Make the script executable
RUN chmod +x pingpanda.py

# Add to your Dockerfile
EXPOSE 9090

# Set the entrypoint to run the Python script
ENTRYPOINT ["python", "/app/pingpanda.py"]
