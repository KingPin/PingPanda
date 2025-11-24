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
