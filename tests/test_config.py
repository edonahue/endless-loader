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

[usb]
mode = "helper"
expected_label = "ENDLESS"
expected_uuid = "1234-ABCD"
auto_eject_after_write = true
verify_hash = false
helper_endpoint = "http://helper.local:8755"
log_path = "runtime/usb.jsonl"
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
    assert settings.usb.mode == "helper"
    assert settings.usb.expected_label == "ENDLESS"
    assert settings.usb.expected_uuid == "1234-ABCD"
    assert settings.usb.auto_eject_after_write is True
    assert settings.usb.verify_hash is False
    assert settings.usb.helper_endpoint == "http://helper.local:8755"
    assert settings.usb.log_path == (tmp_path / "runtime/usb.jsonl").resolve()
