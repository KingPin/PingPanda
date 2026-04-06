import logging

from pingpanda_core.stats import StatsManager, StatsSettings


def _make_settings(tmp_path) -> StatsSettings:
    return StatsSettings(
        enable=True,
        summary_interval=0,
        log_enabled=False,
        log_file=str(tmp_path / "stats.log"),
        log_format="csv",
        log_max_size=1024,
        log_backup_count=1,
        persist=False,
        flap_threshold=2,
        flap_window_seconds=300,
    )


def test_update_ip_detects_flapping(tmp_path):
    manager = StatsManager(logging.getLogger("pingpanda.tests.stats"), _make_settings(tmp_path))

    first = manager.update_ip("1.1.1.1", True)
    assert first.status_changed is True
    assert first.current_status == "up"
    assert first.is_flapping is False
    assert first.flapping_changed is False

    second = manager.update_ip("1.1.1.1", False)
    assert second.status_changed is True
    assert second.current_status == "down"
    assert second.is_flapping is True
    assert second.flapping_changed is True

    third = manager.update_ip("1.1.1.1", True)
    assert third.status_changed is True
    assert third.current_status == "up"
    assert third.is_flapping is True
    assert third.flapping_changed is False  # Still flapping, no change


def test_output_summary_logs_stats(tmp_path, caplog):
    logger_name = "pingpanda.tests.stats.summary"
    manager = StatsManager(logging.getLogger(logger_name), _make_settings(tmp_path))
    manager.update_ip("1.1.1.1", True)
    manager.update_ip("1.1.1.1", False)

    with caplog.at_level(logging.INFO, logger=logger_name):
        manager.output_summary()

    assert "PingPanda Target Statistics Summary" in caplog.text
    assert "1/1 targets UP" in caplog.text or "0/1 targets UP" in caplog.text
