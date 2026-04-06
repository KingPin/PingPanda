"""Monitoring checks for PingPanda."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import socket
import ssl
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
import aiodns
import aioping
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .registry import BaseCheck, CheckDependencies, register_check
from .stats import StatsManager


def _sanitize(value: str) -> str:
    """Strip control characters from user-supplied values before logging."""
    return value.replace("\n", "\\n").replace("\r", "\\r")


# ---------------------------------------------------------------------------
# DNS
# ---------------------------------------------------------------------------

@register_check("dns")
class DNSCheck(BaseCheck):
    @property
    def check_name(self) -> str:
        return "DNS resolution"

    @property
    def is_enabled(self) -> bool:
        return bool(self.ctx.enable_dns)

    @property
    def targets(self) -> List[str]:
        return self.ctx.domains

    async def _check_single(self, domain: str) -> None:
        app = self.ctx
        safe_domain = _sanitize(domain)

        if not app.failure_tracker.should_check(f"dns:{domain}"):
            if app.verbose:
                app.logger.debug("Skipping DNS check for %s (in backoff/circuit open)", safe_domain)
            return

        start_time = time.perf_counter()
        success = False

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(app.retry_count),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_exception_type(aiodns.error.DNSError),
                before_sleep=before_sleep_log(app.logger, logging.DEBUG) if app.verbose else None,
                reraise=True,
            ):
                with attempt:
                    await app.dns_resolver.query(domain, 'A')

                    elapsed = time.perf_counter() - start_time
                    duration_ms = elapsed * 1000

                    if app._should_log_result(True):
                        app.logger.info(
                            "DNS Resolution for %s: PASS (Time: %.2fms)",
                            safe_domain,
                            duration_ms,
                        )

                    if app.enable_prometheus:
                        app.dns_status.labels(domain=domain).set(1)
                        app.dns_response_time.labels(domain=domain).observe(elapsed)

                    await app.send_notification(
                        f"DNS resolution successful in {duration_ms:.2f}ms",
                        status="ok",
                        check_type="DNS",
                        target=domain,
                    )
                    success = True
        except aiodns.error.DNSError as exc:
            if app.verbose:
                app.logger.debug(
                    "DNS Resolution for %s failed after %s attempts: %s",
                    safe_domain, app.retry_count, exc,
                )
            success = False

        app.failure_tracker.record_result(f"dns:{domain}", success)
        await self._record_stats_result(domain, success)

        if not success:
            if app._should_log_result(False):
                app.logger.error("DNS Resolution for %s: FAIL", safe_domain)

            if app.enable_prometheus:
                app.dns_status.labels(domain=domain).set(0)
                app.dns_errors.labels(domain=domain).inc()

            await app.send_notification(
                f"Failed to resolve domain after {app.retry_count} attempts",
                status="error",
                check_type="DNS",
                target=domain,
            )


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------

@register_check("ping")
class PingCheck(BaseCheck):
    @property
    def check_name(self) -> str:
        return "ping"

    @property
    def is_enabled(self) -> bool:
        return bool(self.ctx.enable_ping)

    @property
    def targets(self) -> List[str]:
        return self.ctx.ping_ips

    async def _check_single(self, ip: str) -> None:
        app = self.ctx
        safe_ip = _sanitize(ip)

        if not app.failure_tracker.should_check(f"ping:{ip}"):
            if app.verbose:
                app.logger.debug("Skipping ping check for %s (in backoff/circuit open)", safe_ip)
            return

        success = False

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(app.retry_count),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_exception_type(OSError),
                before_sleep=before_sleep_log(app.logger, logging.DEBUG) if app.verbose else None,
                reraise=True,
            ):
                with attempt:
                    delay = await aioping.ping(ip, timeout=2)
                    duration_ms = delay * 1000

                    if app._should_log_result(True):
                        app.logger.info("Ping to %s: PASS (Time: %.2fms)", safe_ip, duration_ms)

                    if app.enable_prometheus:
                        app.ping_status.labels(target=ip).set(1)
                        app.ping_response_time.labels(target=ip).observe(delay)

                    await app.send_notification(
                        f"Ping successful in {duration_ms:.2f}ms",
                        status="ok",
                        check_type="Ping",
                        target=ip,
                    )
                    success = True
        except Exception as exc:
            if app.verbose:
                app.logger.debug(
                    "Ping to %s failed after %s attempts: %s",
                    safe_ip, app.retry_count, exc,
                )
            success = False

        app.failure_tracker.record_result(f"ping:{ip}", success)
        await self._record_stats_result(ip, success)

        if not success:
            if app._should_log_result(False):
                app.logger.error("Ping to %s: FAIL", safe_ip)

            if app.enable_prometheus:
                app.ping_status.labels(target=ip).set(0)
                app.ping_errors.labels(target=ip).inc()

            await app.send_notification(
                f"Failed to ping host after {app.retry_count} attempts",
                status="error",
                check_type="Ping",
                target=ip,
            )


# ---------------------------------------------------------------------------
# Website
# ---------------------------------------------------------------------------

@register_check("website")
class WebsiteCheck(BaseCheck):
    @property
    def check_name(self) -> str:
        return "website"

    @property
    def is_enabled(self) -> bool:
        return bool(self.ctx.enable_website_check and self.ctx.websites)

    @property
    def targets(self) -> List[str]:
        return self.ctx.websites

    async def _check_single(self, website: str) -> None:
        app = self.ctx
        safe_website = _sanitize(website)

        if not app.failure_tracker.should_check(f"website:{website}"):
            if app.verbose:
                app.logger.debug(
                    "Skipping website check for %s (in backoff/circuit open)", safe_website
                )
            return

        start_time = time.perf_counter()
        success = False

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(app.retry_count),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_exception_type(aiohttp.ClientError),
                before_sleep=before_sleep_log(app.logger, logging.DEBUG) if app.verbose else None,
                reraise=True,
            ):
                with attempt:
                    async with app.http_session.get(
                        website, timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        elapsed = time.perf_counter() - start_time
                        duration_ms = elapsed * 1000
                        status_code = response.status

                        if status_code in app.success_http_codes:
                            success = True
                            if app._should_log_result(True):
                                app.logger.info(
                                    "Website check for %s: PASS (HTTP Status: %s, Time: %.2fms)",
                                    safe_website, status_code, duration_ms,
                                )

                            if app.enable_prometheus:
                                app.website_status.labels(url=website).set(1)
                                app.website_response_time.labels(url=website).observe(elapsed)

                            await app.send_notification(
                                f"Website check successful (HTTP {status_code}) in {duration_ms:.2f}ms",
                                status="ok",
                                check_type="Website",
                                target=website,
                            )
                        else:
                            if app._should_log_result(False):
                                app.logger.warning(
                                    "Website check for %s: FAIL (HTTP Status: %s, Time: %.2fms)",
                                    safe_website, status_code, duration_ms,
                                )

                            await app.send_notification(
                                f"Website check failed: HTTP {status_code}",
                                status="error",
                                check_type="Website",
                                target=website,
                            )

                            if app.enable_prometheus:
                                app.website_status.labels(url=website).set(0)
                                app.website_errors.labels(url=website).inc()

        except aiohttp.ClientError as exc:
            if app.verbose:
                app.logger.debug(
                    "Website check for %s failed after %s attempts: %s",
                    safe_website, app.retry_count, exc,
                )
            success = False
            await app.send_notification(
                f"Failed to reach website: {exc}",
                status="error",
                check_type="Website",
                target=website,
            )
            if app.enable_prometheus:
                app.website_status.labels(url=website).set(0)
                app.website_errors.labels(url=website).inc()

        except Exception as exc:
            if app.verbose:
                app.logger.debug(
                    "Website check for %s failed with unexpected error: %s",
                    safe_website, exc,
                )
            success = False
            await app.send_notification(
                f"Website check failed with unexpected error: {exc}",
                status="error",
                check_type="Website",
                target=website,
            )
            if app.enable_prometheus:
                app.website_status.labels(url=website).set(0)
                app.website_errors.labels(url=website).inc()

        app.failure_tracker.record_result(f"website:{website}", success)
        await self._record_stats_result(website, success)


# ---------------------------------------------------------------------------
# SSL
# ---------------------------------------------------------------------------

@register_check("ssl")
class SSLCheck(BaseCheck):
    def __init__(self, deps: CheckDependencies) -> None:
        super().__init__(deps)
        # Create the SSL context once; ssl.create_default_context() loads CA
        # certs from disk on each call — avoid that in the hot path.
        self._ssl_context = ssl.create_default_context()
        # Dedicated thread pool so SSL handshakes (blocking I/O) don't compete
        # with the default executor shared by the rest of the event loop.
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=10, thread_name_prefix="ssl-check"
        )

    @property
    def check_name(self) -> str:
        return "SSL certificate"

    @property
    def is_enabled(self) -> bool:
        return bool(self.ctx.enable_ssl_check and self.ctx.ssl_check_domains)

    @property
    def targets(self) -> List[str]:
        return self.ctx.ssl_check_domains

    async def _check_ssl(self, domain: str) -> None:
        """Alias so existing callers still work; delegates to _check_single."""
        await self._check_single(domain)

    async def _check_single(self, domain: str) -> None:
        app = self.ctx
        safe_domain = _sanitize(domain)

        if not app.failure_tracker.should_check(f"ssl:{domain}"):
            if app.verbose:
                app.logger.debug(
                    "Skipping SSL check for %s (in backoff/circuit open)", safe_domain
                )
            return

        success = False
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(app.retry_count),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_exception_type((OSError, ssl.SSLError)),
                before_sleep=before_sleep_log(app.logger, logging.DEBUG) if app.verbose else None,
                reraise=True,
            ):
                with attempt:
                    host, port = self._parse_domain(domain)

                    loop = asyncio.get_running_loop()
                    days_remaining = await loop.run_in_executor(
                        self._executor, self._get_ssl_days_remaining, host, port
                    )

                    if days_remaining is None:
                        raise OSError("Failed to get SSL days remaining")

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
                        message = f"SSL certificate for {domain} expires in {days_remaining} days"
                        level = "ok"
                        success = True

                    if level == "ok":
                        if app._should_log_result(True):
                            app.logger.info(
                                "SSL check for %s: PASS (%s days remaining)",
                                safe_domain, days_remaining,
                            )
                        await app.send_notification(
                            message, status="ok", check_type="SSL", target=domain,
                        )
                    else:
                        if app._should_log_result(False):
                            app.logger.warning("SSL check for %s: %s", safe_domain, message)
                        await app.send_notification(
                            message, status="error", check_type="SSL", target=domain,
                        )

                    if app.enable_prometheus:
                        metric_value = 1 if level == "ok" else 0
                        app.ssl_status.labels(domain=domain).set(metric_value)
                        app.ssl_days_remaining.labels(domain=domain).set(days_remaining)
                        if level != "ok":
                            app.ssl_errors.labels(domain=domain).inc()

        except Exception as exc:
            if app.verbose:
                app.logger.debug(
                    "SSL check for %s failed after %s attempts: %s",
                    safe_domain, app.retry_count, exc,
                )
            success = False
            await app.send_notification(
                f"Failed to check SSL certificate: {exc}",
                status="error",
                check_type="SSL",
                target=domain,
            )
            if app.enable_prometheus:
                app.ssl_status.labels(domain=domain).set(0)
                app.ssl_errors.labels(domain=domain).inc()

        app.failure_tracker.record_result(f"ssl:{domain}", success)
        await self._record_stats_result(domain, success)

    def _parse_domain(self, domain: str) -> tuple[str, int]:
        # Bracketed IPv6: "[2001:db8::1]" or "[2001:db8::1]:8443"
        if domain.startswith("["):
            bracket_end = domain.find("]")
            if bracket_end == -1:
                return domain, 443
            host = domain[1:bracket_end]
            rest = domain[bracket_end + 1:]
            if rest.startswith(":"):
                return host, int(rest[1:])
            return host, 443
        # Bare IPv6 (multiple colons): treat entire string as host
        if domain.count(":") > 1:
            return domain, 443
        # "hostname:port" or plain hostname
        if ":" in domain:
            host, port = domain.split(":", 1)
            return host, int(port)
        return domain, 443

    def _get_ssl_days_remaining(self, host: str, port: int) -> Optional[int]:
        context = self._ssl_context
        expire_time: Optional[datetime] = None
        try:
            with socket.create_connection((host, port), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=host) as wrapped:
                    cert: Dict[str, Any] = wrapped.getpeercert() or {}

                    not_after = cert.get("notAfter")
                    if not not_after:
                        return None

                    expire_time = datetime.strptime(
                        str(not_after), "%b %d %H:%M:%S %Y %Z"
                    ).replace(tzinfo=timezone.utc)
        except Exception as e:
            self.ctx.logger.debug("SSL handshake failed for %s:%s: %s", host, port, e)
            raise

        if expire_time is None:
            return None

        delta = expire_time - datetime.now(timezone.utc)
        self.ctx.logger.debug(
            "SSL certificate for %s:%s expires on %s", host, port, expire_time
        )
        return delta.days
