import logging
from pathlib import Path

from pingpanda_core.persistence import PersistenceManager, StatsPersistenceSettings


class DummyLogger(logging.Logger):
    def __init__(self):
        super().__init__("pingpanda.tests.persistence")


def test_stats_round_trip(tmp_path):
    stats_path = tmp_path / "stats.pkl"
    manager = PersistenceManager(
        DummyLogger(),
        base_dir=str(tmp_path),
        stats_settings=StatsPersistenceSettings(True, str(stats_path)),
    )

    payload = {"ip_stats": {"1.1.1.1": {"ip": "1.1.1.1"}}, "saved_at": "now"}
    manager.save_stats(payload)

    assert stats_path.exists()
    loaded = manager.load_stats()
    assert loaded == payload


def test_status_file_helpers(tmp_path):
    manager = PersistenceManager(
        DummyLogger(),
        base_dir=str(tmp_path),
        stats_settings=StatsPersistenceSettings(False, str(tmp_path / "unused.pkl")),
    )

    manager.write_status_count("DNS_example.com", 3)
    status_file = manager.status_file_path("DNS_example.com")
    assert Path(status_file).read_text(encoding="utf-8") == "3"

    manager.clear_status("DNS_example.com")
    assert not Path(status_file).exists()
