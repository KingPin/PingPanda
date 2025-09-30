import sys

import pingpanda


def test_main_invokes_monitor_with_config(monkeypatch, tmp_path):
    config_file = tmp_path / "config.conf"
    config_file.write_text("FOO=bar\n# Comment line\nBAZ=buzz\n", encoding="utf-8")

    captured = {}

    class DummyMonitor:
        def __init__(self, config):
            captured["config"] = config

        def run(self):
            captured["ran"] = True

    monkeypatch.setenv("EXISTING", "value")
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
    assert config["FOO"] == "bar"
    assert config["BAZ"] == "buzz"
    assert config["SHOW_ONLY_SUCCESS"] == "true"
    assert captured.get("ran") is True
    assert config["EXISTING"] == "value"