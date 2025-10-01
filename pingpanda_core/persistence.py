"""Persistence utilities for PingPanda."""

from __future__ import annotations

import logging
import os
import pickle
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class StatsPersistenceSettings:
    """Configuration for statistics persistence."""

    enabled: bool
    file_path: str


class PersistenceManager:
    """Encapsulate filesystem persistence for stats and status markers."""

    def __init__(
        self,
        logger: logging.Logger,
        base_dir: str,
        stats_settings: StatsPersistenceSettings,
        status_dir: Optional[str] = None,
        status_subdir: str = "status",
    ):
        self.logger = logger
        self.stats_settings = stats_settings
        self.base_dir = base_dir
        resolved_status_dir = status_dir or os.path.join(base_dir, status_subdir)
        self.status_dir = resolved_status_dir
        os.makedirs(self.status_dir, exist_ok=True)

    # ---- Status helpers -------------------------------------------------
    def status_file_path(self, status_key: str) -> str:
        return os.path.join(self.status_dir, status_key.replace("/", "_"))

    def write_status_count(self, status_key: str, count: int) -> None:
        try:
            with open(self.status_file_path(status_key), "w", encoding="utf-8") as handle:
                handle.write(str(count))
        except OSError as exc:
            self.logger.warning("Failed to write status file for %s: %s", status_key, exc)

    def clear_status(self, status_key: str) -> None:
        path = self.status_file_path(status_key)
        if not os.path.exists(path):
            return
        try:
            os.remove(path)
        except OSError as exc:
            self.logger.warning("Failed to remove status file for %s: %s", status_key, exc)

    # ---- Stats persistence ----------------------------------------------
    def load_stats(self) -> Optional[Dict[str, Any]]:
        if not self.stats_settings.enabled:
            return None

        path = self.stats_settings.file_path
        if not path or not os.path.exists(path):
            return None

        try:
            with open(path, "rb") as handle:
                return pickle.load(handle)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error("Failed to load stats from %s: %s", path, exc)
            return None

    def save_stats(self, payload: Dict[str, Any]) -> None:
        if not self.stats_settings.enabled:
            return

        path = self.stats_settings.file_path
        if not path:
            return

        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        try:
            with open(path, "wb") as handle:
                pickle.dump(payload, handle)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error("Failed to save stats to %s: %s", path, exc)
