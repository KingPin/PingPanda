# PingPanda

PingPanda is a versatile monitoring script that performs periodic checks for DNS resolution, ping responses, website availability, and SSL certificate expiry. It logs the results to a specified directory and can send notifications to Slack, Microsoft Teams, and Discord.

## Extended documentation

This README covers core usage and common configuration. Extended documentation (adaptive backoff, filtering, and other deep-dives) has been moved to the `docs/` folder:

- `docs/ADAPTIVE_BACKOFF.md` — detailed behavior and examples for adaptive backoff and circuit breaker
- `docs/FILTERING_FEATURES.md` — filtering options and developer notes

Refer to those files for advanced configuration examples (statistics, flapping detection, persistence).
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
```markdown
# PingPanda

PingPanda is a lightweight network monitoring tool that performs periodic checks for DNS resolution, ICMP ping, website availability, and SSL certificate expiry. It logs results, tracks status for threshold-based alerts, and can send notifications to Slack, Teams, and Discord.

## Quick links

- Documentation folder: `docs/` (adaptive backoff, filtering, developer notes)
- Core code: `pingpanda_core/` (app orchestration, checks, notifications, persistence, stats, backoff)
- CLI entrypoint: `pingpanda.py`

## Features

- DNS resolution checks
- Ping checks (ICMP)
- Website availability checks
- SSL certificate expiry checks
- Configurable logging and rotation
- Notification support: Slack, Teams, Discord
- Optional Prometheus metrics export

## Configuration summary

PingPanda is configured primarily via environment variables. See `pingpanda_core/app.py` and the `docs/` folder for full details. Key variables include:

- `LOG_DIR`, `LOG_FILE`, `LOG_LEVEL`, `MAX_LOG_SIZE`
- `INTERVAL`, `VERBOSE`, `RETRY_COUNT`
- `ENABLE_PING`, `ENABLE_DNS`, `ENABLE_WEBSITE_CHECK`, `ENABLE_SSL_CHECK`
- `DOMAINS`, `PING_IPS`, `CHECK_WEBSITE`, `SSL_CHECK_DOMAINS`
- `SLACK_WEBHOOK_URL`, `TEAMS_WEBHOOK_URL`, `DISCORD_WEBHOOK_URL`, `ALERT_THRESHOLD`

For advanced options (statistics, adaptive backoff, filtering) see the files in `docs/`.

## Getting started

Run locally:

```bash
pip install -r requirements.txt
# PingPanda

PingPanda is a lightweight network monitoring tool that performs periodic checks for DNS resolution, ICMP ping, website availability, and SSL certificate expiry. It logs results, tracks status for threshold-based alerts, and can send notifications to Slack, Microsoft Teams, and Discord.

## Quick links

- Documentation folder: `docs/` (adaptive backoff, filtering, developer notes)
- Core code: `pingpanda_core/` (app orchestration, checks, notifications, persistence, stats, backoff)
- CLI entrypoint: `pingpanda.py`

## Features

- DNS resolution checks
- Ping checks (ICMP)
- Website availability checks
- SSL certificate expiry checks
- Configurable logging and rotation
- Notification support: Slack, Teams, Discord
- Optional Prometheus metrics export

## Configuration summary

PingPanda is configured primarily via environment variables. See `pingpanda_core/app.py` and the `docs/` folder for full details. Key variables include:

- `LOG_DIR`, `LOG_FILE`, `LOG_LEVEL`, `MAX_LOG_SIZE`
- `INTERVAL`, `VERBOSE`, `RETRY_COUNT`
- `ENABLE_PING`, `ENABLE_DNS`, `ENABLE_WEBSITE_CHECK`, `ENABLE_SSL_CHECK`
- `DOMAINS`, `PING_IPS`, `CHECK_WEBSITE`, `SSL_CHECK_DOMAINS`
- `SLACK_WEBHOOK_URL`, `TEAMS_WEBHOOK_URL`, `DISCORD_WEBHOOK_URL`, `ALERT_THRESHOLD`

For advanced options (statistics, adaptive backoff, filtering) see the files in `docs/`.

## Getting started

Run locally:

```bash
pip install -r requirements.txt
python pingpanda.py --verbose
```

Run with Docker Compose:

```bash
docker-compose up -d
```

## Tests & CI

- Tests live under `tests/` and use `pytest`.
- CI workflow `.github/workflows/docker-image.yml` runs linting and tests before building images.

## Contributing

Contributions are welcome. Please open an issue or submit a PR. See the `docs/` folder for developer notes.

## License

This project is licensed under the GNU General Public License v3.0. See the LICENSE file for details.
