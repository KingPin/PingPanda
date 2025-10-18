# PingPanda Examples

This folder contains example configuration files and demo scripts demonstrating advanced PingPanda features.

## Configuration Examples

- **`config_advanced_stats.conf`** - Complete example showing advanced statistics features including:
  - Per-IP ping statistics tracking
  - Periodic statistics summaries
  - CSV/JSON statistics logging with rotation
  - Flapping detection
  - Statistics persistence across restarts

- **`config_backoff_example.conf`** - Example configuration for adaptive backoff and circuit breaker:
  - Backoff timing configuration
  - Circuit breaker thresholds
  - Cooldown periods

## Demo Scripts

- **`demo_advanced_stats.py`** - Demonstrates how to:
  - Parse and analyze PingPanda statistics logs
  - Calculate availability percentages
  - Detect flapping targets
  - Generate reports from logged data

- **`demo_verify_stats.py`** - Validation script for:
  - Verifying statistics persistence files
  - Checking stats log format
  - Testing statistics calculation accuracy

## Usage

To use these configuration files with Docker:

```bash
# Copy the config file to your deployment directory
cp config_advanced_stats.conf /path/to/your/deployment/

# Mount it when running the container
docker run -v /path/to/your/deployment/config_advanced_stats.conf:/app/config.conf \
           -v ./logs:/logs \
           ghcr.io/kingpin/pingpanda:latest
```

For the demo scripts, run them directly with Python after PingPanda has generated some logs:

```bash
python demo_advanced_stats.py
python demo_verify_stats.py
```
