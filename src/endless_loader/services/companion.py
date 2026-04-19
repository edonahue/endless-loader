"""Optional companion metadata loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from endless_loader.config import CompanionConfig
from endless_loader.models import compact_lcd_label, humanize_stem

_SLOT_ORDER = ("left", "mid", "right")


class CompanionMetadataProvider:
    """Load optional patch metadata from a sister repo or cache."""

    def __init__(self, config: CompanionConfig):
        self.config = config

    def load_entries(self) -> tuple[dict[str, dict[str, Any]], str | None]:
        local_manifest = self._local_manifest_path()
        if local_manifest and local_manifest.exists():
            payload = self._read_json(local_manifest)
            normalized = self._normalize_manifest(payload)
            self._write_cache(payload)
            return normalized, f"local:{local_manifest}"

        if self.config.fetch_enabled:
            payload = self._fetch_remote_manifest()
            if payload is not None:
                normalized = self._normalize_manifest(payload)
                self._write_cache(payload)
                return normalized, "github"

        cache_path = self.config.cache_path
        if cache_path.exists():
            payload = self._read_json(cache_path)
            return self._normalize_manifest(payload), f"cache:{cache_path}"

        return {}, None

    def _local_manifest_path(self) -> Path | None:
        if self.config.fxpatchsdk_path is None:
            return None
        return self.config.fxpatchsdk_path / self.config.manifest_relpath

    def _fetch_remote_manifest(self) -> dict[str, Any] | None:
        rel_path = self.config.manifest_relpath.as_posix()
        raw_url = (
            f"https://raw.githubusercontent.com/"
            f"{self.config.github_repo}/{self.config.github_branch}/{rel_path}"
        )
        try:
            with urlopen(raw_url, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, json.JSONDecodeError):
            return None

    def _write_cache(self, payload: dict[str, Any]) -> None:
        cache_path = self.config.cache_path
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _normalize_manifest(self, payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        raw_patches = payload.get("patches", payload)
        if not isinstance(raw_patches, dict):
            return {}

        normalized: dict[str, dict[str, Any]] = {}
        for key, value in raw_patches.items():
            if not isinstance(value, dict):
                continue
            record = {
                "display_name": str(value.get("display_name") or humanize_stem(Path(key).stem)),
                "source_family": str(value.get("source_family") or "local_library"),
                "description": value.get("description"),
                "controls": self._normalize_controls(value.get("controls")),
                "short_action": value.get("short_action"),
                "long_action": value.get("long_action"),
                "source_url": value.get("source_url"),
                "doc_url": value.get("doc_url"),
            }
            for candidate in self._candidate_keys(key):
                normalized[candidate] = record
        return normalized

    def _normalize_controls(self, value: object) -> list[dict[str, Any]]:
        slots = {slot: self._default_control(slot) for slot in _SLOT_ORDER}
        if isinstance(value, list):
            for raw in value:
                if not isinstance(raw, dict):
                    continue
                slot = str(raw.get("slot", "")).lower()
                if slot not in slots:
                    continue
                active = bool(raw.get("active", True))
                label = str(raw.get("label", "Unused"))
                slots[slot] = {
                    "slot": slot,
                    "label": label,
                    "description": str(
                        raw.get("description")
                        or ("Not used in this patch." if not active else "No companion details yet.")
                    ),
                    "lcd_label": str(raw.get("lcd_label") or compact_lcd_label(label, active=active)),
                    "active": active,
                    "expression_note": raw.get("expression_note"),
                }
        return [slots[slot] for slot in _SLOT_ORDER]

    @staticmethod
    def _candidate_keys(raw_key: str) -> list[str]:
        path = Path(raw_key)
        keys = {
            raw_key.lower(),
            path.name.lower(),
            path.stem.lower(),
        }
        return sorted(keys)

    @staticmethod
    def _default_control(slot: str) -> dict[str, Any]:
        label = slot.title()
        return {
            "slot": slot,
            "label": label,
            "description": "No companion details yet.",
            "lcd_label": compact_lcd_label(label),
            "active": True,
            "expression_note": None,
        }
