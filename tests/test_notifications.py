import logging
import pytest
from pathlib import Path

from pingpanda_core.notifications import NotificationManager, NotificationSettings
from pingpanda_core.persistence import PersistenceManager, StatsPersistenceSettings


@pytest.mark.asyncio
async def test_notification_threshold_and_recovery(monkeypatch, tmp_path):
    persistence = PersistenceManager(
        logging.getLogger("pingpanda.tests.notifications"),
        base_dir=str(tmp_path),
        stats_settings=StatsPersistenceSettings(False, str(tmp_path / "unused.json")),
    )
    settings = NotificationSettings(
        alert_threshold=2,
        notify_recovery=True,
        retry_attempts=1,
        retry_backoff=0,
        slack_webhook_url="https://hooks.slack.test/example",
    )
    manager = NotificationManager(logging.getLogger("pingpanda.tests.notifications"), persistence, settings)

    sent_statuses = []

    async def fake_slack(title, message, status, session=None):
        sent_statuses.append(status)
        return True

    monkeypatch.setattr(manager, "_send_slack", fake_slack)

    status_key = "DNS_example.com"
    status_path = Path(persistence.status_file_path(status_key))

    await manager.notify("down", "error", "DNS", "example.com")
    assert not sent_statuses
    assert status_path.read_text(encoding="utf-8") == "1"

    await manager.notify("still down", "error", "DNS", "example.com")
    assert sent_statuses == ["error"]
    assert status_path.read_text(encoding="utf-8") == "2"

    await manager.notify("recovered", "ok", "DNS", "example.com")
    assert sent_statuses[-1] == "ok"
    assert not status_path.exists()
