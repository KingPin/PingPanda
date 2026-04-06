"""Tests for configuration validation."""

import logging
import tempfile

import pytest

from pingpanda_core.app import PingPanda, NormalizedConfig
from pingpanda_core.checks import SSLCheck
from pingpanda_core.registry import CheckDependencies


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


def test_normalized_config_aliases():
    """NormalizedConfig should resolve known aliases to canonical keys."""
    cfg = NormalizedConfig({
        "SUMMARY_INTERVAL": "60",          # alias → summary_interval_seconds
        "FLAPPING_THRESHOLD": "3",          # alias → flap_threshold
        "ENABLE_STATS_LOGGING": "true",     # alias → store_stats_log
        "LOG_ROTATION_SIZE": "2097152",     # alias → stats_log_max_size
    })
    # Keys are stored under canonical names
    assert cfg["summary_interval_seconds"] == "60"
    assert cfg["flap_threshold"] == "3"
    assert cfg["store_stats_log"] == "true"
    assert cfg["stats_log_max_size"] == "2097152"
    # get() also resolves via alias
    assert cfg.get("summary_interval") == "60"
    assert cfg.get("flapping_window") is None


@pytest.mark.parametrize("domain,expected_host,expected_port", [
    # Plain hostname
    ("example.com", "example.com", 443),
    # hostname:port
    ("example.com:8443", "example.com", 8443),
    # Bracketed IPv6, default port
    ("[2001:db8::1]", "2001:db8::1", 443),
    # Bracketed IPv6 with port
    ("[2001:db8::1]:8443", "2001:db8::1", 8443),
    # Bare IPv6 (no port)
    ("2001:db8::1", "2001:db8::1", 443),
    # Loopback IPv6
    ("::1", "::1", 443),
])
def test_ssl_parse_domain(domain, expected_host, expected_port):
    """_parse_domain handles plain hosts, host:port, and IPv6 variants."""
    # Build a minimal stub — _parse_domain is a pure method with no deps.
    deps = CheckDependencies(app=None, stats=None)  # type: ignore[arg-type]
    check = object.__new__(SSLCheck)
    check.deps = deps
    host, port = check._parse_domain(domain)
    assert host == expected_host
    assert port == expected_port

