from pathlib import Path

from endless_loader.config import load_settings


def test_load_settings_resolves_relative_paths(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
library_root = "patches"
pedal_mount_path = "pedal"
state_path = "runtime/state.json"

[web]
host = "127.0.0.1"
port = 9090

[lcd]
enabled = true
bus = 1
address = "0x27"

[companion]
fxpatchsdk_path = "fxsdk"
cache_path = "cache/companion.json"
""".strip(),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.library_root == (tmp_path / "patches").resolve()
    assert settings.pedal_mount_path == (tmp_path / "pedal").resolve()
    assert settings.state_path == (tmp_path / "runtime/state.json").resolve()
    assert settings.web.host == "127.0.0.1"
    assert settings.web.port == 9090
    assert settings.lcd.enabled is True
    assert settings.lcd.address == 0x27
    assert settings.companion.fxpatchsdk_path == (tmp_path / "fxsdk").resolve()
    assert settings.companion.cache_path == (tmp_path / "cache/companion.json").resolve()

