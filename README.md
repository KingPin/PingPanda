# PingPanda

PingPanda is a versatile monitoring script that performs periodic checks for DNS resolution, ping responses, website availability, and SSL certificate expiry. It logs the results to a specified directory and can send notifications to Slack, Microsoft Teams, and Discord.

## Features

- DNS resolution checks
- Ping checks
- Website availability checks
- SSL certificate expiry checks
- Configurable logging to file and terminal
- Log rotation
- Notifications to Slack, Microsoft Teams, and Discord
- Parallel execution of checks using threads
- Status tracking with threshold-based alerting
- Recovery notifications

## Prerequisites

- Docker
- Docker Compose

## Getting Started

### Download the Docker Compose File

You can download the `docker-compose.yml` file using `wget` or `curl`:

Using `wget`:
```bash
wget https://raw.githubusercontent.com/KingPin/PingPanda/main/docker-compose.yml
```

Using `curl`:
```bash
curl -O https://raw.githubusercontent.com/KingPin/PingPanda/main/docker-compose.yml
```

## Configuration

PingPanda can be configured using environment variables. Below is a list of the available environment variables:

### Logging Configuration
- **LOG_DIR**: Directory for logs (default: /logs)
- **LOG_FILE**: Log file name (default: pingpanda.log)
- **LOG_LEVEL**: Logging level (default: INFO)
- **MAX_LOG_SIZE**: Maximum log size in bytes before rotation (default: 1048576 - 1MB)
- **LOG_BACKUP_COUNT**: Number of backup logs to keep (default: 5)
- **LOG_TO_TERMINAL**: Whether to log to the terminal (default: true)
- **LOG_TO_FILE**: Whether to log to a file (default: true)

### Core Settings
- **INTERVAL**: Interval in seconds between checks (default: 15)
- **VERBOSE**: Enable verbose logging (default: false)
- **RETRY_COUNT**: Number of retries for checks before considering them failed (default: 3)

### Check Enablement
- **ENABLE_PING**: Enable ping checks (default: true)
- **ENABLE_DNS**: Enable DNS checks (default: true)
- **ENABLE_WEBSITE_CHECK**: Enable website checks (default: false)
- **ENABLE_SSL_CHECK**: Enable SSL certificate checks (default: false)

### Check Targets
- **DOMAINS**: Comma-separated list of domains to check DNS for (default: google.com)
- **PING_IPS**: Comma-separated list of IPs to ping (default: 1.1.1.1)
- **CHECK_WEBSITE**: Comma-separated list of websites to check (default: empty)
- **SSL_CHECK_DOMAINS**: Comma-separated list of domains to check SSL expiry (default: google.com)

### Check Configuration
- **SUCCESS_HTTP_CODES**: Comma-separated list of HTTP status codes considered successful (default: 200)
- **SSL_WARN_DAYS**: Days threshold for SSL certificate warning (default: 30)
- **SSL_CRITICAL_DAYS**: Days threshold for critical SSL alerts (default: 7)

### Notification Settings
- **SLACK_WEBHOOK_URL**: Slack webhook URL for notifications (default: empty)
- **TEAMS_WEBHOOK_URL**: Microsoft Teams webhook URL for notifications (default: empty)
- **DISCORD_WEBHOOK_URL**: Discord webhook URL for notifications (default: empty)
- **ALERT_THRESHOLD**: Number of consecutive failures before alerting (default: 3)
- **NOTIFY_RECOVERY**: Whether to send notifications when services recover (default: true)

 ## Running the Service

To start the PingPanda service using Docker Compose, run the following command:

```bash
docker-compose up -d
```

This will start the PingPanda service in detached mode. Logs will be stored in the `./logs` directory on your host machine.

### Stopping the Service

To stop the PingPanda service, run the following command:

```bash
docker-compose down
```

## Logs
Logs are stored in the directory specified by the LOG_DIR environment variable. By default, this is the ./logs directory on your host machine when using Docker Compose. The logs are rotated when they reach the size specified by the MAX_LOG_SIZE environment variable.

## Status Tracking
PingPanda tracks the status of your services and only sends alerts when a service has failed for a specified number of consecutive checks (configured via ALERT_THRESHOLD). This prevents alert spam for intermittent issues. Additionally, it can send recovery notifications when a previously failing service comes back online.

Status information is stored in a 'status' subdirectory under the LOG_DIR. This directory contains tracking files for service failures.

## Command Line Usage

When running PingPanda directly (not via Docker), the following command line arguments are available:

```
usage: pingpanda.py [-h] [-c CONFIG] [--verbose] [--version]

PingPanda - Network Monitoring Tool

options:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        Path to config file
  --verbose             Enable verbose output
  --version             show program's version number and exit
```

## Contributing
Contributions are welcome! Please open an issue or submit a pull request.

## License
This project is licensed under the GNU General Public License v3.0. See the LICENSE file for details.
