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
from typing import Any, Dict, Optional

from .persistence import PersistenceManager


class TargetStats:
    """Track uptime/downtime statistics for a single monitored target.

    The *key* is a composite "{check_type}:{target}" string (e.g.
    "DNS:google.com", "Ping:1.1.1.1").  The legacy *ip* attribute is
    kept as an alias for backward compatibility.
    """

    def __init__(self, key: str):
        self.key = key
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

    @property
    def ip(self) -> str:
        """Legacy alias — returns the raw target portion of the key."""
        return self.key.split(":", 1)[-1] if ":" in self.key else self.key

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
                # Keep only the 100 most recent outage periods to bound memory.
                self.downtime_periods = self.downtime_periods[-100:]

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
            "key": self.key,
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
    def from_dict(cls, data: Dict[str, Any]) -> "TargetStats":
        # Support both "key" (new) and "ip" (old) field names.
        key = data.get("key") or data.get("ip", "unknown")
        stats = cls(key)
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


# Backward-compatibility alias
IPStats = TargetStats


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
        "target_key",
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

    def log_stats(self, ip_stats: Dict[str, TargetStats], overall_stats: Dict[str, Any]) -> None:
        timestamp = datetime.now().isoformat()

        try:
            if self.format_type == "csv":
                self._log_csv(timestamp, ip_stats, overall_stats)
            else:
                self._log_json(timestamp, ip_stats, overall_stats)
        except Exception as exc:
            self._error_logger.error(f"Failed to log statistics: {exc}")

    def _log_csv(self, timestamp: str, ip_stats: Dict[str, TargetStats], overall_stats: Dict[str, Any]) -> None:
        buffer = io.StringIO()
        writer = csv.writer(buffer)

        for stats in ip_stats.values():
            writer.writerow([
                timestamp,
                stats.key,
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

    def _log_json(self, timestamp: str, ip_stats: Dict[str, TargetStats], overall_stats: Dict[str, Any]) -> None:
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
    """Tracks per-target statistics for all check types.

    Stats are keyed by "{CheckType}:{target}" (e.g. "DNS:google.com",
    "Ping:1.1.1.1", "Website:https://example.com", "SSL:example.com").

    All methods are called from the asyncio event loop and require no
    threading synchronisation.
    """

    logger: logging.Logger
    settings: StatsSettings
    persistence: Optional[PersistenceManager] = None
    target_stats: Dict[str, TargetStats] = field(default_factory=dict)
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

    @property
    def ip_stats(self) -> Dict[str, TargetStats]:
        """Backward-compat alias for target_stats."""
        return self.target_stats

    def update_target(self, key: str, success: bool) -> StatsUpdateResult:
        """Record a check result for the given target key."""
        if key not in self.target_stats:
            self.target_stats[key] = TargetStats(key)

        stats = self.target_stats[key]
        new_status = "up" if success else "down"
        status_changed = stats.update_status(new_status)

        flapping_changed = False
        if status_changed and self.settings.flap_threshold > 0:
            was_flapping = stats.is_flapping
            stats.check_flapping(self.settings.flap_threshold, self.settings.flap_window_seconds)
            flapping_changed = stats.is_flapping != was_flapping
            if stats.is_flapping and not was_flapping:
                self.logger.warning("Flapping detected for %s", key)
            elif not stats.is_flapping and was_flapping:
                self.logger.info("Flapping resolved for %s", key)

        return StatsUpdateResult(
            status_changed=status_changed,
            current_status=stats.current_status,
            is_flapping=stats.is_flapping,
            flapping_changed=flapping_changed,
        )

    def update_ip(self, ip: str, success: bool) -> StatsUpdateResult:
        """Backward-compat alias — wraps update_target with 'Ping:' prefix."""
        return self.update_target(f"Ping:{ip}", success)

    @staticmethod
    def _calculate_availability(total_uptime: float, total_downtime: float) -> float:
        total = total_uptime + total_downtime
        if total <= 0:
            return 100.0
        return (total_uptime / total) * 100

    def get_overall_stats(self) -> Dict[str, Any]:
        total_uptime = sum(s.total_uptime for s in self.target_stats.values())
        total_downtime = sum(s.total_downtime for s in self.target_stats.values())
        total_downtime_events = sum(s.downtime_events for s in self.target_stats.values())
        total_flapping = sum(1 for s in self.target_stats.values() if s.is_flapping)
        total_targets = len(self.target_stats)
        targets_up = sum(1 for s in self.target_stats.values() if s.current_status == "up")
        targets_down = sum(1 for s in self.target_stats.values() if s.current_status == "down")

        availability = self._calculate_availability(total_uptime, total_downtime)

        return {
            "total_uptime": total_uptime,
            "total_downtime": total_downtime,
            "total_downtime_events": total_downtime_events,
            "total_flapping_ips": total_flapping,
            "total_ips": total_targets,
            "ips_up": targets_up,
            "ips_down": targets_down,
            "overall_availability": availability,
        }

    def output_summary(self) -> None:
        self.logger.info("=== PingPanda Target Statistics Summary ===")
        overall_stats = self.get_overall_stats()
        self.logger.info(
            "Overall: %s/%s targets UP",
            overall_stats['ips_up'], overall_stats['total_ips'],
        )
        self.logger.info("Overall Availability: %.2f%%", overall_stats['overall_availability'])
        self.logger.info("Total Uptime: %.1fs", overall_stats['total_uptime'])
        self.logger.info("Total Downtime: %.1fs", overall_stats['total_downtime'])
        self.logger.info("Total Downtime Events: %s", overall_stats['total_downtime_events'])
        if overall_stats['total_flapping_ips'] > 0:
            self.logger.warning("Flapping targets: %s", overall_stats['total_flapping_ips'])

        self.logger.info("")

        # Group by check type for readability
        by_type: Dict[str, list] = {}
        for key, stats in sorted(self.target_stats.items()):
            check_type = key.split(":", 1)[0] if ":" in key else "Unknown"
            by_type.setdefault(check_type, []).append((key, stats))

        for check_type, entries in sorted(by_type.items()):
            self.logger.info("%s checks:", check_type)
            for key, stats in entries:
                target_label = key.split(":", 1)[-1] if ":" in key else key
                status_str = "[UP]" if stats.current_status == "up" else "[DOWN]"
                flap_indicator = " [FLAP]" if stats.is_flapping else ""
                availability = self._calculate_availability(stats.total_uptime, stats.total_downtime)
                current_duration = stats.get_current_status_duration()

                self.logger.info(
                    "  %s %s - %s%s",
                    status_str, target_label, stats.current_status.upper(), flap_indicator,
                )
                self.logger.info(
                    "    Availability: %.2f%% | In current state: %.1fs",
                    availability, current_duration,
                )
                self.logger.info(
                    "    Uptime: %.1fs | Downtime: %.1fs | Events: %s | Last change: %s",
                    stats.total_uptime, stats.total_downtime,
                    stats.downtime_events, stats.last_status_change.strftime('%H:%M:%S'),
                )

                if stats.downtime_periods:
                    recent_outages = stats.downtime_periods[-3:]
                    self.logger.info(
                        "    Recent outages: %s (showing last 3)", len(recent_outages)
                    )
                    for i, period in enumerate(recent_outages):
                        start = period["start"].strftime('%H:%M:%S')
                        end = period["end"].strftime('%H:%M:%S') if "end" in period else "ongoing"
                        duration = (
                            (period["end"] - period["start"]).total_seconds()
                            if "end" in period
                            else current_duration
                        )
                        self.logger.info(
                            "      %s. %s - %s (%.1fs)", i + 1, start, end, duration
                        )

        self.logger.info("==========================================")

        if self.stats_logger:
            self.stats_logger.log_stats(dict(self.target_stats), overall_stats)

        self.last_summary_time = datetime.now()

    def load(self) -> None:
        if not (self.settings.enable and self.settings.persist and self.persistence):
            return

        stored = self.persistence.load_stats()
        if not stored:
            return

        # Support both "target_stats" (new) and "ip_stats" (old) keys.
        raw = stored.get("target_stats") or stored.get("ip_stats") or {}
        self.target_stats = {
            k: TargetStats.from_dict(v) for k, v in raw.items()
        }

        self.logger.info(
            "Loaded statistics for %s targets from %s",
            len(self.target_stats),
            self.persistence.stats_settings.file_path,
        )

    def save(self) -> None:
        if not (self.settings.enable and self.settings.persist and self.persistence):
            return

        payload = {
            "target_stats": {k: s.to_dict() for k, s in self.target_stats.items()},
            "saved_at": datetime.now(),
        }

        self.persistence.save_stats(payload)
