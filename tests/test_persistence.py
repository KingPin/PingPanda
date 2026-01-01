import logging
from pathlib import Path
from datetime import datetime, timezone

from pingpanda_core.persistence import PersistenceManager, StatsPersistenceSettings


class DummyLogger(logging.Logger):
    def __init__(self):
        super().__init__("pingpanda.tests.persistence")


def test_stats_round_trip(tmp_path):
    stats_path = tmp_path / "stats.json"
    manager = PersistenceManager(
        DummyLogger(),
        base_dir=str(tmp_path),
        stats_settings=StatsPersistenceSettings(True, str(stats_path)),
    )

    payload = {"ip_stats": {"1.1.1.1": {"ip": "1.1.1.1"}}, "saved_at": "2025-01-01T00:00:00"}
    manager.save_stats(payload)

    assert stats_path.exists()
    loaded = manager.load_stats()
    assert loaded == payload


def test_status_file_helpers(tmp_path):
    manager = PersistenceManager(
        DummyLogger(),
        base_dir=str(tmp_path),
        stats_settings=StatsPersistenceSettings(False, str(tmp_path / "unused.json")),
    )

    manager.write_status_count("DNS_example.com", 3)
    status_file = manager.status_file_path("DNS_example.com")
    assert Path(status_file).read_text(encoding="utf-8") == "3"

    manager.clear_status("DNS_example.com")
    assert not Path(status_file).exists()


def test_stats_with_datetime_objects(tmp_path):
    """Test that datetime objects are properly serialized."""
    stats_path = tmp_path / "stats.json"
    manager = PersistenceManager(
        DummyLogger(),
        base_dir=str(tmp_path),
        stats_settings=StatsPersistenceSettings(True, str(stats_path)),
    )
    
    now = datetime.now(timezone.utc)
    payload = {
        "ip_stats": {
            "1.1.1.1": {
                "ip": "1.1.1.1",
                "last_check": now,
                "first_seen": now,
            }
        },
        "saved_at": now,
    }
    
    manager.save_stats(payload)
    assert stats_path.exists()
    
    loaded = manager.load_stats()
    assert loaded is not None
    # Datetime objects are serialized as ISO strings
    assert "ip_stats" in loaded
    assert "1.1.1.1" in loaded["ip_stats"]


def test_load_stats_when_file_missing(tmp_path):
    """Test that load_stats returns None when file doesn't exist."""
    stats_path = tmp_path / "nonexistent.json"
    manager = PersistenceManager(
        DummyLogger(),
        base_dir=str(tmp_path),
        stats_settings=StatsPersistenceSettings(True, str(stats_path)),
    )
    
    loaded = manager.load_stats()
    assert loaded is None


def test_multiple_status_files(tmp_path):
    """Test managing multiple status tracking files."""
    manager = PersistenceManager(
        DummyLogger(),
        base_dir=str(tmp_path),
        stats_settings=StatsPersistenceSettings(False, str(tmp_path / "unused.json")),
    )
    
    # Create multiple status files
    manager.write_status_count("DNS_example.com", 1)
    manager.write_status_count("Ping_1.1.1.1", 2)
    manager.write_status_count("Website_https://example.com", 3)
    
    # Verify all exist with correct values
    assert Path(manager.status_file_path("DNS_example.com")).read_text() == "1"
    assert Path(manager.status_file_path("Ping_1.1.1.1")).read_text() == "2"
    assert Path(manager.status_file_path("Website_https://example.com")).read_text() == "3"
    
    # Clear one and verify others remain
    manager.clear_status("DNS_example.com")
    assert not Path(manager.status_file_path("DNS_example.com")).exists()
    assert Path(manager.status_file_path("Ping_1.1.1.1")).exists()
    assert Path(manager.status_file_path("Website_https://example.com")).exists()
