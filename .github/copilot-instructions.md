# PingPanda AI Coding Instructions

## Project Overview
PingPanda is a containerized Python network monitoring tool that performs parallel health checks (DNS, ping, website, SSL) with threshold-based alerting to multiple notification channels (Slack, Teams, Discord) and optional Prometheus metrics export.

## Architecture & Key Components

### Modular Architecture
- **`pingpanda_core/`**: Core application logic split into focused modules
  - `app.py`: Main `PingPanda` class and orchestration with `ThreadPoolExecutor`
  - `checks.py`: Individual check implementations (DNS, Ping, Website, SSL)
  - `notifications.py`: Multi-channel notification manager (Slack, Teams, Discord)
  - `persistence.py`: Status tracking and stats persistence to filesystem
  - `stats.py`: Statistics collection and summary generation
  - `backoff.py`: Adaptive failure tracking and exponential backoff
- **`pingpanda.py`**: Legacy entry point (check if still used or deprecated)
- **`tests/`**: Pytest test suite with coverage for all core modules
- Status tracking via filesystem (`LOG_DIR/status/` directory with per-check files)

### Configuration Pattern
- **Environment-first**: All config via environment variables (no config files by default)
- **Config file support**: Optional `.conf` files for advanced features (see `config_*.conf` examples)
- **NormalizedConfig**: Custom dict wrapper in `app.py` that normalizes keys and supports aliases
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
# Install dependencies (including test dependencies)
pip install -r requirements.txt
pip install flake8 pytest pytest-timeout

# Run tests (configured via pytest.ini)
pytest -q                    # Quick run
pytest -v                    # Verbose output
pytest tests/test_checks.py  # Specific test file

# Run linting
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

# Run application
python pingpanda.py --verbose

# All config via environment variables:
export INTERVAL=5 ENABLE_PROMETHEUS=true PROMETHEUS_PORT=9090
python pingpanda.py
```

### Testing Strategy
- **Test files**: Located in `tests/` directory, one file per core module
- **Pytest config**: `pytest.ini` sets 30s timeout, verbose output, short tracebacks
- **Mock pattern**: Use `DummyApp` class in tests to mock the main application
- **Test naming**: `test_*.py` files with `test_*()` functions
- **CI enforcement**: All tests must pass before Docker image builds (see GitHub Actions)

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
1. **Create check class** in `pingpanda_core/checks.py`:
   - Inherit from base check pattern or create new class
   - Implement check logic with retry loop using `self.app.retry_count`
   - Use `CheckDependencies` for shared dependencies
2. **Update app.py**:
   - Add enable flag in `_load_config()` (e.g., `self.enable_newcheck`)
   - Add targets config with CSV parsing (e.g., `self.newcheck_targets`)
   - Add check to thread pool in `run()` method
3. **Add Prometheus metrics** if `self.enable_prometheus` is true:
   - Define gauges/counters/summaries in `_setup_prometheus()`
   - Update metrics in check implementation
4. **Write tests** in `tests/test_checks.py`:
   - Use `DummyApp` mock and `monkeypatch` for external calls
   - Test success, failure, and retry scenarios
5. **Document** in README.md environment variables section

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

## CI/CD Pipeline (GitHub Actions)

### Workflow: `.github/workflows/docker-image.yml`
**Triggers**: Push/PR to main, releases, manual dispatch
**Jobs**:
1. **lint-and-test**: Runs flake8 and pytest before any build
   - Python 3.11 with pip caching
   - Installs `flake8`, `pytest`, `pytest-timeout`
   - Fails build on syntax errors or test failures
2. **build-and-push**: Multi-architecture Docker build
   - Platforms: `linux/amd64`, `linux/arm64`, `linux/arm/v7`
   - Pushes to `ghcr.io/{owner}/pingpanda` with multiple tags
   - Tags: `latest` (main), `sha-{short}`, branch name, semver (releases)
   - Runs Trivy security scan and uploads to GitHub Security tab

### Branching & PR Guidelines
- **Main branch**: Protected, requires passing CI before merge
- **PR workflow**: Tests run automatically, Docker build runs but doesn't push
- **Releases**: Tag with semver (e.g., `v1.2.0`), triggers full build with version tags
- **Manual testing**: Use `workflow_dispatch` to manually trigger CI pipeline

## Testing Guidance
- **Unit tests**: Run `pytest` before committing (fast, no external dependencies)
- **Integration tests**: Test each check type independently by setting only one `ENABLE_*=true`
- **Iteration**: Use short `INTERVAL=5` for faster feedback loops
- **Status tracking**: Monitor `./logs/status/` directory to verify threshold tracking
- **Notifications**: Test by temporarily setting `ALERT_THRESHOLD=1`
- **Prometheus**: Verify metrics at `http://localhost:9090/metrics` when enabled
- **Coverage**: Add tests in `tests/` directory for any new features
