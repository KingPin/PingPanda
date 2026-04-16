# PingPanda

**PingPanda** is a high-performance, asynchronous network monitor that runs concurrent DNS, ICMP ping, HTTP, and SSL certificate checks, then sends threshold-based alerts to Slack, Microsoft Teams, and Discord. Built on `asyncio`, it monitors hundreds of targets in parallel with a circuit breaker, adaptive backoff, flap detection, and optional Prometheus metrics.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
  - [Docker (recommended)](#docker-recommended)
  - [Docker Compose](#docker-compose)
  - [Local install](#local-install)
- [Configuration](#configuration)
  - [Core settings](#core-settings)
  - [Check targets](#check-targets)
  - [Notifications](#notifications)
  - [Advanced features](#advanced-features)
- [Configuration file](#configuration-file)
- [Prometheus](#prometheus)
- [Architecture](#architecture)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Extended documentation](#extended-documentation)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Concurrent monitoring** — `asyncio.gather()` fan-out over every check type and every target
- **DNS resolution** via `aiodns`
- **ICMP ping** via `aioping`
- **HTTP/HTTPS** availability via `aiohttp`, with configurable success codes
- **SSL certificate expiry** tracking with warn/critical thresholds
- **Smart alerting** — threshold-based alerts and automatic recovery notifications for Slack, Teams, and Discord
- **Circuit breaker + adaptive backoff** — stop hammering hosts that are already down
- **Flapping detection** — suppress noisy alerts when a target rapidly toggles state
- **Uptime / downtime / response-time stats**, optional CSV or JSON stats log, and state persistence across restarts
- **Prometheus metrics** endpoint for Grafana dashboards and alertmanager

## Quick Start

### Docker (recommended)

Prebuilt images are published to GHCR: [`ghcr.io/kingpin/pingpanda:latest`](https://ghcr.io/kingpin/pingpanda).

Minimal one-liner — ping 1.1.1.1, resolve google.com, alert Slack after 3 failures:

```bash
docker run -d --name pingpanda \
  --cap-add=NET_RAW \
  -e PING_IPS=1.1.1.1,8.8.8.8 \
  -e DOMAINS=google.com,github.com \
  -e SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ \
  -e ALERT_THRESHOLD=3 \
  -v $(pwd)/logs:/logs \
  ghcr.io/kingpin/pingpanda:latest
```

Using an env-file (see [example below](#configuration-file)):

```bash
docker run -d --name pingpanda \
  --cap-add=NET_RAW \
  --env-file ./pingpanda.env \
  -v $(pwd)/logs:/logs \
  -p 9090:9090 \
  ghcr.io/kingpin/pingpanda:latest
```

### Docker Compose

A full-featured `compose.yml` is included in the repo root. For task-specific setups (Slack-only, SSL-only, Prometheus stack, etc.), see [`examples/`](examples/README.md). Pulled-image version:

```yaml
services:
  pingpanda:
    image: ghcr.io/kingpin/pingpanda:latest
    container_name: pingpanda
    environment:
      - INTERVAL=15
      - DOMAINS=google.com,github.com
      - PING_IPS=1.1.1.1,8.8.8.8
      - ENABLE_WEBSITE_CHECK=true
      - CHECK_WEBSITE=https://www.google.com,https://api.github.com
      - ENABLE_SSL_CHECK=true
      - SSL_CHECK_DOMAINS=google.com,github.com
      - SSL_WARN_DAYS=30
      - SSL_CRITICAL_DAYS=7
      - SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
      - ALERT_THRESHOLD=3
      - NOTIFY_RECOVERY=true
      - ENABLE_PROMETHEUS=true
      - PROMETHEUS_PORT=9090
      - PROMETHEUS_BIND_ADDRESS=0.0.0.0
    volumes:
      - ./logs:/logs
    ports:
      - "9090:9090"
    cap_drop: [ALL]
    cap_add: [NET_RAW]            # required for ICMP ping
    security_opt: [no-new-privileges:true]
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://127.0.0.1:9090/metrics"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
```

```bash
docker compose up -d
docker compose logs -f pingpanda
```

### Local install

```bash
# Python 3.10+
pip install -r requirements.txt

# Default settings (checks google.com DNS + 1.1.1.1 ping)
python pingpanda.py

# Verbose logging
python pingpanda.py --verbose

# Use a config file
python pingpanda.py -c /path/to/pingpanda.env
```

ICMP requires elevated privileges. Either run with `sudo`, or grant the capability once:

```bash
sudo setcap cap_net_raw+ep $(readlink -f $(which python3))
```

## Configuration

PingPanda reads settings from environment variables, an optional env-file (via `-c /path/to/file`), and `.env` in the working directory. CLI flags (`--verbose`, `--show-only-success`, `--show-only-failure`) override everything.

### Core settings

| Variable | Description | Default |
|----------|-------------|---------|
| `INTERVAL` | Check interval in seconds | `15` |
| `RETRY_COUNT` | Retry attempts per check | `3` |
| `JITTER_SECONDS` | Random jitter added to `INTERVAL` | `5.0` |
| `VERBOSE` | Enable verbose logging | `false` |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |
| `LOG_DIR` | Directory for log files | `/logs` |
| `LOG_FILE` | Log file name | `pingpanda.log` |
| `LOG_TO_FILE` | Write logs to file | `true` |
| `LOG_TO_TERMINAL` | Write logs to stdout | `true` |
| `MAX_LOG_SIZE` | Rotate after N bytes | `1048576` |
| `LOG_BACKUP_COUNT` | Number of rotated logs to keep | `5` |

### Check targets

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_DNS` | Run DNS checks | `true` |
| `ENABLE_PING` | Run ping checks | `true` |
| `ENABLE_WEBSITE_CHECK` | Run HTTP checks | `false` |
| `ENABLE_SSL_CHECK` | Run SSL cert checks | `false` |
| `DOMAINS` | Comma-separated DNS targets | `google.com` |
| `PING_IPS` | Comma-separated ping targets | `1.1.1.1` |
| `CHECK_WEBSITE` | Comma-separated URLs | _(empty)_ |
| `SSL_CHECK_DOMAINS` | Comma-separated hosts for SSL check | `google.com` |
| `SUCCESS_HTTP_CODES` | HTTP codes treated as success | `200` |
| `SSL_WARN_DAYS` | Warn when cert expires within N days | `30` |
| `SSL_CRITICAL_DAYS` | Critical when cert expires within N days | `7` |

### Notifications

| Variable | Description | Default |
|----------|-------------|---------|
| `SLACK_WEBHOOK_URL` | Slack incoming-webhook URL | _(empty)_ |
| `SLACK_CHANNEL` | Override Slack channel | _(empty)_ |
| `SLACK_USERNAME` | Slack bot username | `PingPanda` |
| `SLACK_ICON_EMOJI` | Slack bot emoji (e.g. `:panda_face:`) | _(empty)_ |
| `TEAMS_WEBHOOK_URL` | Microsoft Teams webhook URL | _(empty)_ |
| `DISCORD_WEBHOOK_URL` | Discord webhook URL | _(empty)_ |
| `DISCORD_USERNAME` | Discord bot username | `PingPanda` |
| `DISCORD_AVATAR_URL` | Discord avatar URL | _(empty)_ |
| `ALERT_THRESHOLD` | Consecutive failures before alerting | `3` |
| `NOTIFY_RECOVERY` | Send a "recovered" message | `true` |
| `NOTIFICATION_RETRY_ATTEMPTS` | Retries for failed webhook POST | `3` |
| `NOTIFICATION_RETRY_BACKOFF_SECONDS` | Backoff between retries | `1.0` |

Tip: set all three webhook URLs if you want to fan-out the same alert to Slack, Teams, and Discord simultaneously.

### Advanced features

#### Statistics & flapping

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_ADVANCED_STATS` | Detailed uptime/response-time tracking | `false` |
| `SUMMARY_INTERVAL_SECONDS` | Emit a summary every N seconds (`0` = off) | `0` |
| `STORE_STATS_LOG` | Append results to a stats log | `false` |
| `STATS_LOG_FILE` | Stats log path | `pingpanda_stats.csv` |
| `STATS_LOG_FORMAT` | `csv` or `json` | `csv` |
| `PERSIST_STATS` | Reload stats on restart | `false` |
| `STATS_PERSISTENCE_FILE` | Persisted stats JSON | `pingpanda_stats.json` |
| `STATUS_DIR` | Directory for status files | _(derived from `LOG_DIR`)_ |
| `FLAP_THRESHOLD` | Flips to trigger a flap alert | `5` |
| `FLAP_WINDOW_SECONDS` | Flap-detection window | `300` |

#### Adaptive backoff & circuit breaker

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_ADAPTIVE_BACKOFF` | Slow down checks to failing targets | `true` |
| `BACKOFF_MIN_SECONDS` | Minimum backoff | `10.0` |
| `BACKOFF_MAX_SECONDS` | Maximum backoff | `300.0` |
| `CIRCUIT_BREAKER_THRESHOLD` | Failures before opening circuit | `5` |
| `CIRCUIT_BREAKER_COOLDOWN_SECONDS` | Cooldown before half-open | `60.0` |

See [`docs/ADAPTIVE_BACKOFF.md`](docs/ADAPTIVE_BACKOFF.md) for the full state machine.

#### Output filtering

| Variable | Description | Default |
|----------|-------------|---------|
| `SHOW_ONLY_SUCCESS` | Log only successes | `false` |
| `SHOW_ONLY_FAILURE` | Log only failures | `false` |

#### Prometheus metrics

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_PROMETHEUS` | Expose `/metrics` | `false` |
| `PROMETHEUS_PORT` | Metrics server port | `9090` |
| `PROMETHEUS_BIND_ADDRESS` | Bind address (set to `0.0.0.0` in Docker) | `127.0.0.1` |

## Configuration file

Config files use the same `KEY=value` format as `.env` (parsed by `python-dotenv`). Comments with `#` and quoted values are supported.

Example `pingpanda.env`:

```ini
# --- Core ---
INTERVAL=30
JITTER_SECONDS=5
RETRY_COUNT=3
LOG_LEVEL=INFO

# --- Targets ---
ENABLE_DNS=true
DOMAINS=google.com,github.com,example.com

ENABLE_PING=true
PING_IPS=1.1.1.1,8.8.8.8

ENABLE_WEBSITE_CHECK=true
CHECK_WEBSITE=https://www.google.com,https://api.github.com/status
SUCCESS_HTTP_CODES=200,201,204

ENABLE_SSL_CHECK=true
SSL_CHECK_DOMAINS=google.com,github.com
SSL_WARN_DAYS=30
SSL_CRITICAL_DAYS=7

# --- Alerts ---
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/XXX/YYY
ALERT_THRESHOLD=3
NOTIFY_RECOVERY=true

# --- Stats & resilience ---
ENABLE_ADVANCED_STATS=true
SUMMARY_INTERVAL_SECONDS=300
PERSIST_STATS=true
ENABLE_ADAPTIVE_BACKOFF=true

# --- Metrics ---
ENABLE_PROMETHEUS=true
PROMETHEUS_PORT=9090
```

Run with:

```bash
python pingpanda.py -c ./pingpanda.env
# or via Docker
docker run -d --env-file ./pingpanda.env --cap-add=NET_RAW ghcr.io/kingpin/pingpanda:latest
```

## Prometheus

When `ENABLE_PROMETHEUS=true`, PingPanda serves metrics on `http://<host>:9090/metrics`. Example scrape config:

```yaml
scrape_configs:
  - job_name: pingpanda
    scrape_interval: 30s
    static_configs:
      - targets: ["pingpanda:9090"]
```

## Architecture

```
pingpanda.py                    # CLI entry point, env/file/argv merging
└── pingpanda_core/
    ├── app.py                  # Orchestrator: event loop, config normalization, Prometheus
    ├── checks.py               # DNSCheck / PingCheck / WebsiteCheck / SSLCheck (async + tenacity retries)
    ├── notifications.py        # Slack / Teams / Discord with retry + backoff
    ├── stats.py                # Uptime, response times, flap detection
    ├── backoff.py              # FailureTracker — circuit breaker + adaptive backoff
    └── persistence.py          # JSON state persistence across restarts
```

Design highlights:

- `asyncio.gather()` fans out at both the *check-type* and *per-target* level.
- `CheckDependencies` injects the app + stats manager into each check for testability.
- `NormalizedConfig` resolves env-var aliases (e.g. `summary_interval` → `summary_interval_seconds`) before anything reads them.
- `FailureTracker` opens the circuit after N failures, half-opens after a cooldown, and resets on success.

## Testing

```bash
pip install -r requirements.txt

# Full suite
pytest -q

# Single file / test
pytest tests/test_checks.py
pytest tests/test_checks.py::test_function_name

# Coverage
pytest --cov=pingpanda_core
```

Lint the project the same way CI does:

```bash
flake8 . --count --select=E9,F63,F7,F82 --show-source
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127
```

## Troubleshooting

**`PermissionError` / `Operation not permitted` on ping** — ICMP needs raw sockets. In Docker add `--cap-add=NET_RAW`; on bare metal run `sudo setcap cap_net_raw+ep $(readlink -f $(which python3))`.

**Prometheus endpoint refuses connections in Docker** — the default bind is `127.0.0.1`. Set `PROMETHEUS_BIND_ADDRESS=0.0.0.0` inside the container and publish the port (`-p 9090:9090`).

**Slack/Teams/Discord webhook returns non-2xx** — PingPanda retries `NOTIFICATION_RETRY_ATTEMPTS` times. Enable `--verbose` to see the raw response body.

**Target never recovers after an outage** — the circuit may still be open. Check the logs for `circuit opened` / `circuit half-open`, or lower `CIRCUIT_BREAKER_COOLDOWN_SECONDS`.

**Alert storm from a flapping host** — increase `FLAP_THRESHOLD` or `ALERT_THRESHOLD`, or raise `INTERVAL`.

## Extended documentation

- [`examples/`](examples/README.md) — ready-to-run compose files for common setups (minimal, Slack-only, SSL-only, Prometheus stack, …)
- [`docs/ADAPTIVE_BACKOFF.md`](docs/ADAPTIVE_BACKOFF.md) — circuit-breaker state machine and tuning
- [`docs/FILTERING_FEATURES.md`](docs/FILTERING_FEATURES.md) — output filtering options
- [`docs/README.md`](docs/README.md) — developer notes

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests (`pytest -q` must pass)
4. Submit a pull request

## License

Licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.
