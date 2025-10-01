"""Statistics tracking and logging utilities for PingPanda."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from threading import Lock
from typing import Any, Dict, Optional

from .persistence import PersistenceManager


class IPStats:
    """Track statistics for a single IP address."""

    def __init__(self, ip: str):
        self.ip = ip
        self.current_status = "unknown"  # "up", "down", "unknown"
        self.total_uptime = 0.0  # seconds
        self.total_downtime = 0.0  # seconds
        self.downtime_events = 0
        self.last_status_change = datetime.now()
        self.downtime_periods: list[dict[str, datetime]] = []  # [{"start": datetime, "end": datetime}]
        self.status_change_times = []
        self.is_flapping = False
        self.last_check_time = datetime.now()
        self._status_start_time = datetime.now()

    def update_status(self, new_status: str, timestamp: Optional[datetime] = None) -> bool:
        """Update the status and calculate uptime/downtime."""
        if timestamp is None:
            timestamp = datetime.now()

        time_delta = (timestamp - self.last_check_time).total_seconds()

        if self.current_status == "up":
            self.total_uptime += time_delta
        elif self.current_status == "down":
            self.total_downtime += time_delta

        self.last_check_time = timestamp

        status_changed = self.current_status != new_status

        if status_changed:
            if self.current_status == "down" and new_status == "up":
                if self.downtime_periods and "end" not in self.downtime_periods[-1]:
                    self.downtime_periods[-1]["end"] = timestamp
            elif self.current_status == "up" and new_status == "down":
                self.downtime_events += 1
                self.downtime_periods.append({"start": timestamp})

            self.last_status_change = timestamp
            self.status_change_times.append(timestamp)
            self.status_change_times = self.status_change_times[-20:]
            self.current_status = new_status
            self._status_start_time = timestamp

        return status_changed

    def check_flapping(self, threshold: int, window_seconds: int) -> bool:
        """Check if the IP is flapping (too many status changes in time window)."""
        if threshold <= 0 or len(self.status_change_times) < threshold:
            self.is_flapping = False
            return False

        now = datetime.now()
        window_start = now - timedelta(seconds=window_seconds)
        recent_changes = [t for t in self.status_change_times if t >= window_start]
        self.is_flapping = len(recent_changes) >= threshold
        return self.is_flapping

    def get_current_status_duration(self) -> float:
        return (datetime.now() - self._status_start_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
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
                    "end": period["end"].isoformat() if "end" in period else None,
                }
                for period in self.downtime_periods
            ],
            "is_flapping": self.is_flapping,
            "current_status_duration": self.get_current_status_duration(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IPStats":
        stats = cls(data["ip"])
        stats.current_status = data["current_status"]
        stats.total_uptime = data["total_uptime"]
        stats.total_downtime = data["total_downtime"]
        stats.downtime_events = data["downtime_events"]
        stats.last_status_change = datetime.fromisoformat(data["last_status_change"])
        stats.is_flapping = data.get("is_flapping", False)

        stats.downtime_periods = []
        for period in data.get("downtime_periods", []):
            converted = {"start": datetime.fromisoformat(period["start"])}
            if period.get("end"):
                converted["end"] = datetime.fromisoformat(period["end"])
            stats.downtime_periods.append(converted)

        return stats


class _StatsRotatingFileHandler(RotatingFileHandler):
    """Rotating handler that writes a header row when a new file is created."""

    def __init__(self, filename: str, maxBytes: int, backupCount: int, header_line: Optional[str] = None):
        self.header_line = header_line
        super().__init__(filename, maxBytes=maxBytes, backupCount=backupCount)
        self._ensure_header()

    def _ensure_header(self) -> None:
        if not self.header_line:
            return
        try:
            if not os.path.exists(self.baseFilename) or os.path.getsize(self.baseFilename) == 0:
                if self.stream is None:
                    self.stream = self._open()
                self.stream.write(self.header_line + os.linesep)
                self.stream.flush()
        except OSError:
            pass

    def doRollover(self) -> None:
        super().doRollover()
        self._ensure_header()


class StatsLogger:
    """Handle logging of statistics in CSV or JSON format."""

    _CSV_HEADER = [
        "timestamp",
        "ip",
        "current_status",
        "total_uptime",
        "total_downtime",
        "downtime_events",
        "last_status_change",
        "current_status_duration",
        "is_flapping",
    ]

    def __init__(self, log_file: str, format_type: str = "csv", max_size: int = 1048576, backup_count: int = 5):
        self.log_file = log_file
        self.format_type = format_type.lower()

        directory = os.path.dirname(log_file)
        if directory:
            os.makedirs(directory, exist_ok=True)

        header_line: Optional[str] = None
        if self.format_type == "csv":
            buffer = io.StringIO()
            csv.writer(buffer).writerow(self._CSV_HEADER)
            header_line = buffer.getvalue().strip("\r\n")

        self.handler = _StatsRotatingFileHandler(
            log_file,
            maxBytes=max_size,
            backupCount=backup_count,
            header_line=header_line,
        )
        self.handler.setLevel(logging.INFO)
        self.handler.setFormatter(logging.Formatter("%(message)s"))

        logger_name = f"pingpanda.stats.{id(self)}"
        self._logger = logging.getLogger(logger_name)
        self._logger.handlers = []
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._logger.addHandler(self.handler)

        self._error_logger = logging.getLogger("pingpanda")

    def log_stats(self, ip_stats: Dict[str, IPStats], overall_stats: Dict[str, Any]) -> None:
        timestamp = datetime.now().isoformat()

        try:
            if self.format_type == "csv":
                self._log_csv(timestamp, ip_stats, overall_stats)
            else:
                self._log_json(timestamp, ip_stats, overall_stats)
        except Exception as exc:
            self._error_logger.error(f"Failed to log statistics: {exc}")

    def _log_csv(self, timestamp: str, ip_stats: Dict[str, IPStats], overall_stats: Dict[str, Any]) -> None:
        buffer = io.StringIO()
        writer = csv.writer(buffer)

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
                stats.is_flapping,
            ])

        writer.writerow([
            timestamp,
            "OVERALL",
            "summary",
            f"{overall_stats['total_uptime']:.2f}",
            f"{overall_stats['total_downtime']:.2f}",
            overall_stats['total_downtime_events'],
            "",
            "",
            overall_stats['total_flapping_ips'],
        ])

        data = buffer.getvalue().strip()
        if not data:
            return

        for line in data.splitlines():
            self._logger.info(line)

    def _log_json(self, timestamp: str, ip_stats: Dict[str, IPStats], overall_stats: Dict[str, Any]) -> None:
        log_entry = {
            "timestamp": timestamp,
            "ip_stats": {ip: stats.to_dict() for ip, stats in ip_stats.items()},
            "overall_stats": overall_stats,
        }

        self._logger.info(json.dumps(log_entry, sort_keys=True))


@dataclass
class StatsSettings:
    enable: bool
    summary_interval: int
    log_enabled: bool
    log_file: str
    log_format: str
    log_max_size: int
    log_backup_count: int
    persist: bool
    flap_threshold: int
    flap_window_seconds: int


@dataclass
class StatsUpdateResult:
    status_changed: bool
    current_status: str
    is_flapping: bool
    flapping_changed: bool


@dataclass
class StatsManager:
    logger: logging.Logger
    settings: StatsSettings
    persistence: Optional[PersistenceManager] = None
    ip_stats: Dict[str, IPStats] = field(default_factory=dict)
    stats_lock: Lock = field(default_factory=Lock)
    last_summary_time: Optional[datetime] = None
    stats_logger: Optional[StatsLogger] = None

    def __post_init__(self) -> None:
        if self.settings.log_enabled:
            self.stats_logger = StatsLogger(
                self.settings.log_file,
                self.settings.log_format,
                self.settings.log_max_size,
                self.settings.log_backup_count,
            )
        self.last_summary_time = datetime.now()

    def update_ip(self, ip: str, success: bool) -> StatsUpdateResult:
        with self.stats_lock:
            if ip not in self.ip_stats:
                self.ip_stats[ip] = IPStats(ip)

            stats = self.ip_stats[ip]
            new_status = "up" if success else "down"
            status_changed = stats.update_status(new_status)

            flapping_changed = False
            if status_changed and self.settings.flap_threshold > 0:
                was_flapping = stats.is_flapping
                stats.check_flapping(self.settings.flap_threshold, self.settings.flap_window_seconds)
                flapping_changed = stats.is_flapping != was_flapping
                if stats.is_flapping and not was_flapping:
                    self.logger.warning(f"Flapping detected for IP {ip}")
                elif not stats.is_flapping and was_flapping:
                    self.logger.info(f"Flapping resolved for IP {ip}")

            return StatsUpdateResult(
                status_changed=status_changed,
                current_status=stats.current_status,
                is_flapping=stats.is_flapping,
                flapping_changed=flapping_changed,
            )

    @staticmethod
    def _calculate_availability(total_uptime: float, total_downtime: float) -> float:
        total = total_uptime + total_downtime
        if total <= 0:
            return 100.0
        return (total_uptime / total) * 100

    def get_overall_stats(self) -> Dict[str, Any]:
        with self.stats_lock:
            total_uptime = sum(stats.total_uptime for stats in self.ip_stats.values())
            total_downtime = sum(stats.total_downtime for stats in self.ip_stats.values())
            total_downtime_events = sum(stats.downtime_events for stats in self.ip_stats.values())
            total_flapping_ips = sum(1 for stats in self.ip_stats.values() if stats.is_flapping)
            total_ips = len(self.ip_stats)
            ips_up = sum(1 for stats in self.ip_stats.values() if stats.current_status == "up")
            ips_down = sum(1 for stats in self.ip_stats.values() if stats.current_status == "down")

            availability = self._calculate_availability(total_uptime, total_downtime)

            return {
                "total_uptime": total_uptime,
                "total_downtime": total_downtime,
                "total_downtime_events": total_downtime_events,
                "total_flapping_ips": total_flapping_ips,
                "total_ips": total_ips,
                "ips_up": ips_up,
                "ips_down": ips_down,
                "overall_availability": availability,
            }

    def output_summary(self) -> None:
        self.logger.info("=== PingPanda IP Statistics Summary ===")
        overall_stats = self.get_overall_stats()
        self.logger.info(f"Overall Status: {overall_stats['ips_up']}/{overall_stats['total_ips']} IPs UP")
        self.logger.info(f"Overall Availability: {overall_stats['overall_availability']:.2f}%")
        self.logger.info(f"Total Uptime: {overall_stats['total_uptime']:.1f}s")
        self.logger.info(f"Total Downtime: {overall_stats['total_downtime']:.1f}s")
        self.logger.info(f"Total Downtime Events: {overall_stats['total_downtime_events']}")
        if overall_stats['total_flapping_ips'] > 0:
            self.logger.warning(f"Flapping IPs: {overall_stats['total_flapping_ips']}")

        self.logger.info("")
        self.logger.info("Per-IP Statistics:")

        with self.stats_lock:
            ip_stats_snapshot = dict(self.ip_stats.items())

        for ip, stats in sorted(ip_stats_snapshot.items()):
            status_emoji = "🟢" if stats.current_status == "up" else "🔴"
            flap_indicator = " 🔄" if stats.is_flapping else ""
            availability = self._calculate_availability(stats.total_uptime, stats.total_downtime)
            current_duration = stats.get_current_status_duration()

            self.logger.info(f"  {status_emoji} {ip} - {stats.current_status.upper()}{flap_indicator}")
            self.logger.info(
                f"    Availability: {availability:.2f}% | Current Status: {current_duration:.1f}s"
            )
            self.logger.info(
                f"    Uptime: {stats.total_uptime:.1f}s | Downtime: {stats.total_downtime:.1f}s"
            )
            self.logger.info(
                f"    Downtime Events: {stats.downtime_events} | Last Change: {stats.last_status_change.strftime('%H:%M:%S')}"
            )

            if stats.downtime_periods:
                recent_outages = stats.downtime_periods[-3:]
                self.logger.info(f"    Recent Outages: {len(recent_outages)} (showing last 3)")
                for i, period in enumerate(recent_outages):
                    start = period["start"].strftime('%H:%M:%S')
                    end = period["end"].strftime('%H:%M:%S') if "end" in period else "ongoing"
                    duration = (
                        (period["end"] - period["start"]).total_seconds()
                        if "end" in period
                        else current_duration
                    )
                    self.logger.info(f"      {i + 1}. {start} - {end} ({duration:.1f}s)")

        self.logger.info("==========================================")

        if self.stats_logger:
            with self.stats_lock:
                ip_stats_snapshot_for_log = dict(self.ip_stats.items())
            self.stats_logger.log_stats(ip_stats_snapshot_for_log, overall_stats)

        self.last_summary_time = datetime.now()

    def load(self) -> None:
        if not (self.settings.enable and self.settings.persist and self.persistence):
            return

        stored = self.persistence.load_stats()
        if not stored:
            return

        with self.stats_lock:
            self.ip_stats = {
                ip: IPStats.from_dict(stats_data)
                for ip, stats_data in stored.get("ip_stats", {}).items()
            }

        self.logger.info(
            "Loaded statistics for %s IPs from %s",
            len(self.ip_stats),
            self.persistence.stats_settings.file_path,
        )

    def save(self) -> None:
        if not (self.settings.enable and self.settings.persist and self.persistence):
            return

        with self.stats_lock:
            payload = {
                "ip_stats": {ip: stats.to_dict() for ip, stats in self.ip_stats.items()},
                "saved_at": datetime.now(),
            }

        self.persistence.save_stats(payload)
