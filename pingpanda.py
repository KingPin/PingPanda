import argparse
import logging
import os
import socket
import ssl
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Thread
from typing import Dict, List, Optional, Union

import pythonping
import requests
from slack_sdk import WebClient
from prometheus_client import start_http_server, Gauge, Counter, Summary


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
        log_level = getattr(logging, self.config.get("LOG_LEVEL", "INFO").upper())
        log_dir = self.config.get("LOG_DIR", "/logs")
        log_file = os.path.join(log_dir, self.config.get("LOG_FILE", "pingpanda.log"))
        max_log_size = int(self.config.get("MAX_LOG_SIZE", 1048576))  # 1MB default
        log_backup_count = int(self.config.get("LOG_BACKUP_COUNT", 5))
        
        # Create log directory if it doesn't exist
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        self.logger = logging.getLogger("pingpanda")
        self.logger.setLevel(log_level)
        
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        
        if self.config.get("LOG_TO_TERMINAL", "true").lower() == "true":
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        if self.config.get("LOG_TO_FILE", "true").lower() == "true":
            file_handler = RotatingFileHandler(
                log_file, maxBytes=max_log_size, backupCount=log_backup_count
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
    
    def _load_config(self):
        """Load configuration from environment variables with defaults."""
        self.interval = int(self.config.get("INTERVAL", 15))
        self.verbose = self.config.get("VERBOSE", "false").lower() == "true"
        self.retry_count = int(self.config.get("RETRY_COUNT", 3))
        self.success_http_codes = [
            int(code) for code in self.config.get("SUCCESS_HTTP_CODES", "200").split(",")
        ]
        self.alert_threshold = int(self.config.get("ALERT_THRESHOLD", 3))
        self.domains = self.config.get("DOMAINS", "google.com").split(",")
        self.ping_ips = self.config.get("PING_IPS", "1.1.1.1").split(",")
        self.websites = self.config.get("CHECK_WEBSITE", "").split(",") if self.config.get("CHECK_WEBSITE") else []
        self.enable_website_check = self.config.get("ENABLE_WEBSITE_CHECK", "false").lower() == "true"
        self.ssl_check_domains = self.config.get("SSL_CHECK_DOMAINS", "google.com").split(",")
        self.enable_ssl_check = self.config.get("ENABLE_SSL_CHECK", "false").lower() == "true"
        self.enable_ping = self.config.get("ENABLE_PING", "true").lower() == "true"
        self.enable_dns = self.config.get("ENABLE_DNS", "true").lower() == "true"
        self.ssl_warn_days = int(self.config.get("SSL_WARN_DAYS", 30))
        self.ssl_critical_days = int(self.config.get("SSL_CRITICAL_DAYS", 7))
        self.notify_recovery = self.config.get("NOTIFY_RECOVERY", "true").lower() == "true"
        
        # Notification settings
        self.slack_webhook_url = self.config.get("SLACK_WEBHOOK_URL")
        self.teams_webhook_url = self.config.get("TEAMS_WEBHOOK_URL")
        self.discord_webhook_url = self.config.get("DISCORD_WEBHOOK_URL")
        
        # Initialize Slack client if webhook URL is provided
        self.slack_client = WebClient(token=self.slack_webhook_url) if self.slack_webhook_url else None
        
        # Add Prometheus configuration
        self.enable_prometheus = self.config.get("ENABLE_PROMETHEUS", "false").lower() == "true"
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
        self.status_dir = os.path.join(self.config.get("LOG_DIR", "/logs"), "status")
        os.makedirs(self.status_dir, exist_ok=True)
        self.failure_counts = {}
        
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
                        self.logger.info(f"Ping to {ip}: PASS (Time: {response_list.rtt_avg_ms:.2f}ms)")
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
                self.logger.error(f"Ping to {ip}: FAIL")
                self.send_notification(
                    f"Failed to ping host after {self.retry_count} attempts",
                    status="error",
                    check_type="Ping",
                    target=ip
                )

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
                    self.logger.info(
                        f"Website check for {website}: PASS (HTTP Status: {response.status_code}, Time: {duration:.2f}ms)"
                    )
                    self.send_notification(
                        f"Website check successful (HTTP {response.status_code}, {duration:.2f}ms)",
                        status="ok",
                        check_type="Website",
                        target=website
                    )
                else:
                    self.logger.error(
                        f"Website check for {website}: FAIL (HTTP Status: {response.status_code}, Time: {duration:.2f}ms)"
                    )
                    self.send_notification(
                        f"Website check failed with HTTP status {response.status_code} ({duration:.2f}ms)",
                        status="error",
                        check_type="Website",
                        target=website
                    )
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Website check for {website}: FAIL - {e}")
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
        self.logger.info("===============================")

    def run(self):
        """Run all checks based on configuration."""
        self.output_status_summary()
        
        try:
            while True:
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

                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            self.logger.info("Shutting down gracefully...")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="PingPanda - Network Monitoring Tool")
    parser.add_argument("-c", "--config", help="Path to config file")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
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
        
    # Initialize and run PingPanda
    monitor = PingPanda(config)
    monitor.run()


if __name__ == "__main__":
    main()