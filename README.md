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
- **🆕 Advanced ping statistics with per-IP tracking**
- **🆕 Periodic statistics summaries with availability calculations**
- **🆕 Statistics logging to CSV/JSON with rotation**
- **🆕 Flapping detection for unstable connections**
- **🆕 Statistics persistence across restarts**
- **🆕 Filtering options to show only success/failure results**

## Prerequisites

- Docker
- Docker Compose

## Getting Started

### Download the Docker Compose File

You can download the `docker-compose.yml` file using `wget` or `curl`:

Using `wget`:
```bash
wget https://raw.githubusercontent.com/KingPin/PingPanda/main/compose.yml
```

Using `curl`:
```bash
curl -O https://raw.githubusercontent.com/KingPin/PingPanda/main/compose.yml
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

### Advanced Statistics Configuration

- **ENABLE_ADVANCED_STATS**: Enable detailed ping statistics tracking (default: false)
- **SUMMARY_INTERVAL**: Interval in seconds for statistics summaries (default: 0 - disabled)
- **ENABLE_STATS_LOGGING**: Enable logging statistics to file (default: false)
- **STATS_LOG_FILE**: Path to statistics log file (default: pingpanda_stats.csv)
- **STATS_LOG_FORMAT**: Format for stats logging - 'csv' or 'json' (default: csv)
- **LOG_ROTATION_SIZE**: Size in bytes for stats log rotation (default: 10485760 - 10MB)
- **FLAPPING_THRESHOLD**: Number of status changes to trigger flapping detection (default: 0 - disabled)
- **FLAPPING_WINDOW**: Time window in seconds for flapping detection (default: 300)
- **PERSIST_STATS**: Save statistics across restarts (default: false)
- **STATS_PERSISTENCE_FILE**: File to store persistent statistics (default: pingpanda_stats.pkl)

### Filtering Options

- **SHOW_ONLY_SUCCESS**: Show only successful check results (default: false)
- **SHOW_ONLY_FAILURE**: Show only failed check results (default: false)

## Advanced Statistics Features

PingPanda now includes comprehensive statistics tracking for ping checks with the following capabilities:

### Per-IP Status Tracking
- **Uptime/Downtime Tracking**: Tracks total uptime and downtime for each IP
- **Status History**: Maintains detailed history of status changes
- **Availability Calculations**: Calculates percentage availability for each IP
- **Current Status Duration**: Shows how long each IP has been in current state

### Periodic Statistics Summaries
- **Configurable Intervals**: Show detailed summaries at specified intervals
- **Overall Statistics**: Total uptime, downtime, and availability across all IPs
- **Per-IP Details**: Individual statistics for each monitored IP
- **Recent Outage History**: Shows recent downtime periods with timestamps

### Statistics Logging
- **CSV/JSON Export**: Log statistics to CSV or JSON files
- **Automatic Rotation**: Rotate log files based on size
- **Historical Data**: Maintain historical statistics for analysis
- **Configurable Fields**: Choose what data to log

### Flapping Detection
- **Unstable Connection Detection**: Identify IPs with frequent status changes
- **Configurable Thresholds**: Set sensitivity for flapping detection
- **Time Window Analysis**: Analyze status changes within specific time periods
- **Visual Indicators**: Clear marking of flapping connections in output

### Statistics Persistence
- **Restart Survival**: Statistics survive application restarts
- **Automatic Save/Load**: Seamlessly save and restore statistics
- **Pickle Format**: Efficient binary storage of statistics data
- **Configurable Location**: Choose where to store persistent data

### Example Configuration

```bash
# Enable advanced statistics
ENABLE_ADVANCED_STATS=true
SUMMARY_INTERVAL=300  # Show summary every 5 minutes

# Enable statistics logging
ENABLE_STATS_LOGGING=true
STATS_LOG_FILE=pingpanda_stats.csv
STATS_LOG_FORMAT=csv

# Enable flapping detection
FLAPPING_THRESHOLD=5  # 5 status changes
FLAPPING_WINDOW=600   # within 10 minutes

# Enable persistence
PERSIST_STATS=true
STATS_PERSISTENCE_FILE=pingpanda_stats.pkl
```

### Testing Advanced Statistics

Use the included test script to see advanced statistics in action:

```bash
python3 test_advanced_stats.py
```

This will run a demonstration with intentionally failing targets to show the statistics features.

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
