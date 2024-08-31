FROM alpine:latest

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