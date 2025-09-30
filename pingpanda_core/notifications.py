"""Notification handling for PingPanda."""

from __future__ import annotations

import logging
import os
import socket
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

import requests


@dataclass
class NotificationSettings:
    alert_threshold: int
    notify_recovery: bool
    retry_attempts: int
    retry_backoff: float
    slack_webhook_url: Optional[str] = None
    teams_webhook_url: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    slack_channel: Optional[str] = None
    slack_username: Optional[str] = "PingPanda"
    slack_icon_emoji: Optional[str] = None
    discord_username: Optional[str] = "PingPanda"
    discord_avatar_url: Optional[str] = None


class NotificationManager:
    """Manage notification throttling and webhook delivery."""

    def __init__(self, logger: logging.Logger, status_dir: str, settings: NotificationSettings):
        self.logger = logger
        self.settings = settings
        self.status_dir = status_dir
        os.makedirs(self.status_dir, exist_ok=True)
        self._failure_counts: Dict[str, int] = {}

    def notify(self, message: str, status: str, check_type: str, target: str) -> None:
        if not self._should_notify(check_type, target, status):
            return

        hostname = socket.gethostname()
        formatted_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emoji = "✅" if status == "ok" else "🔴"

        title = f"PingPanda: {emoji} {check_type} check for {target}"
        formatted_message = (
            f"*Host:* {hostname}\n"
            f"*Time:* {formatted_time}\n"
            f"*Status:* {status}\n"
            f"*Message:* {message}"
        )

        sent = False

        if self.settings.slack_webhook_url:
            sent |= self._send_slack(title, formatted_message, status)

        if self.settings.teams_webhook_url:
            sent |= self._send_teams(title, formatted_message, status)

        if self.settings.discord_webhook_url:
            sent |= self._send_discord(title, formatted_message, status)

        if not sent:
            self.logger.debug("Notification suppressed; no webhook endpoints configured")

    def _status_key(self, check_type: str, target: str) -> str:
        return f"{check_type}_{target}"

    def _status_file(self, status_key: str) -> str:
        return os.path.join(self.status_dir, status_key.replace("/", "_"))

    def _should_notify(self, check_type: str, target: str, status: str) -> bool:
        status_key = self._status_key(check_type, target)
        status_file = self._status_file(status_key)

        if status == "error":
            failure_count = self._failure_counts.get(status_key, 0) + 1
            self._failure_counts[status_key] = failure_count
            with open(status_file, "w", encoding="utf-8") as handle:
                handle.write(str(failure_count))
            return failure_count >= self.settings.alert_threshold

        if status == "ok":
            should_notify = (
                self.settings.notify_recovery
                and self._failure_counts.get(status_key, 0) >= self.settings.alert_threshold
            )
            self._failure_counts[status_key] = 0
            if os.path.exists(status_file):
                try:
                    os.remove(status_file)
                except OSError:
                    pass
            return should_notify

        return False

    def _send_slack(self, title: str, message: str, status: str) -> bool:
        color = "good" if status == "ok" else "danger"
        payload: Dict[str, Any] = {
            "text": title,
            "attachments": [
                {
                    "color": color,
                    "text": message,
                    "footer": "PingPanda",
                    "ts": int(datetime.now().timestamp()),
                }
            ],
        }

        if self.settings.slack_channel:
            payload["channel"] = self.settings.slack_channel
        if self.settings.slack_username:
            payload["username"] = self.settings.slack_username
        if self.settings.slack_icon_emoji:
            payload["icon_emoji"] = self.settings.slack_icon_emoji

        return self._post_with_retries(
            self.settings.slack_webhook_url,
            payload,
            "Slack",
        )

    def _send_teams(self, title: str, message: str, status: str) -> bool:
        color = "00FF00" if status == "ok" else "FF0000"
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": title,
            "title": title,
            "text": message.replace("*", ""),
        }

        return self._post_with_retries(
            self.settings.teams_webhook_url,
            payload,
            "Microsoft Teams",
        )

    def _send_discord(self, title: str, message: str, status: str) -> bool:
        color = 65280 if status == "ok" else 16711680
        payload: Dict[str, Any] = {
            "embeds": [
                {
                    "title": title,
                    "description": message.replace("*", ""),
                    "color": color,
                }
            ]
        }

        if self.settings.discord_username:
            payload["username"] = self.settings.discord_username
        if self.settings.discord_avatar_url:
            payload["avatar_url"] = self.settings.discord_avatar_url

        return self._post_with_retries(
            self.settings.discord_webhook_url,
            payload,
            "Discord",
        )

    def _post_with_retries(
        self,
        url: Optional[str],
        payload: Dict[str, Any],
        service: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        if not url:
            return False

        for attempt in range(1, self.settings.retry_attempts + 1):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=5)
                if response.status_code < 400:
                    return True

                self.logger.warning(
                    "%s webhook returned status %s: %s",
                    service,
                    response.status_code,
                    response.text[:500],
                )
            except requests.RequestException as exc:
                self.logger.warning(
                    "%s notification attempt %s/%s failed: %s",
                    service,
                    attempt,
                    self.settings.retry_attempts,
                    exc,
                )

            if attempt < self.settings.retry_attempts and self.settings.retry_backoff > 0:
                time.sleep(self.settings.retry_backoff * attempt)

        self.logger.error(
            "Failed to send %s notification after %s attempts",
            service,
            self.settings.retry_attempts,
        )
        return False