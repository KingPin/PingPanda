"""CLI entrypoint for PingPanda monitoring."""

import argparse
import os
import sys
from typing import Dict

from pingpanda_core import PingPanda as PingPandaApp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PingPanda - Network Monitoring Tool")
    parser.add_argument("-c", "--config", help="Path to config file")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--show-only-success", action="store_true", help="Show only successful check results")
    parser.add_argument("--show-only-failure", action="store_true", help="Show only failed check results")
    parser.add_argument("--version", action="version", version="PingPanda v1.1.0")
    return parser.parse_args()


_KNOWN_ENV_KEYS = {
    "LOG_DIR", "LOG_FILE", "LOG_LEVEL", "LOG_TO_TERMINAL", "LOG_TO_FILE",
    "MAX_LOG_SIZE", "LOG_BACKUP_COUNT",
    "INTERVAL", "VERBOSE", "RETRY_COUNT", "JITTER_SECONDS",
    "ENABLE_PING", "ENABLE_DNS", "ENABLE_WEBSITE_CHECK", "ENABLE_SSL_CHECK",
    "DOMAINS", "PING_IPS", "CHECK_WEBSITE", "SSL_CHECK_DOMAINS",
    "SUCCESS_HTTP_CODES", "SSL_WARN_DAYS", "SSL_CRITICAL_DAYS",
    "SLACK_WEBHOOK_URL", "TEAMS_WEBHOOK_URL", "DISCORD_WEBHOOK_URL",
    "SLACK_CHANNEL", "SLACK_USERNAME", "SLACK_ICON_EMOJI",
    "DISCORD_USERNAME", "DISCORD_AVATAR_URL",
    "ALERT_THRESHOLD", "NOTIFY_RECOVERY",
    "NOTIFICATION_RETRY_ATTEMPTS", "NOTIFICATION_RETRY_BACKOFF_SECONDS",
    "ENABLE_PROMETHEUS", "PROMETHEUS_PORT", "PROMETHEUS_BIND_ADDRESS",
    "ENABLE_ADVANCED_STATS", "SUMMARY_INTERVAL_SECONDS",
    "STORE_STATS_LOG", "STATS_LOG_FORMAT", "STATS_LOG_MAX_SIZE",
    "STATS_LOG_BACKUP_COUNT", "STATS_LOG_FILE",
    "PERSIST_STATS", "STATS_PERSISTENCE_FILE",
    "FLAP_THRESHOLD", "FLAP_WINDOW_SECONDS",
    "SHOW_ONLY_SUCCESS", "SHOW_ONLY_FAILURE",
    "ENABLE_ADAPTIVE_BACKOFF", "BACKOFF_MIN_SECONDS", "BACKOFF_MAX_SECONDS",
    "CIRCUIT_BREAKER_THRESHOLD", "CIRCUIT_BREAKER_COOLDOWN_SECONDS",
    "STATUS_DIR",
}


def load_config(args: argparse.Namespace) -> Dict[str, str]:
    # Start from the allowlisted subset of the current environment.
    config: Dict[str, str] = {k: v for k, v in os.environ.items() if k in _KNOWN_ENV_KEYS}

    if args.config:
        config_path = os.path.expanduser(args.config)
        if not os.path.exists(config_path):
            print(
                f"[PingPanda] WARNING: config file not found: {config_path}",
                file=sys.stderr,
            )
        else:
            try:
                from dotenv import dotenv_values
            except ImportError:
                # Graceful fallback: parse manually if python-dotenv is absent.
                _parse_config_file_fallback(config_path, config)
            else:
                # dotenv_values() parses KEY=value, supports inline # comments,
                # quoted values, and multi-line values.
                for key, value in dotenv_values(config_path).items():
                    if key in _KNOWN_ENV_KEYS and value is not None:
                        config[key] = value

    if args.verbose:
        config["VERBOSE"] = "true"
    if args.show_only_success:
        config["SHOW_ONLY_SUCCESS"] = "true"
    if args.show_only_failure:
        config["SHOW_ONLY_FAILURE"] = "true"

    return config


def _parse_config_file_fallback(path: str, config: Dict[str, str]) -> None:
    """Minimal KEY=value parser used when python-dotenv is not installed."""
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                # Strip inline comments and surrounding quotes.
                value = value.split("#", 1)[0].strip().strip('"').strip("'")
                if key in _KNOWN_ENV_KEYS:
                    config[key] = value


def main() -> None:
    import asyncio
    args = parse_args()
    config = load_config(args)
    monitor = PingPandaApp(config)
    try:
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        # Graceful shutdown on Ctrl+C - cleanup is handled in app.run()
        pass


PingPanda = PingPandaApp


if __name__ == "__main__":
    main()
