from pathlib import Path

from endless_loader.services.scanner import scan_library


def test_scan_library_uses_companion_metadata_and_groups(tmp_path: Path) -> None:
    custom_dir = tmp_path / "effects" / "builds"
    plates_dir = tmp_path / "polyend_plates"
    misc_dir = tmp_path / "misc"
    custom_dir.mkdir(parents=True)
    plates_dir.mkdir(parents=True)
    misc_dir.mkdir(parents=True)

    (custom_dir / "tube_screamer.endl").write_bytes(b"custom")
    (plates_dir / "Wax.endl").write_bytes(b"plates")
    (misc_dir / "ambient.endl").write_bytes(b"misc")

    companion = {
        "tube_screamer.endl": {
            "display_name": "Tube Screamer",
            "source_family": "custom_sdk",
            "description": "OD",
            "controls": [
                {"slot": "left", "label": "Drive", "lcd_label": "Driv", "active": True, "description": "drive"},
                {"slot": "mid", "label": "Level", "lcd_label": "Leve", "active": True, "description": "level"},
                {"slot": "right", "label": "Tone", "lcd_label": "Tone", "active": True, "description": "tone"},
            ],
        }
    }

    records = scan_library(tmp_path, companion, "local:test")

    assert [record.display_name for record in records] == ["Tube Screamer", "Ambient", "Wax"]
    assert records[0].source_family == "custom_sdk"
    assert records[1].source_family == "local_library"
    assert records[2].source_family == "official_plates"

