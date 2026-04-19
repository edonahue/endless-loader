from pathlib import Path

from endless_loader.config import CompanionConfig
from endless_loader.services.companion import CompanionMetadataProvider


def test_companion_provider_reads_local_manifest(tmp_path: Path) -> None:
    fxsdk = tmp_path / "FxPatchSDK"
    manifest = fxsdk / "metadata" / "endless_loader_companion.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
{
  "version": 1,
  "patches": {
    "phase_90.endl": {
      "display_name": "Phase 90",
      "source_family": "custom_sdk",
      "controls": [
        {"slot": "left", "label": "Unused", "lcd_label": "----", "active": false, "description": "unused"},
        {"slot": "mid", "label": "Speed", "lcd_label": "Spee", "active": true, "description": "speed"},
        {"slot": "right", "label": "Unused", "lcd_label": "----", "active": false, "description": "unused"}
      ]
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    provider = CompanionMetadataProvider(
        CompanionConfig(
            fxpatchsdk_path=fxsdk,
            cache_path=tmp_path / "cache.json",
        )
    )

    entries, source = provider.load_entries()

    assert source and source.startswith("local:")
    assert entries["phase_90.endl"]["display_name"] == "Phase 90"
    assert entries["phase_90"]["controls"][1]["label"] == "Speed"
    assert (tmp_path / "cache.json").exists()


def test_companion_provider_falls_back_to_cache_on_invalid_local_manifest(tmp_path: Path) -> None:
    fxsdk = tmp_path / "FxPatchSDK"
    manifest = fxsdk / "metadata" / "endless_loader_companion.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{bad json", encoding="utf-8")

    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        """
{
  "patches": {
    "phase_90.endl": {
      "display_name": "Phase 90",
      "source_family": "custom_sdk",
      "controls": [
        {"slot": "left", "label": "Unused", "lcd_label": "----", "active": false, "description": "unused"},
        {"slot": "mid", "label": "Speed", "lcd_label": "Spee", "active": true, "description": "speed"},
        {"slot": "right", "label": "Unused", "lcd_label": "----", "active": false, "description": "unused"}
      ]
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    provider = CompanionMetadataProvider(
        CompanionConfig(
            fxpatchsdk_path=fxsdk,
            fetch_enabled=False,
            cache_path=cache_path,
        )
    )

    entries, source = provider.load_entries()

    assert source and source.startswith("cache:")
    assert entries["phase_90.endl"]["display_name"] == "Phase 90"
