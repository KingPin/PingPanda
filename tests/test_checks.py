import logging
import socket
import time

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

    def _should_log_result(self, is_success):
        return True

    def send_notification(self, message, status, check_type, target):
        self.notifications.append(
            {
                "message": message,
                "status": status,
                "type": check_type,
                "target": target,
            }
        )


def test_dns_check_success(monkeypatch):
    app = DummyApp()
    app.enable_dns = True
    app.domains = ["example.com"]

    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(socket, "gethostbyname", lambda domain: "93.184.216.34")

    DNSCheck(CheckDependencies(app=app, stats=None)).run()

    assert len(app.notifications) == 1
    assert app.notifications[0]["status"] == "ok"
    assert app.notifications[0]["type"] == "DNS"


def test_ping_check_failure(monkeypatch):
    app = DummyApp()
    app.enable_ping = True
    app.ping_ips = ["1.1.1.1"]

    monkeypatch.setattr(time, "sleep", lambda _: None)

    class FailingPing:
        def success(self):
            return False

        @property
        def rtt_avg_ms(self):
            return 0.0

    monkeypatch.setattr(checks_module.pythonping, "ping", lambda *args, **kwargs: FailingPing())

    PingCheck(CheckDependencies(app=app, stats=None)).run()

    assert len(app.notifications) == 1
    assert app.notifications[0]["status"] == "error"
    assert app.notifications[0]["type"] == "Ping"


def test_website_check_non_success(monkeypatch):
    app = DummyApp()
    app.enable_website_check = True
    app.websites = ["https://service"]
    app.success_http_codes = [200]

    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    monkeypatch.setattr(checks_module.requests, "get", lambda *args, **kwargs: FakeResponse(500))

    WebsiteCheck(CheckDependencies(app=app, stats=None)).run()

    assert len(app.notifications) == 1
    assert app.notifications[0]["status"] == "error"
    assert app.notifications[0]["type"] == "Website"


def test_ssl_check_warning(monkeypatch):
    app = DummyApp()
    app.enable_ssl_check = True
    app.ssl_check_domains = ["example.com"]
    app.ssl_warn_days = 30
    app.ssl_critical_days = 7

    monkeypatch.setattr(SSLCheck, "_get_ssl_days_remaining", lambda self, host, port: 10)

    SSLCheck(CheckDependencies(app=app, stats=None)).run()

    assert len(app.notifications) == 1
    assert app.notifications[0]["status"] == "error"  # warning mapped to error notifications
    assert app.notifications[0]["type"] == "SSL"
