"""Application orchestration for PingPanda."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from importlib import import_module
from logging.handlers import RotatingFileHandler
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Set, Union

from .checks import CheckDependencies, DNSCheck, PingCheck, SSLCheck, WebsiteCheck
from .notifications import NotificationManager, NotificationSettings
from .persistence import PersistenceManager, StatsPersistenceSettings
from .stats import StatsManager, StatsSettings
from .backoff import FailureTracker


class NormalizedConfig(dict):
    """Dictionary wrapper that normalizes configuration keys and supports aliases."""

    _ALIASES: Dict[str, str] = {
        "summary_interval": "summary_interval_seconds",
        "summary_interval_seconds": "summary_interval_seconds",
        "enable_stats_logging": "store_stats_log",
        "store_stats_log": "store_stats_log",
        "stats_log_size": "stats_log_max_size",
        "log_rotation_size": "stats_log_max_size",
        "stats_log_max_size": "stats_log_max_size",
        "flapping_threshold": "flap_threshold",
        "flap_threshold": "flap_threshold",
        "flapping_window": "flap_window_seconds",
        "flap_window_seconds": "flap_window_seconds",
        "check_website": "check_website",
    }

    def __init__(self, initial: Optional[Dict[str, Any]] = None):
        super().__init__()
        self._original = dict(initial) if initial else {}
        if initial:
            for key, value in initial.items():
                super().__setitem__(self._canonical_key(key), value)

    def _canonical_key(self, key: Union[str, Any]) -> str:
        key_str = str(key)
        lowered = key_str.lower()
        return self._ALIASES.get(lowered, lowered)

    def __setitem__(self, key: Union[str, Any], value: Any) -> None:
        super().__setitem__(self._canonical_key(key), value)

    def __getitem__(self, key: Union[str, Any]) -> Any:
        return super().__getitem__(self._canonical_key(key))

    def get(self, key: Union[str, Any], default: Any = None) -> Any:
        return super().get(self._canonical_key(key), default)

    def __contains__(self, key: object) -> bool:
        return super().__contains__(self._canonical_key(key))

    @property
    def original(self) -> Dict[str, Any]:
        return dict(self._original)


class PingPanda:
    """PingPanda orchestration layer coordinating checks, notifications, and stats."""

    _prometheus_exports: Optional[Dict[str, Any]] = None

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = NormalizedConfig(config or {})
        self.logger = logging.getLogger("pingpanda")
        self._setup_logging()
        self._load_config()
        self._setup_prometheus()
        self._thread_pool: Optional[ThreadPoolExecutor] = None
        self._initialize_components()
        self.logger.info(
            "PingPanda initialized at %s",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _setup_logging(self) -> None:
        log_level = getattr(logging, str(self.config.get("log_level", "INFO")).upper(), logging.INFO)
        log_dir = str(self.config.get("log_dir", "/logs"))
        log_file = os.path.join(log_dir, str(self.config.get("log_file", "pingpanda.log")))
        max_log_size = int(self.config.get("max_log_size", 1048576))
        log_backup_count = int(self.config.get("log_backup_count", 5))

        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        self.logger.setLevel(log_level)

        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

        if str(self.config.get("log_to_terminal", "true")).lower() == "true":
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

        if str(self.config.get("log_to_file", "true")).lower() == "true":
            file_handler = RotatingFileHandler(log_file, maxBytes=max_log_size, backupCount=log_backup_count)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

        self.log_dir = log_dir
        self.log_file = log_file

    def _load_config(self) -> None:
        def get_bool(key: str, default: bool = False) -> bool:
            value = self.config.get(key, default)
            if isinstance(value, bool):
                return value
            if value is None:
                return bool(default)
            if isinstance(value, (int, float)):
                return bool(value)
            return str(value).strip().lower() in {"true", "1", "yes", "on"}

        def get_int(key: str, default: int) -> int:
            value = self.config.get(key, default)
            try:
                return int(value)
            except (TypeError, ValueError):
                return int(default)

        def get_float(key: str, default: float) -> float:
            value = self.config.get(key, default)
            try:
                return float(value)
            except (TypeError, ValueError):
                return float(default)

        def get_list(key: str, default: str = "") -> List[str]:
            raw_value = self.config.get(key, default)
            if raw_value is None:
                return []
            if isinstance(raw_value, (list, tuple)):
                return [str(item).strip() for item in raw_value if str(item).strip()]
            return [item.strip() for item in str(raw_value).split(",") if item.strip()]

        self.interval = get_int("interval", 15)
        self.verbose = get_bool("verbose", False)
        self.retry_count = get_int("retry_count", 3)
        self.success_http_codes = [
            int(code.strip())
            for code in str(self.config.get("success_http_codes", "200")).split(",")
            if code.strip()
        ] or [200]
        self.alert_threshold = get_int("alert_threshold", 3)
        self.domains = get_list("domains", "google.com")
        self.ping_ips = get_list("ping_ips", "1.1.1.1")
        websites_config = self.config.get("check_website")
        self.websites = get_list("check_website") if websites_config else []
        self.enable_website_check = get_bool("enable_website_check", False)
        self.ssl_check_domains = get_list("ssl_check_domains", "google.com")
        self.enable_ssl_check = get_bool("enable_ssl_check", False)
        self.enable_ping = get_bool("enable_ping", True)
        self.enable_dns = get_bool("enable_dns", True)
        self.ssl_warn_days = get_int("ssl_warn_days", 30)
        self.ssl_critical_days = get_int("ssl_critical_days", 7)
        self.notify_recovery = get_bool("notify_recovery", True)

        self.show_only_success = get_bool("show_only_success", False)
        self.show_only_failure = get_bool("show_only_failure", False)

        self.enable_advanced_stats = get_bool("enable_advanced_stats", False)
        self.summary_interval = max(0, get_int("summary_interval_seconds", 0))
        self.store_stats_log = get_bool("store_stats_log", False)
        self.stats_log_format = str(self.config.get("stats_log_format", "csv")).lower()
        self.stats_log_max_size = get_int("stats_log_max_size", 1048576)
        self.stats_log_backup_count = get_int("stats_log_backup_count", 5)
        self.persist_stats = get_bool("persist_stats", False)
        self.flap_threshold = get_int("flap_threshold", 5)
        self.flap_window_seconds = get_int("flap_window_seconds", 300)
        log_dir = self.log_dir
        self.stats_log_file = str(self.config.get("stats_log_file", os.path.join(log_dir, "pingpanda_stats.csv")))
        self.stats_persistence_file = str(
            self.config.get("stats_persistence_file", os.path.join(log_dir, "pingpanda_stats.pkl"))
        )

        self.slack_webhook_url = self.config.get("slack_webhook_url")
        self.teams_webhook_url = self.config.get("teams_webhook_url")
        self.discord_webhook_url = self.config.get("discord_webhook_url")
        self.slack_channel = self.config.get("slack_channel")
        self.slack_username = self.config.get("slack_username", "PingPanda")
        self.slack_icon_emoji = self.config.get("slack_icon_emoji")
        self.discord_username = self.config.get("discord_username", "PingPanda")
        self.discord_avatar_url = self.config.get("discord_avatar_url")
        self.notification_retry_attempts = max(1, get_int("notification_retry_attempts", 3))
        self.notification_retry_backoff = max(0.0, get_float("notification_retry_backoff_seconds", 1.0))

        self.enable_prometheus = get_bool("enable_prometheus", False)
        self.prometheus_port = get_int("prometheus_port", 9090)

        self.enable_adaptive_backoff = get_bool("enable_adaptive_backoff", True)
        self.backoff_min_seconds = max(1.0, get_float("backoff_min_seconds", 10.0))
        self.backoff_max_seconds = max(self.backoff_min_seconds, get_float("backoff_max_seconds", 300.0))
        self.circuit_breaker_threshold = max(1, get_int("circuit_breaker_threshold", 5))
        self.circuit_breaker_cooldown = max(10.0, get_float("circuit_breaker_cooldown_seconds", 60.0))

    def _setup_prometheus(self) -> None:
        if not self.enable_prometheus:
            return

        exports = self._ensure_prometheus()
        if not exports:
            self.logger.warning(
                "Prometheus metrics requested but prometheus_client is not installed; disabling metrics."
            )
            self.enable_prometheus = False
            return

        counter = exports["Counter"]
        gauge = exports["Gauge"]
        summary = exports["Summary"]
        start_server = exports["start_http_server"]

        self.dns_status = gauge("pingpanda_dns_status", "DNS resolution status", ["domain"])
        self.ping_status = gauge("pingpanda_ping_status", "Ping status", ["target"])
        self.website_status = gauge("pingpanda_website_status", "Website check status", ["url"])
        self.ssl_status = gauge("pingpanda_ssl_status", "SSL certificate status", ["domain"])

        self.dns_response_time = summary("pingpanda_dns_response_seconds", "DNS resolution time", ["domain"])
        self.ping_response_time = summary("pingpanda_ping_response_seconds", "Ping response time", ["target"])
        self.website_response_time = summary("pingpanda_website_response_seconds", "Website response time", ["url"])

        self.ssl_days_remaining = gauge("pingpanda_ssl_days_remaining", "Days until SSL certificate expiry", ["domain"])

        self.dns_errors = counter("pingpanda_dns_errors_total", "Total DNS resolution errors", ["domain"])
        self.ping_errors = counter("pingpanda_ping_errors_total", "Total ping errors", ["target"])
        self.website_errors = counter("pingpanda_website_errors_total", "Total website check errors", ["url"])
        self.ssl_errors = counter("pingpanda_ssl_errors_total", "Total SSL check errors", ["domain"])

        start_server(self.prometheus_port)
        self.logger.info("Prometheus metrics server started on port %s", self.prometheus_port)

    @classmethod
    def _ensure_prometheus(cls) -> Optional[Dict[str, Any]]:
        if cls._prometheus_exports is not None:
            return cls._prometheus_exports

        try:
            module = import_module("prometheus_client")
        except ImportError:
            cls._prometheus_exports = None
            return None

        cls._prometheus_exports = {
            "Counter": getattr(module, "Counter"),
            "Gauge": getattr(module, "Gauge"),
            "Summary": getattr(module, "Summary"),
            "start_http_server": getattr(module, "start_http_server"),
        }
        return cls._prometheus_exports

    def _initialize_components(self) -> None:
        stats_persistence_settings = StatsPersistenceSettings(
            enabled=self.enable_advanced_stats and self.persist_stats,
            file_path=self.stats_persistence_file,
        )
        status_dir_override = self.config.get("status_dir")
        status_dir = str(status_dir_override) if status_dir_override else None
        self.persistence = PersistenceManager(
            self.logger,
            base_dir=self.log_dir,
            stats_settings=stats_persistence_settings,
            status_dir=status_dir,
        )

        self._filter_log_tracker: Set[str] = set()

        notification_settings = NotificationSettings(
            alert_threshold=self.alert_threshold,
            notify_recovery=self.notify_recovery,
            retry_attempts=self.notification_retry_attempts,
            retry_backoff=self.notification_retry_backoff,
            slack_webhook_url=self.slack_webhook_url,
            teams_webhook_url=self.teams_webhook_url,
            discord_webhook_url=self.discord_webhook_url,
            slack_channel=self.slack_channel,
            slack_username=self.slack_username,
            slack_icon_emoji=self.slack_icon_emoji,
            discord_username=self.discord_username,
            discord_avatar_url=self.discord_avatar_url,
        )
        self.notifier = NotificationManager(self.logger, self.persistence, notification_settings)

        if self.enable_advanced_stats:
            stats_settings = StatsSettings(
                enable=True,
                summary_interval=self.summary_interval,
                log_enabled=self.store_stats_log,
                log_file=self.stats_log_file,
                log_format=self.stats_log_format,
                log_max_size=self.stats_log_max_size,
                log_backup_count=self.stats_log_backup_count,
                persist=self.persist_stats,
                flap_threshold=self.flap_threshold,
                flap_window_seconds=self.flap_window_seconds,
            )
            self.stats_manager = StatsManager(self.logger, stats_settings, persistence=self.persistence)
            self.stats_manager.load()
            self.stats_logger = self.stats_manager.stats_logger
            self.ip_stats = self.stats_manager.ip_stats
        else:
            self.stats_manager = None
            self.stats_logger = None
            self.ip_stats: Dict[str, Any] = {}

        self.last_summary_time: Optional[datetime] = datetime.now() if self.enable_advanced_stats else None

        self.failure_tracker = FailureTracker(
            enable_backoff=self.enable_adaptive_backoff,
            min_backoff_seconds=self.backoff_min_seconds,
            max_backoff_seconds=self.backoff_max_seconds,
            circuit_threshold=self.circuit_breaker_threshold,
            circuit_cooldown_seconds=self.circuit_breaker_cooldown,
        )

        self._check_deps = CheckDependencies(app=self, stats=self.stats_manager)
        self._dns_check = DNSCheck(self._check_deps)
        self._ping_check = PingCheck(self._check_deps)
        self._website_check = WebsiteCheck(self._check_deps)
        self._ssl_check = SSLCheck(self._check_deps)

        self._build_check_jobs()
        self._setup_thread_pool()

    def _build_check_jobs(self) -> None:
        self._check_jobs: List[Callable[[], None]] = []
        if self.enable_dns:
            self._check_jobs.append(self._dns_check.run)
        if self.enable_ping:
            self._check_jobs.append(self._ping_check.run)
        if self.enable_website_check and self.websites:
            self._check_jobs.append(self._website_check.run)
        if self.enable_ssl_check:
            self._check_jobs.append(self._ssl_check.run)

    def _setup_thread_pool(self) -> None:
        worker_count = len(getattr(self, "_check_jobs", []))
        if worker_count == 0:
            self._thread_pool = None
            return

        self._thread_pool = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="pingpanda-check")
        self.logger.debug("Thread pool initialized with %s worker(s).", worker_count)

    def send_notification(self, message: str, status: str, check_type: str, target: str) -> None:
        self.notifier.notify(message, status=status, check_type=check_type, target=target)

    def _log_filter_notice(self, key: str, message: str, level: int = logging.INFO) -> None:
        if key not in self._filter_log_tracker:
            self.logger.log(level, message)
            self._filter_log_tracker.add(key)

    def _should_log_result(self, is_success: bool) -> bool:
        if not self.show_only_success and not self.show_only_failure:
            return True

        if self.show_only_success and self.show_only_failure:
            self._log_filter_notice(
                "conflicting",
                "Filtering disabled output: both SHOW_ONLY_SUCCESS and SHOW_ONLY_FAILURE are enabled.",
                level=logging.WARNING,
            )
            return False

        if self.show_only_success:
            if is_success:
                return True
            self._log_filter_notice(
                "hide_failure",
                "Filtering active (SHOW_ONLY_SUCCESS=true); suppressing failed results.",
            )
            return False

        if self.show_only_failure:
            if not is_success:
                return True
            self._log_filter_notice(
                "hide_success",
                "Filtering active (SHOW_ONLY_FAILURE=true); suppressing successful results.",
            )
            return False

        return True

    def _output_stats_summary(self) -> None:
        if not self.stats_manager:
            return
        self.stats_manager.output_summary()

    def _maybe_output_summary(self) -> None:
        if not self.stats_manager or self.summary_interval <= 0:
            return

        now = datetime.now()
        if self.last_summary_time is None or (now - self.last_summary_time).total_seconds() >= self.summary_interval:
            self.stats_manager.output_summary()
            self.last_summary_time = now

    def output_status_summary(self) -> None:
        self.logger.info("=== PingPanda Status Summary ===")
        self.logger.info("Running with interval: %s seconds", self.interval)

        checks: List[str] = []
        if self.enable_dns:
            checks.append(f"DNS Resolution (domains: {', '.join(self.domains)})")
        if self.enable_ping:
            checks.append(f"Ping (targets: {', '.join(self.ping_ips)})")
        if self.enable_website_check and self.websites:
            checks.append(f"Website (URLs: {', '.join(self.websites)})")
        if self.enable_ssl_check:
            checks.append(f"SSL Certificates (domains: {', '.join(self.ssl_check_domains)})")

        self.logger.info("Active checks: %s", len(checks))
        for check in checks:
            self.logger.info("  - %s", check)

        if self.show_only_success:
            self.logger.info("Filtering: Showing only SUCCESSFUL results")
        elif self.show_only_failure:
            self.logger.info("Filtering: Showing only FAILED results")
        elif self.show_only_success and self.show_only_failure:
            self.logger.warning("Filtering: Both success and failure filters enabled - no results will be shown")
        else:
            self.logger.info("Filtering: Showing ALL results")

        if self.enable_adaptive_backoff:
            self.logger.info(
                "Adaptive backoff: ENABLED (min: %ss, max: %ss)",
                self.backoff_min_seconds,
                self.backoff_max_seconds
            )
            self.logger.info(
                "Circuit breaker: threshold=%s failures, cooldown=%ss",
                self.circuit_breaker_threshold,
                self.circuit_breaker_cooldown
            )
        else:
            self.logger.info("Adaptive backoff: DISABLED")

        self.logger.info("===============================")

    def run(self) -> None:
        self.output_status_summary()

        if self.enable_advanced_stats:
            self.logger.info("Advanced statistics tracking: ENABLED")
            if self.summary_interval > 0:
                self.logger.info("Statistics summary interval: %s seconds", self.summary_interval)
            if self.store_stats_log:
                self.logger.info("Statistics logging: ENABLED -> %s", self.stats_log_file)
            if self.flap_threshold > 0:
                self.logger.info(
                    "Flapping detection threshold: %s status changes in %ss",
                    self.flap_threshold,
                    self.flap_window_seconds,
                )

        try:
            while True:
                loop_start = time.time()
                self._filter_log_tracker.clear()

                if self._thread_pool and self._check_jobs:
                    futures: List[Future[None]] = [self._thread_pool.submit(job) for job in self._check_jobs]
                    for future in futures:
                        future.result()
                else:
                    for job in self._check_jobs:
                        job()

                self._maybe_output_summary()

                elapsed = time.time() - loop_start
                remaining = max(0.0, self.interval - elapsed)
                time.sleep(remaining)
        except KeyboardInterrupt:
            self.logger.info("Shutting down gracefully...")
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        if self._thread_pool:
            self._thread_pool.shutdown(wait=True)
            self._thread_pool = None
        if self.stats_manager:
            self.stats_manager.save()


__all__ = ["PingPanda", "NormalizedConfig"]
