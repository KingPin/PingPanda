# PingPanda

**PingPanda** is a high-performance, asynchronous network monitoring tool that performs concurrent checks for DNS resolution, ICMP ping, website availability, and SSL certificate expiry. Built with Python's `asyncio`, it efficiently monitors multiple targets in parallel and sends notifications to Slack, Microsoft Teams, and Discord.

## Features

- **Concurrent Monitoring**: AsyncIO-powered checks run in parallel for maximum efficiency
- **DNS Resolution Checks**: Verify domain name resolution with `aiodns`
- **ICMP Ping Checks**: Monitor host reachability with `aioping`
- **Website Availability**: Check HTTP/HTTPS endpoints with `aiohttp`
- **SSL Certificate Monitoring**: Track certificate expiry dates
- **Smart Notifications**: Threshold-based alerts with recovery notifications
- **Advanced Statistics**: Track uptime, downtime, response times, and flapping detection
- **Adaptive Backoff**: Circuit breaker pattern to reduce load on failing targets
- **Prometheus Metrics**: Optional metrics export for monitoring dashboards
- **Flexible Logging**: Configurable log levels, rotation, and filtering

## Quick Start

### Local Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run with default settings
python pingpanda.py

# Run with verbose output
python pingpanda.py --verbose
```

### Docker Compose

```bash
docker-compose up -d
```

## Requirements

PingPanda requires Python 3.10+ and the following dependencies:

- `aiohttp>=3.9.0` - Async HTTP client for website checks and notifications
- `aiodns>=3.1.0` - Async DNS resolver
- `aioping>=0.4.0` - Async ICMP ping
- `tenacity>=8.2.0` - Retry logic with backoff
- `prometheus-client>=0.17.0` - Metrics export

**Note**: ICMP ping requires elevated privileges. Run with `sudo` or grant `CAP_NET_RAW` capability:
```bash
sudo setcap cap_net_raw+ep $(which python3)
```

## Configuration

PingPanda is configured via environment variables or a configuration file.

### Core Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `INTERVAL` | Check interval in seconds | `15` |
| `RETRY_COUNT` | Number of retry attempts | `3` |
| `JITTER_SECONDS` | Random jitter to add/subtract from interval | `5.0` |
| `VERBOSE` | Enable verbose logging | `false` |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `LOG_DIR` | Directory for log files | `/logs` |
| `LOG_FILE` | Log file name | `pingpanda.log` |
| `LOG_TO_FILE` | Enable file logging | `true` |
| `LOG_TO_TERMINAL` | Enable terminal logging | `true` |
| `MAX_LOG_SIZE` | Maximum log file size in bytes | `1048576` |
| `LOG_BACKUP_COUNT` | Number of rotated log files to keep | `5` |

### Check Targets

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_DNS` | Enable DNS checks | `true` |
| `ENABLE_PING` | Enable ping checks | `true` |
| `ENABLE_WEBSITE_CHECK` | Enable website checks | `false` |
| `ENABLE_SSL_CHECK` | Enable SSL certificate checks | `false` |
| `DOMAINS` | Comma-separated domains for DNS checks | `google.com` |
| `PING_IPS` | Comma-separated IPs for ping checks | `1.1.1.1` |
| `CHECK_WEBSITE` | Comma-separated URLs for website checks | _(empty)_ |
| `SSL_CHECK_DOMAINS` | Comma-separated domains for SSL checks | `google.com` |
| `SUCCESS_HTTP_CODES` | Comma-separated HTTP codes considered successful | `200` |

### Notification Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `SLACK_WEBHOOK_URL` | Slack webhook URL | _(empty)_ |
| `SLACK_CHANNEL` | Slack channel to post to | _(empty)_ |
| `SLACK_USERNAME` | Slack bot username | `PingPanda` |
| `SLACK_ICON_EMOJI` | Slack bot emoji icon | _(empty)_ |
| `TEAMS_WEBHOOK_URL` | Microsoft Teams webhook URL | _(empty)_ |
| `DISCORD_WEBHOOK_URL` | Discord webhook URL | _(empty)_ |
| `DISCORD_USERNAME` | Discord bot username | `PingPanda` |
| `DISCORD_AVATAR_URL` | Discord bot avatar URL | _(empty)_ |
| `ALERT_THRESHOLD` | Consecutive failures before alerting | `3` |
| `NOTIFY_RECOVERY` | Send recovery notifications | `true` |
| `NOTIFICATION_RETRY_ATTEMPTS` | Retry attempts for failed notifications | `3` |
| `NOTIFICATION_RETRY_BACKOFF_SECONDS` | Backoff between notification retries | `1.0` |

### Advanced Features

#### Statistics & Monitoring

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_ADVANCED_STATS` | Enable detailed statistics tracking | `false` |
| `SUMMARY_INTERVAL_SECONDS` | Interval for statistics summaries (0=disabled) | `0` |
| `STORE_STATS_LOG` | Log statistics to file | `false` |
| `STATS_LOG_FILE` | Statistics log file path | `pingpanda_stats.csv` |
| `STATS_LOG_FORMAT` | Log format: `csv` or `json` | `csv` |
| `PERSIST_STATS` | Save statistics across restarts | `false` |
| `STATS_PERSISTENCE_FILE` | File path for persisted statistics | `pingpanda_stats.json` |
| `STATUS_DIR` | Directory for status tracking files | _(derived from LOG_DIR)_ |
| `FLAP_THRESHOLD` | Status changes to trigger flapping alert | `5` |
| `FLAP_WINDOW_SECONDS` | Time window for flapping detection | `300` |

#### Adaptive Backoff & Circuit Breaker

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_ADAPTIVE_BACKOFF` | Enable adaptive backoff for failing targets | `true` |
| `BACKOFF_MIN_SECONDS` | Minimum backoff time | `10.0` |
| `BACKOFF_MAX_SECONDS` | Maximum backoff time | `300.0` |
| `CIRCUIT_BREAKER_THRESHOLD` | Failures to open circuit | `5` |
| `CIRCUIT_BREAKER_COOLDOWN_SECONDS` | Circuit cooldown period | `60.0` |

#### Filtering

| Variable | Description | Default |
|----------|-------------|---------|
| `SHOW_ONLY_SUCCESS` | Show only successful results | `false` |
| `SHOW_ONLY_FAILURE` | Show only failed results | `false` |

#### Prometheus Metrics

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_PROMETHEUS` | Enable Prometheus metrics export | `false` |
| `PROMETHEUS_PORT` | Metrics server port | `9090` |

## Configuration File

You can also use a configuration file:

```bash
python pingpanda.py -c config.conf
```

Example `config.conf`:
```ini
INTERVAL=30
DOMAINS=google.com,github.com,example.com
PING_IPS=1.1.1.1,8.8.8.8
ENABLE_WEBSITE_CHECK=true
CHECK_WEBSITE=https://google.com,https://github.com
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
ALERT_THRESHOLD=2
ENABLE_ADVANCED_STATS=true
SUMMARY_INTERVAL_SECONDS=300
```

## Extended Documentation

For detailed information on advanced features:

- **[Adaptive Backoff](docs/ADAPTIVE_BACKOFF.md)** - Circuit breaker behavior and examples
- **[Filtering Features](docs/FILTERING_FEATURES.md)** - Output filtering options

## Architecture

PingPanda uses an async architecture for efficient concurrent monitoring:

```
pingpanda.py (CLI entry point)
    └── pingpanda_core/
        ├── app.py          - AsyncIO orchestration & event loop
        ├── checks.py       - Async check implementations
        ├── notifications.py - Async notification delivery
        ├── stats.py        - Statistics tracking & flapping detection
        ├── backoff.py      - Adaptive backoff & circuit breaker
        └── persistence.py  - State persistence
```

## Testing

Run the test suite:

```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=pingpanda_core
```

## Docker Deployment

The included `docker-compose.yml` provides a ready-to-use deployment:

```yaml
services:
  pingpanda:
    build: .
    environment:
      - DOMAINS=google.com,github.com
      - PING_IPS=1.1.1.1,8.8.8.8
      - SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
    volumes:
      - ./logs:/logs
    cap_add:
      - NET_RAW  # Required for ICMP ping
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

See the `docs/` folder for developer notes.

## License

This project is licensed under the GNU General Public License v3.0. See the [LICENSE](LICENSE) file for details.
