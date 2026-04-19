"""Config loading for Endless Loader."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import tomllib
from typing import Any


@dataclass(frozen=True)
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass(frozen=True)
class LcdConfig:
    enabled: bool = False
    bus: int = 1
    address: int = 0x27


@dataclass(frozen=True)
class ButtonConfig:
    enabled: bool = False
    next_pin: int | None = None
    prev_pin: int | None = None
    load_pin: int | None = None


@dataclass(frozen=True)
class CompanionConfig:
    fxpatchsdk_path: Path | None = None
    manifest_relpath: Path = Path("metadata/endless_loader_companion.json")
    github_repo: str = "edonahue/FxPatchSDK"
    github_branch: str = "master"
    fetch_enabled: bool = True
    timeout_seconds: int = 5
    cache_path: Path = Path("data/companion_cache.json")


@dataclass(frozen=True)
class Settings:
    config_path: Path
    library_root: Path
    pedal_mount_path: Path
    state_path: Path
    web: WebConfig = field(default_factory=WebConfig)
    lcd: LcdConfig = field(default_factory=LcdConfig)
    buttons: ButtonConfig = field(default_factory=ButtonConfig)
    companion: CompanionConfig = field(default_factory=CompanionConfig)


def _resolve_path(base: Path, raw: str | None, fallback: str) -> Path:
    value = raw or fallback
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = (base / candidate).resolve()
    return candidate


def _resolve_optional_path(base: Path, raw: str | None) -> Path | None:
    if not raw:
        return None
    return _resolve_path(base, raw, raw)


def _get_section(data: dict[str, Any], key: str) -> dict[str, Any]:
    section = data.get(key, {})
    return section if isinstance(section, dict) else {}


def default_config_path() -> Path:
    raw = os.environ.get("ENDLESS_LOADER_CONFIG")
    if raw:
        return Path(raw).expanduser()
    return Path("config.toml")


def load_settings(config_path: str | Path | None = None) -> Settings:
    path = Path(config_path).expanduser() if config_path else default_config_path()
    base = path.parent.resolve()
    data: dict[str, Any] = {}
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))

    web = _get_section(data, "web")
    lcd = _get_section(data, "lcd")
    buttons = _get_section(data, "buttons")
    companion = _get_section(data, "companion")

    return Settings(
        config_path=path.resolve(),
        library_root=_resolve_path(base, data.get("library_root"), "samples/library"),
        pedal_mount_path=_resolve_path(base, data.get("pedal_mount_path"), "data/pedal_mount"),
        state_path=_resolve_path(base, data.get("state_path"), "data/runtime/state.json"),
        web=WebConfig(
            host=str(web.get("host", "0.0.0.0")),
            port=int(web.get("port", 8080)),
        ),
        lcd=LcdConfig(
            enabled=bool(lcd.get("enabled", False)),
            bus=int(lcd.get("bus", 1)),
            address=int(str(lcd.get("address", "0x27")), 0),
        ),
        buttons=ButtonConfig(
            enabled=bool(buttons.get("enabled", False)),
            next_pin=_optional_int(buttons.get("next_pin")),
            prev_pin=_optional_int(buttons.get("prev_pin")),
            load_pin=_optional_int(buttons.get("load_pin")),
        ),
        companion=CompanionConfig(
            fxpatchsdk_path=_resolve_optional_path(base, companion.get("fxpatchsdk_path")),
            manifest_relpath=Path(
                str(companion.get("manifest_relpath", "metadata/endless_loader_companion.json"))
            ),
            github_repo=str(companion.get("github_repo", "edonahue/FxPatchSDK")),
            github_branch=str(companion.get("github_branch", "master")),
            fetch_enabled=bool(companion.get("fetch_enabled", True)),
            timeout_seconds=int(companion.get("timeout_seconds", 5)),
            cache_path=_resolve_path(
                base,
                companion.get("cache_path"),
                "data/companion_cache.json",
            ),
        ),
    )


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(value)
