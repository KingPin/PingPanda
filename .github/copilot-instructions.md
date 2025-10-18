# PingPanda AI Coding Instructions

## Project Overview
PingPanda is a containerized Python network monitoring tool that performs parallel health checks (DNS, ping, website, SSL) with threshold-based alerting to multiple notification channels (Slack, Teams, Discord) and optional Prometheus metrics export.

## Architecture & Key Components

### Single-File Architecture
- **`pingpanda.py`**: Monolithic design containing all monitoring logic in one `PingPanda` class
- Uses threading (`threading.Thread`) for parallel check execution
- Status tracking via filesystem (`LOG_DIR/status/` directory with per-check files)

### Configuration Pattern
- **Environment-first**: All config via environment variables (no config files)
- **Defaults in code**: `_load_config()` method uses `.get()` with inline defaults
- **Boolean parsing**: Always use `.lower() == "true"` pattern for env var booleans
- **CSV parsing**: Multi-value configs use `.split(",")` (e.g., `DOMAINS`, `PING_IPS`)

### Check System Design
Each check type (`check_dns()`, `check_ping()`, `check_website()`, `check_ssl_expiry()`) follows this pattern:
1. Check enable flag (`self.enable_*`)
2. Iterate over targets with retry loop (`self.retry_count`)
3. Time execution with `time.perf_counter()` for millisecond precision
4. Update Prometheus metrics if enabled (`self.enable_prometheus`)
5. Call `send_notification()` with `(message, status, check_type, target)`

### Status Tracking & Alerting
- **Threshold-based**: Alerts only after `ALERT_THRESHOLD` consecutive failures
- **Recovery notifications**: Controlled by `NOTIFY_RECOVERY` flag
- **Persistence**: `_update_status_tracking()` writes failure counts to `{status_dir}/{check_type}_{target}` files
- **Return logic**: Returns `True` only when threshold reached or recovery detected

## Development Workflows

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run with custom config
python pingpanda.py --verbose

# All config via environment variables:
export INTERVAL=5 ENABLE_PROMETHEUS=true PROMETHEUS_PORT=9090
python pingpanda.py
```

### Docker Build & Test
```bash
# Build image (matches GitHub Container Registry naming)
docker build -t ghcr.io/kingpin/pingpanda:latest .

# Run locally with volume mount for logs
docker run -v ./logs:/logs -e ENABLE_PROMETHEUS=true -p 9090:9090 ghcr.io/kingpin/pingpanda:latest

# Use docker-compose for full setup
docker-compose up -d
docker-compose logs -f pingpanda
```

### Adding New Check Types
1. Add enable flag to `_load_config()` (e.g., `self.enable_newcheck`)
2. Add targets config with CSV parsing (e.g., `self.newcheck_targets`)
3. Create `check_newcheck()` method following existing patterns:
   - Early return if disabled
   - Retry loop with `self.retry_count`
   - Call `send_notification()` with proper `check_type` and `target`
   - Add Prometheus metrics if enabled
4. Add thread in `run()` method: `Thread(target=self.check_newcheck)`
5. Update `output_status_summary()` to include new check type
6. Document in README.md environment variables section

## Project Conventions

### Logging
- Use `self.logger` (never `print()`)
- Levels: `.info()` for success, `.error()` for failures, `.debug()` for verbose (controlled by `self.verbose`)
- Format: `"{Check} for {target}: PASS/FAIL (details)"` pattern
- RotatingFileHandler configured in `_setup_logging()` with `MAX_LOG_SIZE` and `LOG_BACKUP_COUNT`

### Notification Format
- Always include hostname via `socket.gethostname()`
- Use emoji prefixes: ✅ for ok, 🔴 for error
- Structure: `*Host:* {hostname}\n*Time:* {formatted_time}\n*Status:* {status}\n*Message:* {message}`
- Color codes: Slack ("good"/"danger"), Teams (hex "00FF00"/"FF0000"), Discord (int 65280/16711680)

### Prometheus Metrics
- Gauges for status (1=OK, 0=ERROR): `self.{type}_status.labels({target}).set(value)`
- Summaries for response times: `self.{type}_response_time.labels({target}).observe(duration_seconds)`
- Counters for errors: `self.{type}_errors.labels({target}).inc()`
- Special metric: `ssl_days_remaining` gauge

### Error Handling
- Use retry loops with `time.sleep(1)` between attempts
- Catch specific exceptions (`socket.gaierror`, `requests.exceptions.RequestException`)
- Log errors only after all retries exhausted
- Never raise exceptions in check methods (log and continue)

## Dependencies & External Integrations

### Required Packages
- `pythonping`: ICMP ping (requires `CAP_NET_RAW` capability in Docker)
- `requests`: HTTP checks with 10-second timeout
- `slack-sdk`: Slack notifications via `WebClient` (not webhooks despite variable name)
- `prometheus-client`: Metrics export via HTTP server on `PROMETHEUS_PORT`

### Docker Security
- Uses `python:alpine` base image
- `cap_drop: ALL` + `cap_add: NET_RAW` for minimal privileges
- `no-new-privileges: true` security option
- `restart: unless-stopped` for resilience

### Notification Webhooks
- Slack: Uses `WebClient.chat_postMessage()` with attachments (not raw webhook POST)
- Teams: POST with `@type: MessageCard` schema
- Discord: POST with `embeds` array
- All wrapped in try-except to prevent notification failures from crashing checks

## Testing Guidance
- Test each check type independently by setting only one `ENABLE_*=true`
- Use short `INTERVAL=5` for faster iteration
- Monitor `./logs/status/` directory to verify threshold tracking
- Test notifications by temporarily setting `ALERT_THRESHOLD=1`
- Verify Prometheus metrics at `http://localhost:9090/metrics` when enabled
