import logging
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

import pingpanda_core.checks as checks_module
from pingpanda_core.backoff import FailureTracker
from pingpanda_core.checks import CheckDependencies, DNSCheck, PingCheck, SSLCheck, WebsiteCheck


class DummyApp:
    def __init__(self):
        self.logger = logging.getLogger(f"pingpanda.tests.checks.{id(self)}")
        self.logger.propagate = False
        self.logger.addHandler(logging.NullHandler())
        self.show_only_success = False
        self.show_only_failure = False
        self.enable_prometheus = False
        self.verbose = False
        self.retry_count = 2
        self.notifications = []
        self.enable_dns = False
        self.domains = []
        self.enable_ping = False
        self.ping_ips = []
        self.enable_website_check = False
        self.websites = []
        self.success_http_codes = [200]
        self.enable_ssl_check = False
        self.ssl_check_domains = []
        self.ssl_warn_days = 30
        self.ssl_critical_days = 7
        self.flap_threshold = 3
        self.flap_window_seconds = 300
        self.failure_tracker = FailureTracker(enable_backoff=False)
        self.http_session = None
        self.dns_resolver = None
        # Prometheus metrics
        self.dns_status = None
        self.dns_response_time = None
        self.ping_status = None
        self.ping_response_time = None
        self.website_status = None
        self.website_response_time = None
        self.ssl_status = None
        self.ssl_days_remaining = None
        self.ssl_errors = None

    def _should_log_result(self, is_success):
        return True

    async def send_notification(self, message, status, check_type, target):
        self.notifications.append(
            {
                "message": message,
                "status": status,
                "type": check_type,
                "target": target,
            }
        )


@pytest.mark.asyncio
async def test_dns_check_success(monkeypatch):
    app = DummyApp()
    app.enable_dns = True
    app.domains = ["example.com"]

    # Mock aiodns resolver
    mock_resolver = MagicMock()
    # query is async
    mock_resolver.query = AsyncMock(return_value="93.184.216.34")
    app.dns_resolver = mock_resolver

    await DNSCheck(CheckDependencies(app=app, stats=None)).run()

    assert len(app.notifications) == 1
    assert app.notifications[0]["status"] == "ok"
    assert app.notifications[0]["type"] == "DNS"


@pytest.mark.asyncio
async def test_ping_check_failure(monkeypatch):
    app = DummyApp()
    app.enable_ping = True
    app.ping_ips = ["1.1.1.1"]

    # Mock aioping.ping to raise exception
    monkeypatch.setattr(checks_module.aioping, "ping", AsyncMock(side_effect=Exception("Ping failed")))
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await PingCheck(CheckDependencies(app=app, stats=None)).run()

    assert len(app.notifications) == 1
    assert app.notifications[0]["status"] == "error"
    assert app.notifications[0]["type"] == "Ping"


@pytest.mark.asyncio
async def test_website_check_non_success(monkeypatch):
    app = DummyApp()
    app.enable_website_check = True
    app.websites = ["https://service"]
    app.success_http_codes = [200]

    # Mock aiohttp session
    mock_session = MagicMock()
    mock_response = AsyncMock()
    mock_response.status = 500
    # __aenter__ returns the response
    mock_response.__aenter__.return_value = mock_response
    mock_response.__aexit__.return_value = None
    
    mock_session.get.return_value = mock_response
    app.http_session = mock_session

    await WebsiteCheck(CheckDependencies(app=app, stats=None)).run()

    assert len(app.notifications) == 1
    assert app.notifications[0]["status"] == "error"
    assert app.notifications[0]["type"] == "Website"


@pytest.mark.asyncio
async def test_ssl_check_warning(monkeypatch):
    app = DummyApp()
    app.enable_ssl_check = True
    app.ssl_check_domains = ["example.com"]
    app.ssl_warn_days = 30
    app.ssl_critical_days = 7

    # Mock _get_ssl_days_remaining which is run in executor
    # Since we mock the method on the instance, we can just make it return the value
    # But run_in_executor calls it.
    
    # We can mock loop.run_in_executor
    # Or we can mock SSLCheck._get_ssl_days_remaining
    
    # Since run_in_executor executes the function, if we mock the function it should work.
    
    monkeypatch.setattr(SSLCheck, "_get_ssl_days_remaining", lambda self, host, port: 10)

    await SSLCheck(CheckDependencies(app=app, stats=None)).run()

    assert len(app.notifications) == 1
    assert app.notifications[0]["status"] == "error"  # warning mapped to error notifications
    assert app.notifications[0]["type"] == "SSL"


@pytest.mark.asyncio
async def test_prometheus_metrics_updated_on_success(monkeypatch):
    """Test that prometheus metrics are set when checks succeed."""
    app = DummyApp()
    app.enable_prometheus = True
    app.enable_dns = True
    app.domains = ["example.com"]
    
    # Mock prometheus gauges and summaries
    mock_status = MagicMock()
    mock_response_time = MagicMock()
    app.dns_status = mock_status
    app.dns_response_time = mock_response_time
    
    # Mock aiodns resolver
    mock_resolver = MagicMock()
    mock_resolver.query = AsyncMock(return_value="93.184.216.34")
    app.dns_resolver = mock_resolver
    
    await DNSCheck(CheckDependencies(app=app, stats=None)).run()
    
    # Verify metrics were updated (using keyword args)
    mock_status.labels.assert_called_once_with(domain="example.com")
    mock_status.labels.return_value.set.assert_called_once_with(1)  # 1 = OK
    mock_response_time.labels.assert_called_once_with(domain="example.com")
    mock_response_time.labels.return_value.observe.assert_called_once()


@pytest.mark.asyncio
async def test_prometheus_metrics_updated_on_failure(monkeypatch):
    """Test that prometheus metrics are set when checks fail."""
    app = DummyApp()
    app.enable_prometheus = True
    app.enable_ping = True
    app.ping_ips = ["1.1.1.1"]
    
    # Mock prometheus metrics
    mock_status = MagicMock()
    mock_errors = MagicMock()
    app.ping_status = mock_status
    app.ping_errors = mock_errors
    
    # Mock aioping.ping to raise exception
    monkeypatch.setattr(checks_module.aioping, "ping", AsyncMock(side_effect=Exception("Ping failed")))
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    
    await PingCheck(CheckDependencies(app=app, stats=None)).run()
    
    # Verify error metrics were updated (using keyword args)
    mock_status.labels.assert_called_with(target="1.1.1.1")
    mock_status.labels.return_value.set.assert_called_with(0)  # 0 = ERROR
    mock_errors.labels.assert_called_with(target="1.1.1.1")
    mock_errors.labels.return_value.inc.assert_called_once()
