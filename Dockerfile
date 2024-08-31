FROM alpine:latest

org.opencontainers.image.source = "https://github.com/KingPin/PingPanda"
org.opencontainers.image.authors = "KingPin"
org.opencontainers.image.description = "A simple container that pings a list of hosts, ips, and checks DNS, SSL expiry and logs the results"
org.opencontainers.image.url = "https://github.com/KingPin/PingPanda/pkgs/container/pingpanda"

# Install necessary packages
RUN apk add --no-cache bash bind-tools iputils curl

# Copy the script into the container
COPY pingpanda.sh /usr/local/bin/pingpanda.sh

# Make the script executable
RUN chmod +x /usr/local/bin/pingpanda.sh

# Create the logs directory
RUN mkdir -p /logs

# Set the entrypoint to the script
ENTRYPOINT ["/usr/local/bin/pingpanda.sh"]