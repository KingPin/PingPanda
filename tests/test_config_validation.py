"""Tests for configuration validation."""

import logging
import tempfile

from pingpanda_core.app import PingPanda


def test_mutually_exclusive_filters_are_disabled():
    """Both show filters enabled should disable both."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "SHOW_ONLY_SUCCESS": "true",
            "SHOW_ONLY_FAILURE": "true",
            "LOG_TO_FILE": "false",
            "LOG_DIR": tmpdir,
        }
        app = PingPanda(config)
        assert app.show_only_success is False
        assert app.show_only_failure is False


def test_ssl_check_disabled_without_domains():
    """SSL check should be disabled if no domains specified."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "ENABLE_SSL_CHECK": "true",
            "SSL_CHECK_DOMAINS": "",
            "LOG_TO_FILE": "false",
            "LOG_DIR": tmpdir,
        }
        app = PingPanda(config)
        assert app.enable_ssl_check is False


def test_website_check_disabled_without_urls():
    """Website check should be disabled if no URLs specified."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "ENABLE_WEBSITE_CHECK": "true",
            "CHECK_WEBSITE": "",
            "LOG_TO_FILE": "false",
            "LOG_DIR": tmpdir,
        }
        app = PingPanda(config)
        assert app.enable_website_check is False


def test_invalid_stats_log_format_defaults_to_csv():
    """Invalid stats log format should default to csv."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "STATS_LOG_FORMAT": "xml",
            "LOG_TO_FILE": "false",
            "LOG_DIR": tmpdir,
        }
        app = PingPanda(config)
        assert app.stats_log_format == "csv"


def test_backoff_max_corrected_if_less_than_min():
    """Backoff max should be set equal to min if it's less."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "BACKOFF_MIN_SECONDS": "100",
            "BACKOFF_MAX_SECONDS": "50",
            "LOG_TO_FILE": "false",
            "LOG_DIR": tmpdir,
        }
        app = PingPanda(config)
        assert app.backoff_max_seconds == app.backoff_min_seconds == 100.0


def test_valid_configuration_passes():
    """Valid configuration should not trigger warnings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "SHOW_ONLY_SUCCESS": "false",
            "SHOW_ONLY_FAILURE": "false",
            "ENABLE_SSL_CHECK": "true",
            "SSL_CHECK_DOMAINS": "example.com",
            "STATS_LOG_FORMAT": "json",
            "BACKOFF_MIN_SECONDS": "10",
            "BACKOFF_MAX_SECONDS": "300",
            "LOG_TO_FILE": "false",
            "LOG_DIR": tmpdir,
        }
        app = PingPanda(config)
        assert app.show_only_success is False
        assert app.show_only_failure is False
        assert app.enable_ssl_check is True
        assert app.stats_log_format == "json"
        assert app.backoff_min_seconds == 10.0
        assert app.backoff_max_seconds == 300.0

