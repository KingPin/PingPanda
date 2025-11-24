"""CLI entrypoint for PingPanda monitoring."""

import argparse
import os
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


def load_config(args: argparse.Namespace) -> Dict[str, str]:
    config = {k: v for k, v in os.environ.items()}

    if args.config:
        config_path = os.path.expanduser(args.config)
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        config[key.strip()] = value.strip()

    if args.verbose:
        config["VERBOSE"] = "true"
    if args.show_only_success:
        config["SHOW_ONLY_SUCCESS"] = "true"
    if args.show_only_failure:
        config["SHOW_ONLY_FAILURE"] = "true"

    return config


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
