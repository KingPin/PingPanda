import argparse
import csv
import json
import logging
import os
import pickle
import socket
import ssl
import time
from collections import deque
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Thread, Lock
from typing import Dict, List, Optional, Union, Any

import pythonping
import requests
from slack_sdk import WebClient
from prometheus_client import start_http_server, Gauge, Counter, Summary


class IPStats:
    """Track statistics for a single IP address."""
    
    def __init__(self, ip: str):
        self.ip = ip
        self.current_status = "unknown"  # "up", "down", "unknown"
        self.total_uptime = 0.0  # seconds
        self.total_downtime = 0.0  # seconds
        self.downtime_events = 0
        self.last_status_change = datetime.now()
        self.downtime_periods: List[Dict[str, datetime]] = []  # [{"start": datetime, "end": datetime}]
        self.status_change_times = deque(maxlen=20)  # For flapping detection
        self.is_flapping = False
        self.last_check_time = datetime.now()
        self._status_start_time = datetime.now()
        
    def update_status(self, new_status: str, timestamp: Optional[datetime] = None) -> bool:
        """
        Update the status and calculate uptime/downtime.
        
        Returns:
            bool: True if status changed, False otherwise
        """
        if timestamp is None:
            timestamp = datetime.now()
            
        # Calculate time since last update
        time_delta = (timestamp - self.last_check_time).total_seconds()
        
        # Add time to current status
        if self.current_status == "up":
            self.total_uptime += time_delta
        elif self.current_status == "down":
            self.total_downtime += time_delta
            
        self.last_check_time = timestamp
        
        # Check if status changed
        status_changed = self.current_status != new_status
        
        if status_changed:
            # Handle downtime period tracking
            if self.current_status == "down" and new_status == "up":
                # End of downtime period
                if self.downtime_periods and "end" not in self.downtime_periods[-1]:
                    self.downtime_periods[-1]["end"] = timestamp
            elif self.current_status == "up" and new_status == "down":
                # Start of downtime period
                self.downtime_events += 1
                self.downtime_periods.append({"start": timestamp})
                
            # Update status change tracking
            self.last_status_change = timestamp
            self.status_change_times.append(timestamp)
            self.current_status = new_status
            self._status_start_time = timestamp
            
        return status_changed
        
    def check_flapping(self, threshold: int, window_seconds: int) -> bool:
        """
        Check if the IP is flapping (too many status changes in time window).
        
        Args:
            threshold: Maximum number of status changes allowed
            window_seconds: Time window in seconds
            
        Returns:
            bool: True if flapping detected
        """
        if len(self.status_change_times) < threshold:
            return False
            
        now = datetime.now()
        window_start = now - timedelta(seconds=window_seconds)
        
        # Count status changes within the window
        recent_changes = [t for t in self.status_change_times if t >= window_start]
        
        self.is_flapping = len(recent_changes) >= threshold
        return self.is_flapping
        
    def get_current_status_duration(self) -> float:
        """Get duration in seconds of current status."""
        return (datetime.now() - self._status_start_time).total_seconds()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary for serialization."""
        return {
            "ip": self.ip,
            "current_status": self.current_status,
            "total_uptime": self.total_uptime,
            "total_downtime": self.total_downtime,
            "downtime_events": self.downtime_events,
            "last_status_change": self.last_status_change.isoformat(),
            "downtime_periods": [
                {
                    "start": period["start"].isoformat(),
                    "end": period["end"].isoformat() if "end" in period else None
                }
                for period in self.downtime_periods
            ],
            "is_flapping": self.is_flapping,
            "current_status_duration": self.get_current_status_duration()
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPStats':
        """Create IPStats from dictionary."""
        stats = cls(data["ip"])
        stats.current_status = data["current_status"]
        stats.total_uptime = data["total_uptime"]
        stats.total_downtime = data["total_downtime"]
        stats.downtime_events = data["downtime_events"]
        stats.last_status_change = datetime.fromisoformat(data["last_status_change"])
        stats.is_flapping = data.get("is_flapping", False)
        
        # Reconstruct downtime periods
        stats.downtime_periods = []
        for period in data.get("downtime_periods", []):
            p = {"start": datetime.fromisoformat(period["start"])}
            if period["end"]:
                p["end"] = datetime.fromisoformat(period["end"])
            stats.downtime_periods.append(p)
            
        return stats


class StatsLogger:
    """Handle logging of statistics in CSV or JSON format."""
    
    def __init__(self, log_file: str, format_type: str = "csv", max_size: int = 1048576, backup_count: int = 5):
        self.log_file = log_file
        self.format_type = format_type.lower()
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # Setup rotating file handler
        self.handler = RotatingFileHandler(
            log_file, 
            maxBytes=max_size, 
            backupCount=backup_count
        )
        
        # Write CSV header if file is new and format is CSV
        if self.format_type == "csv" and not os.path.exists(log_file):
            self._write_csv_header()
            
    def _write_csv_header(self):
        """Write CSV header row."""
        header = [
            "timestamp", "ip", "current_status", "total_uptime", "total_downtime",
            "downtime_events", "last_status_change", "current_status_duration",
            "is_flapping"
        ]
        with open(self.log_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            
    def log_stats(self, ip_stats: Dict[str, IPStats], overall_stats: Dict[str, Any]):
        """Log statistics to file."""
        timestamp = datetime.now().isoformat()
        
        if self.format_type == "csv":
            self._log_csv(timestamp, ip_stats, overall_stats)
        else:
            self._log_json(timestamp, ip_stats, overall_stats)
            
    def _log_csv(self, timestamp: str, ip_stats: Dict[str, IPStats], overall_stats: Dict[str, Any]):
        """Log in CSV format."""
        # Use file rotation
        if os.path.getsize(self.log_file) > self.handler.maxBytes:
            self.handler.doRollover()
            
        with open(self.log_file, 'a', newline='') as f:
            writer = csv.writer(f)
            
            # Write IP stats
            for stats in ip_stats.values():
                writer.writerow([
                    timestamp,
                    stats.ip,
                    stats.current_status,
                    f"{stats.total_uptime:.2f}",
                    f"{stats.total_downtime:.2f}",
                    stats.downtime_events,
                    stats.last_status_change.isoformat(),
                    f"{stats.get_current_status_duration():.2f}",
                    stats.is_flapping
                ])
                
            # Write overall stats
            writer.writerow([
                timestamp,
                "OVERALL",
                "summary",
                f"{overall_stats['total_uptime']:.2f}",
                f"{overall_stats['total_downtime']:.2f}",
                overall_stats['total_downtime_events'],
                "",
                "",
                overall_stats['total_flapping_ips']
            ])
            
    def _log_json(self, timestamp: str, ip_stats: Dict[str, IPStats], overall_stats: Dict[str, Any]):
        """Log in JSON format."""
        # Use file rotation
        if os.path.getsize(self.log_file) > self.handler.maxBytes:
            self.handler.doRollover()
            
        log_entry = {
            "timestamp": timestamp,
            "ip_stats": {ip: stats.to_dict() for ip, stats in ip_stats.items()},
            "overall_stats": overall_stats
        }
        
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')


class PingPanda:
    """
    PingPanda - A modern network monitoring tool written in Python.
    Monitors DNS resolution, ping response, website availability, and SSL certificate expiry.
    """

    def __init__(self, config: Optional[Dict[str, Union[str, int, bool]]] = None):
        """Initialize the PingPanda monitoring tool with configuration."""
        self.config = config or {}
        self._setup_logging()
        self._load_config()
        self._initialize_status_tracking()
        self._setup_prometheus()  # Add this line
        self.logger.info(f"PingPanda started on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    def _setup_logging(self):
        """Configure logging with console and file handlers if enabled."""
        log_level = getattr(logging, str(self.config.get("LOG_LEVEL", "INFO")).upper())
        log_dir = str(self.config.get("LOG_DIR", "/logs"))
        log_file = os.path.join(log_dir, str(self.config.get("LOG_FILE", "pingpanda.log")))
        max_log_size = int(self.config.get("MAX_LOG_SIZE", 1048576))  # 1MB default
        log_backup_count = int(self.config.get("LOG_BACKUP_COUNT", 5))
        
        # Create log directory if it doesn't exist
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        self.logger = logging.getLogger("pingpanda")
        self.logger.setLevel(log_level)
        
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        
        if str(self.config.get("LOG_TO_TERMINAL", "true")).lower() == "true":
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        if str(self.config.get("LOG_TO_FILE", "true")).lower() == "true":
            file_handler = RotatingFileHandler(
                log_file, maxBytes=max_log_size, backupCount=log_backup_count
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
    
    def _load_config(self):
        """Load configuration from environment variables with defaults."""
        self.interval = int(self.config.get("INTERVAL", 15))
        self.verbose = str(self.config.get("VERBOSE", "false")).lower() == "true"
        self.retry_count = int(self.config.get("RETRY_COUNT", 3))
        self.success_http_codes = [
            int(code) for code in str(self.config.get("SUCCESS_HTTP_CODES", "200")).split(",")
        ]
        self.alert_threshold = int(self.config.get("ALERT_THRESHOLD", 3))
        self.domains = str(self.config.get("DOMAINS", "google.com")).split(",")
        self.ping_ips = str(self.config.get("PING_IPS", "1.1.1.1")).split(",")
        self.websites = str(self.config.get("CHECK_WEBSITE", "")).split(",") if self.config.get("CHECK_WEBSITE") else []
        self.enable_website_check = str(self.config.get("ENABLE_WEBSITE_CHECK", "false")).lower() == "true"
        self.ssl_check_domains = str(self.config.get("SSL_CHECK_DOMAINS", "google.com")).split(",")
        self.enable_ssl_check = str(self.config.get("ENABLE_SSL_CHECK", "false")).lower() == "true"
        self.enable_ping = str(self.config.get("ENABLE_PING", "true")).lower() == "true"
        self.enable_dns = str(self.config.get("ENABLE_DNS", "true")).lower() == "true"
        self.ssl_warn_days = int(self.config.get("SSL_WARN_DAYS", 30))
        self.ssl_critical_days = int(self.config.get("SSL_CRITICAL_DAYS", 7))
        self.notify_recovery = str(self.config.get("NOTIFY_RECOVERY", "true")).lower() == "true"
        
        # Filtering options
        self.show_only_success = str(self.config.get("SHOW_ONLY_SUCCESS", "false")).lower() == "true"
        self.show_only_failure = str(self.config.get("SHOW_ONLY_FAILURE", "false")).lower() == "true"
        
        # Stats tracking configuration
        self.summary_interval = int(self.config.get("SUMMARY_INTERVAL_SECONDS", 120))
        self.store_stats_log = str(self.config.get("STORE_STATS_LOG", "false")).lower() == "true"
        self.stats_log_format = str(self.config.get("STATS_LOG_FORMAT", "csv")).lower()
        self.stats_log_max_size = int(self.config.get("STATS_LOG_MAX_SIZE", 1048576))  # 1MB
        self.stats_log_backup_count = int(self.config.get("STATS_LOG_BACKUP_COUNT", 5))
        self.persist_stats = str(self.config.get("PERSIST_STATS", "false")).lower() == "true"
        self.flap_threshold = int(self.config.get("FLAP_THRESHOLD", 5))
        self.flap_window_seconds = int(self.config.get("FLAP_WINDOW_SECONDS", 300))  # 5 minutes
        
        # Notification settings
        self.slack_webhook_url = self.config.get("SLACK_WEBHOOK_URL")
        self.teams_webhook_url = self.config.get("TEAMS_WEBHOOK_URL")
        self.discord_webhook_url = self.config.get("DISCORD_WEBHOOK_URL")
        
        # Initialize Slack client if webhook URL is provided
        self.slack_client = WebClient(token=self.slack_webhook_url) if self.slack_webhook_url else None
        
        # Add Prometheus configuration
        self.enable_prometheus = str(self.config.get("ENABLE_PROMETHEUS", "false")).lower() == "true"
        self.prometheus_port = int(self.config.get("PROMETHEUS_PORT", "9090"))
    
    def _setup_prometheus(self):
        """Initialize Prometheus metrics if enabled."""
        if not self.enable_prometheus:
            return
            
        # Status metrics (1=OK, 0=Error)
        self.dns_status = Gauge('pingpanda_dns_status', 'DNS resolution status', ['domain'])
        self.ping_status = Gauge('pingpanda_ping_status', 'Ping status', ['target'])
        self.website_status = Gauge('pingpanda_website_status', 'Website check status', ['url'])
        self.ssl_status = Gauge('pingpanda_ssl_status', 'SSL certificate status', ['domain'])
        
        # Response time metrics
        self.dns_response_time = Summary('pingpanda_dns_response_seconds', 'DNS resolution time', ['domain'])
        self.ping_response_time = Summary('pingpanda_ping_response_seconds', 'Ping response time', ['target'])
        self.website_response_time = Summary('pingpanda_website_response_seconds', 'Website response time', ['url'])
        
        # SSL specific metrics
        self.ssl_days_remaining = Gauge('pingpanda_ssl_days_remaining', 'Days until SSL certificate expiry', ['domain'])
        
        # Error counters
        self.dns_errors = Counter('pingpanda_dns_errors_total', 'Total DNS resolution errors', ['domain'])
        self.ping_errors = Counter('pingpanda_ping_errors_total', 'Total ping errors', ['target'])
        self.website_errors = Counter('pingpanda_website_errors_total', 'Total website check errors', ['url'])
        self.ssl_errors = Counter('pingpanda_ssl_errors_total', 'Total SSL check errors', ['domain'])
        
        # Start the HTTP server
        start_http_server(self.prometheus_port)
        self.logger.info(f"Prometheus metrics server started on port {self.prometheus_port}")
    
    def _initialize_status_tracking(self):
        """Initialize status tracking for alert thresholds and recovery notifications."""
        self.status_dir = os.path.join(str(self.config.get("LOG_DIR", "/logs")), "status")
        os.makedirs(self.status_dir, exist_ok=True)
        self.failure_counts = {}
        
        # Initialize IP stats tracking
        self.ip_stats: Dict[str, IPStats] = {}
        self.stats_lock = Lock()  # Thread safety for stats updates
        self.last_summary_time = datetime.now()
        
        # Setup stats logger if enabled
        if self.store_stats_log:
            stats_log_file = os.path.join(str(self.config.get("LOG_DIR", "/logs")), "ping_stats.log")
            self.stats_logger = StatsLogger(
                stats_log_file,
                self.stats_log_format,
                self.stats_log_max_size,
                self.stats_log_backup_count
            )
        else:
            self.stats_logger = None
            
        # Load persisted stats if enabled
        if self.persist_stats:
            self._load_persisted_stats()
            
        # Initialize IP stats for all ping targets
        for ip in self.ping_ips:
            if ip not in self.ip_stats:
                self.ip_stats[ip] = IPStats(ip)
        
    def _update_status_tracking(self, check_type: str, target: str, status: str) -> bool:
        """
        Update status tracking for a check and determine if notification is needed.
        
        Args:
            check_type: Type of check (DNS, Ping, etc.)
            target: The target being checked (domain, IP, etc.)
            status: 'ok' or 'error'
            
        Returns:
            bool: True if notification should be sent, False otherwise
        """
        status_key = f"{check_type}_{target}"
        status_file = os.path.join(self.status_dir, status_key.replace("/", "_"))
        
        if status == "error":
            # For errors, track consecutive failures
            if status_key in self.failure_counts:
                self.failure_counts[status_key] += 1
            else:
                self.failure_counts[status_key] = 1
                
            with open(status_file, "w") as f:
                f.write(str(self.failure_counts[status_key]))
                
            # Only notify if we hit threshold
            return self.failure_counts[status_key] >= self.alert_threshold
            
        elif status == "ok":
            # For success, check if we previously had an error
            should_notify = False
            if status_key in self.failure_counts and self.failure_counts[status_key] >= self.alert_threshold:
                should_notify = self.notify_recovery
            
            # Reset the counter
            self.failure_counts[status_key] = 0
            if os.path.exists(status_file):
                os.remove(status_file)
                
            return should_notify
            
        return False

    def _load_persisted_stats(self):
        """Load persisted IP stats from file."""
        stats_file = os.path.join(self.status_dir, "ip_stats.pkl")
        if os.path.exists(stats_file):
            try:
                with open(stats_file, 'rb') as f:
                    saved_stats = pickle.load(f)
                    for ip, stats_data in saved_stats.items():
                        self.ip_stats[ip] = IPStats.from_dict(stats_data)
                self.logger.info(f"Loaded persisted stats for {len(self.ip_stats)} IPs")
            except Exception as e:
                self.logger.warning(f"Failed to load persisted stats: {e}")
                
    def _save_persisted_stats(self):
        """Save IP stats to file."""
        if not self.persist_stats:
            return
            
        stats_file = os.path.join(self.status_dir, "ip_stats.pkl")
        try:
            stats_data = {ip: stats.to_dict() for ip, stats in self.ip_stats.items()}
            with open(stats_file, 'wb') as f:
                pickle.dump(stats_data, f)
        except Exception as e:
            self.logger.error(f"Failed to save persisted stats: {e}")
            
    def _update_ip_stats(self, ip: str, success: bool):
        """Update IP statistics with current check result."""
        with self.stats_lock:
            if ip not in self.ip_stats:
                self.ip_stats[ip] = IPStats(ip)
                
            stats = self.ip_stats[ip]
            new_status = "up" if success else "down"
            status_changed = stats.update_status(new_status)
            
            # Check for flapping
            if status_changed:
                was_flapping = stats.is_flapping
                is_flapping = stats.check_flapping(self.flap_threshold, self.flap_window_seconds)
                
                if is_flapping and not was_flapping:
                    self.logger.warning(f"Flapping detected for IP {ip}")
                    self.send_notification(
                        f"IP {ip} is flapping (>{self.flap_threshold} status changes in {self.flap_window_seconds}s)",
                        status="error",
                        check_type="Flapping",
                        target=ip
                    )
                elif not is_flapping and was_flapping:
                    self.logger.info(f"Flapping resolved for IP {ip}")
                    
                # Log status change
                if success and not was_flapping:
                    self.logger.info(f"IP {ip} recovered (was down for {stats.total_downtime:.1f}s)")
                    
            return status_changed

    def _should_log_result(self, is_success: bool) -> bool:
        """
        Determine if a result should be logged based on filtering configuration.
        
        Args:
            is_success: True if the check was successful, False if it failed
            
        Returns:
            bool: True if the result should be logged, False otherwise
        """
        # If both filters are disabled, show everything
        if not self.show_only_success and not self.show_only_failure:
            return True
            
        # If only success filter is enabled, show only successes
        if self.show_only_success and not self.show_only_failure:
            return is_success
            
        # If only failure filter is enabled, show only failures
        if self.show_only_failure and not self.show_only_success:
            return not is_success
            
        # If both filters are enabled, show nothing (conflicting filters)
        if self.show_only_success and self.show_only_failure:
            self.logger.warning("Both SHOW_ONLY_SUCCESS and SHOW_ONLY_FAILURE are enabled. No results will be displayed.")
            return False
            
        return True

    def send_notification(self, message: str, status: str = "error", check_type: str = "general", target: str = "unknown"):
        """
        Send notifications to configured channels with improved formatting.
        Only sends after alert threshold is reached or on recovery.
        """
        # Check if we should send this notification based on threshold and status
        if not self._update_status_tracking(check_type, target, status):
            return
            
        # Create a more structured notification
        hostname = socket.gethostname()
        formatted_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emoji = "✅" if status == "ok" else "🔴"
        
        title = f"PingPanda: {emoji} {check_type} check for {target}"
        formatted_message = f"*Host:* {hostname}\n*Time:* {formatted_time}\n*Status:* {status}\n*Message:* {message}"
        
        # Send to Slack
        if self.slack_webhook_url:
            try:
                color = "good" if status == "ok" else "danger"
                self.slack_client.chat_postMessage(
                    channel="#general",
                    text=title,
                    attachments=[{
                        "color": color,
                        "text": formatted_message,
                        "mrkdwn_in": ["text"]
                    }]
                )
            except Exception as e:
                self.logger.error(f"Failed to send Slack notification: {e}")
                
        # Send to Microsoft Teams
        if self.teams_webhook_url:
            try:
                color = "00FF00" if status == "ok" else "FF0000"
                requests.post(
                    self.teams_webhook_url,
                    json={
                        "@type": "MessageCard",
                        "@context": "http://schema.org/extensions",
                        "themeColor": color,
                        "title": title,
                        "text": formatted_message
                    },
                    timeout=5
                )
            except Exception as e:
                self.logger.error(f"Failed to send Teams notification: {e}")
                
        # Send to Discord
        if self.discord_webhook_url:
            try:
                color = 65280 if status == "ok" else 16711680  # Green or Red
                requests.post(
                    self.discord_webhook_url,
                    json={
                        "embeds": [{
                            "title": title,
                            "description": formatted_message,
                            "color": color
                        }]
                    },
                    timeout=5
                )
            except Exception as e:
                self.logger.error(f"Failed to send Discord notification: {e}")

    def check_dns(self):
        """Check DNS resolution for configured domains."""
        if not self.enable_dns:
            return
            
        self.logger.info("Starting DNS resolution checks...")
        for domain in self.domains:
            start_time = time.perf_counter()
            success = False
            
            for i in range(self.retry_count):
                try:
                    socket.gethostbyname(domain)
                    end_time = time.perf_counter()
                    duration = end_time - start_time  # In seconds for Prometheus
                    duration_ms = duration * 1000     # In milliseconds for logging
                    
                    if self._should_log_result(True):
                        self.logger.info(f"DNS Resolution for {domain}: PASS (Time: {duration_ms:.2f}ms)")
                    
                    # Update Prometheus metrics
                    if self.enable_prometheus:
                        self.dns_status.labels(domain=domain).set(1)  # 1 = OK
                        self.dns_response_time.labels(domain=domain).observe(duration)
                    
                    self.send_notification(
                        f"DNS resolution successful in {duration_ms:.2f}ms",
                        status="ok",
                        check_type="DNS",
                        target=domain
                    )
                    success = True
                    break
                except socket.gaierror as e:
                    if self.verbose:
                        self.logger.debug(f"DNS Resolution attempt {i+1} for {domain} failed: {e}")
                    time.sleep(1)
                    
            if not success:
                if self._should_log_result(False):
                    self.logger.error(f"DNS Resolution for {domain}: FAIL")
                
                # Update Prometheus metrics for failure
                if self.enable_prometheus:
                    self.dns_status.labels(domain=domain).set(0)  # 0 = ERROR
                    self.dns_errors.labels(domain=domain).inc()
                    
                self.send_notification(
                    f"Failed to resolve domain after {self.retry_count} attempts",
                    status="error",
                    check_type="DNS",
                    target=domain
                )

    def check_ping(self):
        """Check ping for configured IP addresses."""
        if not self.enable_ping:
            return
            
        self.logger.info("Starting ping checks...")
        for ip in self.ping_ips:
            success = False
            start_time = time.perf_counter()
            
            for i in range(self.retry_count):
                try:
                    response_list = pythonping.ping(ip, count=1, timeout=2)
                    if response_list.success():
                        end_time = time.perf_counter()
                        duration = (end_time - start_time) * 1000
                        duration_seconds = (end_time - start_time)  # For Prometheus
                        
                        if self._should_log_result(True):
                            self.logger.info(f"Ping to {ip}: PASS (Time: {response_list.rtt_avg_ms:.2f}ms)")
                        
                        # Update Prometheus metrics
                        if self.enable_prometheus:
                            self.ping_status.labels(target=ip).set(1)  # 1 = OK
                            self.ping_response_time.labels(target=ip).observe(duration_seconds)
                        
                        # Update IP stats
                        status_changed = self._update_ip_stats(ip, True)
                        
                        self.send_notification(
                            f"Ping successful in {response_list.rtt_avg_ms:.2f}ms",
                            status="ok",
                            check_type="Ping",
                            target=ip
                        )
                        success = True
                        break
                    elif self.verbose:
                        self.logger.debug(f"Ping attempt {i+1} to {ip} failed")
                    time.sleep(1)
                except Exception as e:
                    if self.verbose:
                        self.logger.debug(f"Ping attempt {i+1} to {ip} failed: {e}")
                    time.sleep(1)
                    
            if not success:
                if self._should_log_result(False):
                    self.logger.error(f"Ping to {ip}: FAIL")
                
                # Update Prometheus metrics for failure
                if self.enable_prometheus:
                    self.ping_status.labels(target=ip).set(0)  # 0 = ERROR
                    self.ping_errors.labels(target=ip).inc()
                
                # Update IP stats
                status_changed = self._update_ip_stats(ip, False)
                
                self.send_notification(
                    f"Failed to ping host after {self.retry_count} attempts",
                    status="error",
                    check_type="Ping",
                    target=ip
                )

    def _get_overall_stats(self) -> Dict[str, Any]:
        """Calculate overall statistics across all IPs."""
        with self.stats_lock:
            total_uptime = sum(stats.total_uptime for stats in self.ip_stats.values())
            total_downtime = sum(stats.total_downtime for stats in self.ip_stats.values())
            total_downtime_events = sum(stats.downtime_events for stats in self.ip_stats.values())
            total_flapping_ips = sum(1 for stats in self.ip_stats.values() if stats.is_flapping)
            total_ips = len(self.ip_stats)
            ips_up = sum(1 for stats in self.ip_stats.values() if stats.current_status == "up")
            ips_down = sum(1 for stats in self.ip_stats.values() if stats.current_status == "down")
            
            return {
                "total_uptime": total_uptime,
                "total_downtime": total_downtime,
                "total_downtime_events": total_downtime_events,
                "total_flapping_ips": total_flapping_ips,
                "total_ips": total_ips,
                "ips_up": ips_up,
                "ips_down": ips_down,
                "overall_availability": (total_uptime / (total_uptime + total_downtime)) * 100 if (total_uptime + total_downtime) > 0 else 100
            }

    def _output_stats_summary(self):
        """Output a detailed statistics summary."""
        with self.stats_lock:
            self.logger.info("=== PingPanda IP Statistics Summary ===")
            
            overall_stats = self._get_overall_stats()
            
            # Overall statistics
            self.logger.info(f"Overall Status: {overall_stats['ips_up']}/{overall_stats['total_ips']} IPs UP")
            self.logger.info(f"Overall Availability: {overall_stats['overall_availability']:.2f}%")
            self.logger.info(f"Total Uptime: {overall_stats['total_uptime']:.1f}s")
            self.logger.info(f"Total Downtime: {overall_stats['total_downtime']:.1f}s")
            self.logger.info(f"Total Downtime Events: {overall_stats['total_downtime_events']}")
            if overall_stats['total_flapping_ips'] > 0:
                self.logger.warning(f"Flapping IPs: {overall_stats['total_flapping_ips']}")
            
            self.logger.info("")
            self.logger.info("Per-IP Statistics:")
            
            # Per-IP statistics
            for ip, stats in sorted(self.ip_stats.items()):
                status_emoji = "🟢" if stats.current_status == "up" else "🔴"
                flap_indicator = " 🔄" if stats.is_flapping else ""
                
                availability = (stats.total_uptime / (stats.total_uptime + stats.total_downtime)) * 100 if (stats.total_uptime + stats.total_downtime) > 0 else 100
                current_duration = stats.get_current_status_duration()
                
                self.logger.info(f"  {status_emoji} {ip} - {stats.current_status.upper()}{flap_indicator}")
                self.logger.info(f"    Availability: {availability:.2f}% | Current Status: {current_duration:.1f}s")
                self.logger.info(f"    Uptime: {stats.total_uptime:.1f}s | Downtime: {stats.total_downtime:.1f}s")
                self.logger.info(f"    Downtime Events: {stats.downtime_events} | Last Change: {stats.last_status_change.strftime('%H:%M:%S')}")
                
                if stats.downtime_periods:
                    recent_outages = stats.downtime_periods[-3:]  # Show last 3 outages
                    self.logger.info(f"    Recent Outages: {len(recent_outages)} (showing last 3)")
                    for i, period in enumerate(recent_outages):
                        start = period["start"].strftime('%H:%M:%S')
                        end = period["end"].strftime('%H:%M:%S') if "end" in period else "ongoing"
                        duration = (period["end"] - period["start"]).total_seconds() if "end" in period else current_duration
                        self.logger.info(f"      {i+1}. {start} - {end} ({duration:.1f}s)")
            
            self.logger.info("==========================================")
            
            # Log to stats file if enabled
            if self.stats_logger:
                self.stats_logger.log_stats(self.ip_stats, overall_stats)
                
            # Update last summary time
            self.last_summary_time = datetime.now()

    def _load_stats(self):
        """Load statistics from persistent storage if enabled."""
        if not self.config.get('enable_advanced_stats', False) or not self.config.get('persist_stats', False):
            return
            
        stats_file = str(self.config.get('stats_persistence_file', 'pingpanda_stats.pkl'))
        if os.path.exists(stats_file):
            try:
                with open(stats_file, 'rb') as f:
                    loaded_data = pickle.load(f)
                    
                with self.stats_lock:
                    self.ip_stats = loaded_data.get('ip_stats', {})
                    
                self.logger.info(f"Loaded statistics for {len(self.ip_stats)} IPs from {stats_file}")
            except Exception as e:
                self.logger.error(f"Failed to load stats from {stats_file}: {e}")

    def _save_stats(self):
        """Save statistics to persistent storage if enabled."""
        if not self.config.get('enable_advanced_stats', False) or not self.config.get('persist_stats', False):
            return
            
        stats_file = str(self.config.get('stats_persistence_file', 'pingpanda_stats.pkl'))
        try:
            with self.stats_lock:
                data_to_save = {
                    'ip_stats': self.ip_stats,
                    'saved_at': datetime.now()
                }
                
            with open(stats_file, 'wb') as f:
                pickle.dump(data_to_save, f)
                
            self.logger.debug(f"Saved statistics to {stats_file}")
        except Exception as e:
            self.logger.error(f"Failed to save stats to {stats_file}: {e}")

    def _cleanup(self):
        """Cleanup and save stats before shutdown."""
        self.logger.info("Performing cleanup...")
        self._save_stats()

    def check_website(self):
        """Check website availability and response codes."""
        if not self.enable_website_check or not self.websites:
            return
            
        self.logger.info("Starting website checks...")
        for website in self.websites:
            if not website:
                continue
                
            start_time = time.perf_counter()
            try:
                response = requests.get(website, timeout=10)
                end_time = time.perf_counter()
                duration = (end_time - start_time) * 1000  # Convert to milliseconds
                
                if response.status_code in self.success_http_codes:
                    if self._should_log_result(True):
                        self.logger.info(
                            f"Website check for {website}: PASS (HTTP Status: {response.status_code}, Time: {duration:.2f}ms)"
                        )
                    
                    # Update Prometheus metrics
                    if self.enable_prometheus:
                        self.website_status.labels(url=website).set(1)  # 1 = OK
                        self.website_response_time.labels(url=website).observe(duration / 1000)  # Convert to seconds
                    
                    self.send_notification(
                        f"Website check successful (HTTP {response.status_code}, {duration:.2f}ms)",
                        status="ok",
                        check_type="Website",
                        target=website
                    )
                else:
                    if self._should_log_result(False):
                        self.logger.error(
                            f"Website check for {website}: FAIL (HTTP Status: {response.status_code}, Time: {duration:.2f}ms)"
                        )
                    
                    # Update Prometheus metrics for failure
                    if self.enable_prometheus:
                        self.website_status.labels(url=website).set(0)  # 0 = ERROR
                        self.website_errors.labels(url=website).inc()
                    
                    self.send_notification(
                        f"Website check failed with HTTP status {response.status_code} ({duration:.2f}ms)",
                        status="error",
                        check_type="Website",
                        target=website
                    )
            except requests.exceptions.RequestException as e:
                if self._should_log_result(False):
                    self.logger.error(f"Website check for {website}: FAIL - {e}")
                
                # Update Prometheus metrics for exception
                if self.enable_prometheus:
                    self.website_status.labels(url=website).set(0)  # 0 = ERROR
                    self.website_errors.labels(url=website).inc()
                
                self.send_notification(
                    f"Website connection failed: {e}",
                    status="error",
                    check_type="Website",
                    target=website
                )

    def check_ssl_expiry(self):
        """Check SSL certificate expiry for configured domains."""
        if not self.enable_ssl_check:
            return
            
        self.logger.info("Starting SSL certificate checks...")
        for domain in self.ssl_check_domains:
            try:
                context = ssl.create_default_context()
                with socket.create_connection((domain, 443), timeout=5) as sock:
                    with context.wrap_socket(sock, server_hostname=domain) as ssock:
                        cert = ssock.getpeercert()
                        expiry_date = datetime.strptime(
                            cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
                        )
                        days_left = (expiry_date - datetime.now()).days
                        
                        # Update Prometheus metrics
                        if self.enable_prometheus:
                            self.ssl_days_remaining.labels(domain=domain).set(days_left)
                        
                        if days_left <= self.ssl_critical_days:
                            # Update Prometheus metrics for critical SSL
                            if self.enable_prometheus:
                                self.ssl_status.labels(domain=domain).set(0)  # 0 = ERROR
                                self.ssl_errors.labels(domain=domain).inc()
                            
                            if self._should_log_result(False):
                                self.logger.error(
                                    f"SSL certificate for {domain} critically expiring in {days_left} days"
                                )
                            self.send_notification(
                                f"SSL certificate critically expiring in {days_left} days",
                                status="error",
                                check_type="SSL",
                                target=domain
                            )
                        elif days_left <= self.ssl_warn_days:
                            # Update Prometheus metrics for warning SSL
                            if self.enable_prometheus:
                                self.ssl_status.labels(domain=domain).set(0)  # 0 = ERROR (warning is still an issue)
                                self.ssl_errors.labels(domain=domain).inc()
                            
                            if self._should_log_result(False):
                                self.logger.warning(
                                    f"SSL certificate for {domain} expiring soon in {days_left} days"
                                )
                            self.send_notification(
                                f"SSL certificate expiring soon in {days_left} days",
                                status="error",
                                check_type="SSL",
                                target=domain
                            )
                        else:
                            # Update Prometheus metrics for valid SSL
                            if self.enable_prometheus:
                                self.ssl_status.labels(domain=domain).set(1)  # 1 = OK
                            
                            if self._should_log_result(True):
                                self.logger.info(
                                    f"SSL certificate for {domain} is valid for {days_left} more days"
                                )
                            self.send_notification(
                                f"SSL certificate valid for {days_left} more days",
                                status="ok",
                                check_type="SSL", 
                                target=domain
                            )
            except Exception as e:
                # Update Prometheus metrics for SSL exception
                if self.enable_prometheus:
                    self.ssl_status.labels(domain=domain).set(0)  # 0 = ERROR
                    self.ssl_errors.labels(domain=domain).inc()
                
                if self._should_log_result(False):
                    self.logger.error(f"SSL certificate check for {domain}: FAIL - {e}")
                self.send_notification(
                    f"SSL certificate check failed: {e}",
                    status="error",
                    check_type="SSL",
                    target=domain
                )

    def output_status_summary(self):
        """Output a summary of current status."""
        self.logger.info("=== PingPanda Status Summary ===")
        self.logger.info(f"Running with interval: {self.interval} seconds")
        
        checks = []
        if self.enable_dns:
            checks.append(f"DNS Resolution (domains: {', '.join(self.domains)})")
        if self.enable_ping:
            checks.append(f"Ping (targets: {', '.join(self.ping_ips)})")
        if self.enable_website_check and self.websites:
            checks.append(f"Website (URLs: {', '.join(self.websites)})")
        if self.enable_ssl_check:
            checks.append(f"SSL Certificates (domains: {', '.join(self.ssl_check_domains)})")
            
        self.logger.info(f"Active checks: {len(checks)}")
        for check in checks:
            self.logger.info(f"  - {check}")
        
        # Show filtering status
        if self.show_only_success:
            self.logger.info("Filtering: Showing only SUCCESSFUL results")
        elif self.show_only_failure:
            self.logger.info("Filtering: Showing only FAILED results")
        elif self.show_only_success and self.show_only_failure:
            self.logger.warning("Filtering: Both success and failure filters enabled - no results will be shown")
        else:
            self.logger.info("Filtering: Showing ALL results")
            
        self.logger.info("===============================")

    def run(self):
        """Run all checks based on configuration."""
        self.output_status_summary()
        
        # Log advanced stats configuration if enabled
        if self.config.get('enable_advanced_stats', False):
            self.logger.info("Advanced statistics tracking: ENABLED")
            summary_interval = int(self.config.get('summary_interval', 0))
            if summary_interval > 0:
                self.logger.info(f"Statistics summary interval: {summary_interval} seconds")
            if self.config.get('enable_stats_logging', False):
                self.logger.info(f"Statistics logging: ENABLED -> {self.config.get('stats_log_file', 'pingpanda_stats.csv')}")
            flapping_threshold = int(self.config.get('flapping_threshold', 0))
            if flapping_threshold > 0:
                self.logger.info(f"Flapping detection threshold: {flapping_threshold} status changes")
        
        # Load existing stats
        self._load_stats()
        
        try:
            while True:
                loop_start = time.time()
                
                # Run checks in parallel using threads
                threads = []
                if self.enable_dns:
                    threads.append(Thread(target=self.check_dns))
                if self.enable_ping:
                    threads.append(Thread(target=self.check_ping))
                if self.enable_website_check and self.websites:
                    threads.append(Thread(target=self.check_website))
                if self.enable_ssl_check:
                    threads.append(Thread(target=self.check_ssl_expiry))

                # Start all threads
                for thread in threads:
                    thread.start()

                # Wait for all threads to complete
                for thread in threads:
                    thread.join()

                # Check if it's time for a summary (first run or interval passed)
                current_time = datetime.now()
                summary_interval = int(self.config.get('summary_interval', 0))
                
                if (self.config.get('enable_advanced_stats', False) and 
                    summary_interval > 0 and 
                    (self.last_summary_time is None or 
                     (current_time - self.last_summary_time).total_seconds() >= summary_interval)):
                    self._output_stats_summary()

                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            self.logger.info("Shutting down gracefully...")
            self._cleanup()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="PingPanda - Network Monitoring Tool")
    parser.add_argument("-c", "--config", help="Path to config file")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--show-only-success", action="store_true", help="Show only successful check results")
    parser.add_argument("--show-only-failure", action="store_true", help="Show only failed check results")
    parser.add_argument("--version", action="version", version="PingPanda v1.1.0")
    return parser.parse_args()


def main():
    """Main entry point for PingPanda."""
    args = parse_args()
    
    # Load environment variables
    config = {k: v for k, v in os.environ.items()}
    
    # Override with command line arguments
    if args.verbose:
        config["VERBOSE"] = "true"
    if args.show_only_success:
        config["SHOW_ONLY_SUCCESS"] = "true"
    if args.show_only_failure:
        config["SHOW_ONLY_FAILURE"] = "true"
        
    # Initialize and run PingPanda
    monitor = PingPanda(config)
    monitor.run()


if __name__ == "__main__":
    main()