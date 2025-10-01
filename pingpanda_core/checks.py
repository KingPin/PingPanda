"""Monitoring checks for PingPanda."""

from __future__ import annotations

import socket
import ssl
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

import pythonping
import requests

from .stats import StatsManager, StatsUpdateResult


@dataclass
class CheckDependencies:
    app: Any
    stats: Optional[StatsManager]


class DNSCheck:
    def __init__(self, deps: CheckDependencies):
        self.deps = deps

    @property
    def app(self):
        return self.deps.app

    def run(self) -> None:
        app = self.app
        if not app.enable_dns:
            return

        if not (app.show_only_success or app.show_only_failure):
            app.logger.info("Starting DNS resolution checks...")

        for domain in app.domains:
            start_time = time.perf_counter()
            success = False

            for attempt in range(app.retry_count):
                try:
                    socket.gethostbyname(domain)
                    elapsed = time.perf_counter() - start_time
                    duration_ms = elapsed * 1000

                    if app._should_log_result(True):
                        app.logger.info(
                            "DNS Resolution for %s: PASS (Time: %.2fms)",
                            domain,
                            duration_ms,
                        )

                    if app.enable_prometheus:
                        app.dns_status.labels(domain=domain).set(1)
                        app.dns_response_time.labels(domain=domain).observe(elapsed)

                    app.send_notification(
                        f"DNS resolution successful in {duration_ms:.2f}ms",
                        status="ok",
                        check_type="DNS",
                        target=domain,
                    )
                    success = True
                    break
                except socket.gaierror as exc:
                    if app.verbose:
                        app.logger.debug("DNS Resolution attempt %s for %s failed: %s", attempt + 1, domain, exc)
                    time.sleep(1)

            if success:
                continue

            if app._should_log_result(False):
                app.logger.error("DNS Resolution for %s: FAIL", domain)

            if app.enable_prometheus:
                app.dns_status.labels(domain=domain).set(0)
                app.dns_errors.labels(domain=domain).inc()

            app.send_notification(
                f"Failed to resolve domain after {app.retry_count} attempts",
                status="error",
                check_type="DNS",
                target=domain,
            )


class PingCheck:
    def __init__(self, deps: CheckDependencies):
        self.deps = deps

    @property
    def app(self):
        return self.deps.app

    @property
    def stats(self) -> Optional[StatsManager]:
        return self.deps.stats

    def run(self) -> None:
        app = self.app
        if not app.enable_ping:
            return

        if not (app.show_only_success or app.show_only_failure):
            app.logger.info("Starting ping checks...")

        for ip in app.ping_ips:
            success = False
            start_time = time.perf_counter()

            for attempt in range(app.retry_count):
                try:
                    response_list = pythonping.ping(ip, count=1, timeout=2)
                    if not response_list.success():
                        if app.verbose:
                            app.logger.debug("Ping attempt %s to %s failed", attempt + 1, ip)
                        time.sleep(1)
                        continue

                    elapsed = time.perf_counter() - start_time
                    duration_ms = response_list.rtt_avg_ms

                    if app._should_log_result(True):
                        app.logger.info("Ping to %s: PASS (Time: %.2fms)", ip, duration_ms)

                    if app.enable_prometheus:
                        app.ping_status.labels(target=ip).set(1)
                        app.ping_response_time.labels(target=ip).observe(elapsed)

                    self._update_stats(ip, True)

                    app.send_notification(
                        f"Ping successful in {duration_ms:.2f}ms",
                        status="ok",
                        check_type="Ping",
                        target=ip,
                    )
                    success = True
                    break
                except Exception as exc:  # pylint: disable=broad-except
                    if app.verbose:
                        app.logger.debug("Ping attempt %s to %s failed: %s", attempt + 1, ip, exc)
                    time.sleep(1)

            if success:
                continue

            if app._should_log_result(False):
                app.logger.error("Ping to %s: FAIL", ip)

            if app.enable_prometheus:
                app.ping_status.labels(target=ip).set(0)
                app.ping_errors.labels(target=ip).inc()

            self._update_stats(ip, False)

            app.send_notification(
                f"Failed to ping host after {app.retry_count} attempts",
                status="error",
                check_type="Ping",
                target=ip,
            )

    def _update_stats(self, ip: str, success: bool) -> None:
        if not self.stats:
            return

        result: StatsUpdateResult = self.stats.update_ip(ip, success)

        if result.flapping_changed and result.is_flapping:
            self.app.send_notification(
                f"IP {ip} is flapping (>{self.app.flap_threshold} status changes in {self.app.flap_window_seconds}s)",
                status="error",
                check_type="Flapping",
                target=ip,
            )
        elif result.status_changed and success and not result.is_flapping:
            self.app.logger.info(
                "IP %s recovered (was down for %.1fs)",
                ip,
                self.stats.ip_stats[ip].total_downtime,
            )


class WebsiteCheck:
    def __init__(self, deps: CheckDependencies):
        self.deps = deps

    @property
    def app(self):
        return self.deps.app

    def run(self) -> None:
        app = self.app
        if not app.enable_website_check or not app.websites:
            return

        if not (app.show_only_success or app.show_only_failure):
            app.logger.info("Starting website checks...")

        for website in app.websites:
            if not website:
                continue

            start_time = time.perf_counter()
            try:
                response = requests.get(website, timeout=10)
                elapsed = time.perf_counter() - start_time
                duration_ms = elapsed * 1000

                if response.status_code in app.success_http_codes:
                    if app._should_log_result(True):
                        app.logger.info(
                            "Website check for %s: PASS (HTTP Status: %s, Time: %.2fms)",
                            website,
                            response.status_code,
                            duration_ms,
                        )

                    if app.enable_prometheus:
                        app.website_status.labels(url=website).set(1)
                        app.website_response_time.labels(url=website).observe(elapsed)

                    app.send_notification(
                        f"Website check successful (HTTP {response.status_code}, {duration_ms:.2f}ms)",
                        status="ok",
                        check_type="Website",
                        target=website,
                    )
                else:
                    if app._should_log_result(False):
                        app.logger.error(
                            "Website check for %s: FAIL (HTTP Status: %s)",
                            website,
                            response.status_code,
                        )

                    if app.enable_prometheus:
                        app.website_status.labels(url=website).set(0)
                        app.website_errors.labels(url=website).inc()

                    app.send_notification(
                        f"Website returned HTTP {response.status_code}",
                        status="error",
                        check_type="Website",
                        target=website,
                    )
            except requests.RequestException as exc:
                if app._should_log_result(False):
                    app.logger.error("Website check for %s: FAIL (%s)", website, exc)

                if app.enable_prometheus:
                    app.website_status.labels(url=website).set(0)
                    app.website_errors.labels(url=website).inc()

                app.send_notification(
                    f"Failed to reach website: {exc}",
                    status="error",
                    check_type="Website",
                    target=website,
                )


class SSLCheck:
    def __init__(self, deps: CheckDependencies):
        self.deps = deps

    @property
    def app(self):
        return self.deps.app

    def run(self) -> None:
        app = self.app
        if not app.enable_ssl_check or not app.ssl_check_domains:
            return

        if not (app.show_only_success or app.show_only_failure):
            app.logger.info("Starting SSL certificate checks...")

        for domain in app.ssl_check_domains:
            try:
                host, port = self._parse_domain(domain)
                days_remaining = self._get_ssl_days_remaining(host, port)

                if days_remaining is None:
                    continue

                if days_remaining < 0:
                    message = f"SSL certificate for {domain} has expired"
                    level = "error"
                elif days_remaining <= app.ssl_critical_days:
                    message = f"SSL certificate for {domain} expires in {days_remaining} days (CRITICAL)"
                    level = "error"
                elif days_remaining <= app.ssl_warn_days:
                    message = f"SSL certificate for {domain} expires in {days_remaining} days (WARNING)"
                    level = "warning"
                else:
                    message = f"SSL certificate for {domain} is valid for {days_remaining} more days"
                    level = "ok"

                self._handle_result(domain, days_remaining, message, level)
            except Exception as exc:  # pylint: disable=broad-except
                if app._should_log_result(False):
                    app.logger.error("SSL check for %s failed: %s", domain, exc)

                if app.enable_prometheus:
                    app.ssl_status.labels(domain=domain).set(0)
                    app.ssl_errors.labels(domain=domain).inc()

                app.send_notification(
                    f"SSL check failed: {exc}",
                    status="error",
                    check_type="SSL",
                    target=domain,
                )

    def _parse_domain(self, domain: str) -> tuple[str, int]:
        if ":" in domain:
            host, port = domain.split(":", 1)
            return host, int(port)
        return domain, 443

    def _get_ssl_days_remaining(self, host: str, port: int) -> Optional[int]:
        context = ssl.create_default_context()
        expire_time: Optional[datetime] = None
        with socket.create_connection((host, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=host) as wrapped:
                cert: Dict[str, Any] = wrapped.getpeercert() or {}

                not_after = cert.get("notAfter")
                if not not_after:
                    return None

                expire_time = datetime.strptime(str(not_after), "%b %d %H:%M:%S %Y %Z")

        if expire_time is None:
            return None

        delta = expire_time - datetime.utcnow()

        self.app.logger.debug("SSL certificate for %s:%s expires on %s", host, port, expire_time)

        return delta.days

    def _handle_result(self, domain: str, days_remaining: int, message: str, level: str) -> None:
        app = self.app

        if level == "ok":
            if app._should_log_result(True):
                app.logger.info("SSL check for %s: PASS (%s)", domain, message)
            status = "ok"
        elif level == "warning":
            if app._should_log_result(False):
                app.logger.warning("SSL check for %s: WARNING (%s)", domain, message)
            status = "error"
        else:
            if app._should_log_result(False):
                app.logger.error("SSL check for %s: FAIL (%s)", domain, message)
            status = "error"

        if app.enable_prometheus:
            metric_value = 1 if level == "ok" else 0
            app.ssl_status.labels(domain=domain).set(metric_value)
            app.ssl_days_remaining.labels(domain=domain).set(days_remaining)
            if level != "ok":
                app.ssl_errors.labels(domain=domain).inc()

        app.send_notification(
            message,
            status=status,
            check_type="SSL",
            target=domain,
        )
