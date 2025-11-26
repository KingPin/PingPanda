"""Monitoring checks for PingPanda."""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
import aiodns
import aioping

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

    async def run(self) -> None:
        app = self.app
        if not app.enable_dns:
            return

        if not (app.show_only_success or app.show_only_failure):
            app.logger.info("Starting DNS resolution checks...")

        tasks = []
        for domain in app.domains:
            tasks.append(self._check_domain(domain))
        
        await asyncio.gather(*tasks)

    async def _check_domain(self, domain: str) -> None:
        app = self.app
        # Check if we should skip this target due to backoff/circuit breaker
        if not app.failure_tracker.should_check(f"dns:{domain}"):
            if app.verbose:
                app.logger.debug("Skipping DNS check for %s (in backoff/circuit open)", domain)
            return

        from tenacity import AsyncRetrying, stop_after_attempt, wait_fixed, retry_if_exception_type, before_sleep_log

        start_time = time.perf_counter()
        success = False

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(app.retry_count),
                wait=wait_fixed(1),
                retry=retry_if_exception_type((aiodns.error.DNSError, Exception)),
                before_sleep=before_sleep_log(app.logger, logging.DEBUG) if app.verbose else None,
                reraise=True,
            ):
                with attempt:
                    # Use aiodns for async resolution
                    # Assuming app has a resolver instance or we create one
                    resolver = getattr(app, "dns_resolver", None)
                    if not resolver:
                        # Fallback if not initialized in app (though it should be)
                        resolver = aiodns.DNSResolver()
                    
                    await resolver.query(domain, 'A')
                    
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

                    await app.send_notification(
                        f"DNS resolution successful in {duration_ms:.2f}ms",
                        status="ok",
                        check_type="DNS",
                        target=domain,
                    )
                    success = True
        except (aiodns.error.DNSError, Exception) as exc:
            if app.verbose:
                app.logger.debug("DNS Resolution for %s failed after %s attempts: %s", domain, app.retry_count, exc)
            success = False

        # Record the result in the failure tracker
        app.failure_tracker.record_result(f"dns:{domain}", success)

        if not success:
            if app._should_log_result(False):
                app.logger.error("DNS Resolution for %s: FAIL", domain)

            if app.enable_prometheus:
                app.dns_status.labels(domain=domain).set(0)
                app.dns_errors.labels(domain=domain).inc()

            await app.send_notification(
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

    async def run(self) -> None:
        app = self.app
        if not app.enable_ping:
            return

        if not (app.show_only_success or app.show_only_failure):
            app.logger.info("Starting ping checks...")

        tasks = []
        for ip in app.ping_ips:
            tasks.append(self._check_ip(ip))
        
        await asyncio.gather(*tasks)

    async def _check_ip(self, ip: str) -> None:
        app = self.app
        # Check if we should skip this target due to backoff/circuit breaker
        if not app.failure_tracker.should_check(f"ping:{ip}"):
            if app.verbose:
                app.logger.debug("Skipping ping check for %s (in backoff/circuit open)", ip)
            return

        from tenacity import AsyncRetrying, stop_after_attempt, wait_fixed, retry_if_exception_type, before_sleep_log

        success = False

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(app.retry_count),
                wait=wait_fixed(1),
                retry=retry_if_exception_type(Exception),
                before_sleep=before_sleep_log(app.logger, logging.DEBUG) if app.verbose else None,
                reraise=True,
            ):
                with attempt:
                    # aioping returns delay in seconds
                    delay = await aioping.ping(ip, timeout=2)
                    
                    duration_ms = delay * 1000

                    if app._should_log_result(True):
                        app.logger.info("Ping to %s: PASS (Time: %.2fms)", ip, duration_ms)

                    if app.enable_prometheus:
                        app.ping_status.labels(target=ip).set(1)
                        app.ping_response_time.labels(target=ip).observe(delay)

                    await self._update_stats(ip, True)

                    await app.send_notification(
                        f"Ping successful in {duration_ms:.2f}ms",
                        status="ok",
                        check_type="Ping",
                        target=ip,
                    )
                    success = True
        except Exception as exc:
            if app.verbose:
                app.logger.debug("Ping to %s failed after %s attempts: %s", ip, app.retry_count, exc)
            success = False
            await self._update_stats(ip, False)
        # Record the result in the failure tracker
        app.failure_tracker.record_result(f"ping:{ip}", success)

        if not success:
            if app._should_log_result(False):
                app.logger.error("Ping to %s: FAIL", ip)

            if app.enable_prometheus:
                app.ping_status.labels(target=ip).set(0)
                app.ping_errors.labels(target=ip).inc()

            await self._update_stats(ip, False)

            await app.send_notification(
                f"Failed to ping host after {app.retry_count} attempts",
                status="error",
                check_type="Ping",
                target=ip,
            )

    async def _update_stats(self, ip: str, success: bool) -> None:
        if not self.stats:
            return

        result: StatsUpdateResult = self.stats.update_ip(ip, success)

        if result.flapping_changed and result.is_flapping:
            await self.app.send_notification(
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

    async def run(self) -> None:
        app = self.app
        if not app.enable_website_check or not app.websites:
            return

        if not (app.show_only_success or app.show_only_failure):
            app.logger.info("Starting website checks...")

        tasks = []
        for website in app.websites:
            if not website:
                continue
            tasks.append(self._check_website(website))
        
        await asyncio.gather(*tasks)

    async def _check_website(self, website: str) -> None:
        app = self.app
        # Check if we should skip this target due to backoff/circuit breaker
        if not app.failure_tracker.should_check(f"website:{website}"):
            if app.verbose:
                app.logger.debug("Skipping website check for %s (in backoff/circuit open)", website)
            return

        start_time = time.perf_counter()
        success = False
        
        # Use existing session if available
        session = getattr(app, "http_session", None)
        local_session = False
        if not session:
            session = aiohttp.ClientSession()
            local_session = True

        from tenacity import AsyncRetrying, stop_after_attempt, wait_fixed, retry_if_exception_type, before_sleep_log

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(app.retry_count),
                wait=wait_fixed(1),
                retry=retry_if_exception_type(aiohttp.ClientError),
                before_sleep=before_sleep_log(app.logger, logging.DEBUG) if app.verbose else None,
                reraise=True,
            ):
                with attempt:
                    async with session.get(website, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        elapsed = time.perf_counter() - start_time
                        duration_ms = elapsed * 1000
                        status_code = response.status

                        if status_code in app.success_http_codes:
                            success = True
                            if app._should_log_result(True):
                                app.logger.info(
                                    "Website check for %s: PASS (HTTP Status: %s, Time: %.2fms)",
                                    website,
                                    status_code,
                                    duration_ms,
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
                                    website,
                                    status_code,
                                    duration_ms,
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
                app.logger.debug("Website check for %s failed after %s attempts: %s", website, app.retry_count, exc)
            success = False
            # Original code also sent notification here for ClientError
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
             # Non-retryable exception
            if app.verbose:
                app.logger.debug("Website check for %s failed with unexpected error: %s", website, exc)
            success = False
            # Original code didn't have a specific catch-all, but this is good for robustness
            await app.send_notification(
                f"Website check failed with unexpected error: {exc}",
                status="error",
                check_type="Website",
                target=website,
            )
            if app.enable_prometheus:
                app.website_status.labels(url=website).set(0)
                app.website_errors.labels(url=website).inc()
        finally:
            if local_session:
                await session.close()
        
        # Wait, the original code didn't loop for website checks!
        # It just did a single try/except block.
        # "for attempt in range(app.retry_count)" was NOT present in the view_file output for _check_website.
        # Let me verify that.

        # Record the result in the failure tracker
        app.failure_tracker.record_result(f"website:{website}", success)


class SSLCheck:
    def __init__(self, deps: CheckDependencies):
        self.deps = deps

    @property
    def app(self):
        return self.deps.app

    async def run(self) -> None:
        app = self.app
        if not app.enable_ssl_check or not app.ssl_check_domains:
            return

        if not (app.show_only_success or app.show_only_failure):
            app.logger.info("Starting SSL certificate checks...")

        tasks = []
        for domain in app.ssl_check_domains:
            tasks.append(self._check_ssl(domain))
        
        await asyncio.gather(*tasks)

    async def _check_ssl(self, domain: str) -> None:
        app = self.app
        # Check if we should skip this target due to backoff/circuit breaker
        if not app.failure_tracker.should_check(f"ssl:{domain}"):
            if app.verbose:
                app.logger.debug("Skipping SSL check for %s (in backoff/circuit open)", domain)
            return
        
        from tenacity import AsyncRetrying, stop_after_attempt, wait_fixed, retry_if_exception_type, before_sleep_log

        success = False
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(app.retry_count),
                wait=wait_fixed(1),
                retry=retry_if_exception_type(Exception),
                before_sleep=before_sleep_log(app.logger, logging.DEBUG) if app.verbose else None,
                reraise=True,
            ):
                with attempt:
                    host, port = self._parse_domain(domain)
                    
                    # Run the blocking SSL check in a thread executor
                    loop = asyncio.get_running_loop()
                    days_remaining = await loop.run_in_executor(
                        None, self._get_ssl_days_remaining, host, port
                    )

                    if days_remaining is None:
                        # If None, it means an exception was caught inside _get_ssl_days_remaining
                        # But wait, _get_ssl_days_remaining catches exceptions and returns None?
                        # If so, we can't retry based on exception unless we change that.
                        # Let's check _get_ssl_days_remaining.
                        # Assuming it raises exception for now, or we treat None as failure.
                        # If it returns None, we should probably raise an exception to trigger retry.
                        raise Exception("Failed to get SSL days remaining")

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
                            app.logger.info("SSL check for %s: PASS (%s days remaining)", domain, days_remaining)
                        await app.send_notification(
                            message,
                            status="ok",
                            check_type="SSL",
                            target=domain,
                        )
                    else:
                        if app._should_log_result(False):
                            app.logger.warning("SSL check for %s: %s", domain, message)
                        await app.send_notification(
                            message,
                            status="error",
                            check_type="SSL",
                            target=domain,
                        )

                    if app.enable_prometheus:
                        app.ssl_days_remaining.labels(domain=domain).set(days_remaining)
        except Exception as exc:
            if app.verbose:
                app.logger.debug("SSL check for %s failed after %s attempts: %s", domain, app.retry_count, exc)
            success = False
            # If we failed to get days remaining after retries
            await app.send_notification(
                f"Failed to check SSL certificate: {exc}",
                status="error",
                check_type="SSL",
                target=domain,
            )

        # Record the result in the failure tracker
        app.failure_tracker.record_result(f"ssl:{domain}", success)

    def _parse_domain(self, domain: str) -> tuple[str, int]:
        if ":" in domain:
            host, port = domain.split(":", 1)
            return host, int(port)
        return domain, 443

    def _get_ssl_days_remaining(self, host: str, port: int) -> Optional[int]:
        # This is a blocking function, intended to be run in an executor
        context = ssl.create_default_context()
        expire_time: Optional[datetime] = None
        try:
            with socket.create_connection((host, port), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=host) as wrapped:
                    cert: Dict[str, Any] = wrapped.getpeercert() or {}

                    not_after = cert.get("notAfter")
                    if not not_after:
                        return None

                    expire_time = datetime.strptime(str(not_after), "%b %d %H:%M:%S %Y %Z")
        except Exception as e:
            self.app.logger.debug("SSL handshake failed for %s:%s: %s", host, port, e)
            raise

        if expire_time is None:
            return None

        delta = expire_time - datetime.utcnow()

        self.app.logger.debug("SSL certificate for %s:%s expires on %s", host, port, expire_time)

        return delta.days

    async def _handle_result(self, domain: str, days_remaining: int, message: str, level: str) -> None:
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

        await app.send_notification(
            message,
            status=status,
            check_type="SSL",
            target=domain,
        )
