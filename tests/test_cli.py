import sys
import asyncio
import pingpanda


def test_main_invokes_monitor_with_config(monkeypatch, tmp_path):
    config_file = tmp_path / "config.conf"
    # Use keys that are in _KNOWN_ENV_KEYS; unknown keys are filtered for security.
    config_file.write_text(
        "PING_IPS=8.8.8.8  # inline comment should be stripped\n"
        "# Comment-only line\n"
        "INTERVAL=30\n",
        encoding="utf-8",
    )

    captured = {}

    class DummyMonitor:
        def __init__(self, config):
            captured["config"] = config

        async def run(self):
            captured["ran"] = True

    monkeypatch.setenv("DOMAINS", "example.com")
    monkeypatch.setattr(pingpanda, "PingPandaApp", DummyMonitor)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pingpanda",
            "-c",
            str(config_file),
            "--show-only-success",
        ],
    )

    pingpanda.main()

    config = captured["config"]
    assert config["PING_IPS"] == "8.8.8.8"     # inline comment stripped
    assert config["INTERVAL"] == "30"
    assert config["SHOW_ONLY_SUCCESS"] == "true"
    assert captured.get("ran") is True
    assert config["DOMAINS"] == "example.com"
