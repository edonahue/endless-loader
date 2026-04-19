from pathlib import Path

from starlette.requests import Request

from endless_loader.main import create_app


def _write_config(base: Path) -> Path:
    config_path = base / "config.toml"
    config_path.write_text(
        """
library_root = "library"
pedal_mount_path = "pedal_mount"
state_path = "runtime/state.json"

[companion]
fxpatchsdk_path = "fxsdk"
cache_path = "runtime/companion_cache.json"
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_companion(base: Path) -> None:
    manifest = base / "fxsdk" / "metadata" / "endless_loader_companion.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
{
  "version": 1,
  "patches": {
    "phase_90.endl": {
      "display_name": "Phase 90",
      "source_family": "custom_sdk",
      "description": "One-knob phaser.",
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


def test_index_and_load_flow(tmp_path: Path) -> None:
    library = tmp_path / "library" / "effects" / "builds"
    library.mkdir(parents=True)
    patch_path = library / "phase_90.endl"
    patch_path.write_bytes(b"patch-data")
    (tmp_path / "pedal_mount").mkdir()
    _write_companion(tmp_path)
    config_path = _write_config(tmp_path)

    app = create_app(config_path)

    index = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/" and "GET" in getattr(route, "methods", [])
    )
    load = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/load"
    )

    index_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "app": app,
        }
    )
    response = index(index_request)
    html = response.body.decode("utf-8")
    assert response.status_code == 200
    assert "Phase 90" in html
    assert "pedal-card" in html
    assert "Preview" in html
    assert "Unused" in html
    assert "Speed" in html

    load_request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/load",
            "headers": [],
            "query_string": b"",
            "app": app,
        }
    )
    redirect = load(load_request, "effects/builds/phase_90.endl")
    assert redirect.status_code == 303
    assert "Loaded+Phase+90" in redirect.headers["location"]
    assert (tmp_path / "pedal_mount" / "phase_90.endl").read_bytes() == b"patch-data"


def test_load_and_rescan_preserve_query_context(tmp_path: Path) -> None:
    library = tmp_path / "library" / "effects" / "builds"
    library.mkdir(parents=True)
    (library / "phase_90.endl").write_bytes(b"patch-data")
    (tmp_path / "pedal_mount").mkdir()
    _write_companion(tmp_path)
    config_path = _write_config(tmp_path)

    app = create_app(config_path)

    load = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/load"
    )
    rescan = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/rescan"
    )

    load_request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/load",
            "headers": [],
            "query_string": b"",
            "app": app,
        }
    )
    load_redirect = load(
        load_request,
        "effects/builds/phase_90.endl",
        q="phase",
        selected="effects/builds/phase_90.endl",
    )
    assert load_redirect.status_code == 303
    assert "q=phase" in load_redirect.headers["location"]
    assert "selected=effects%2Fbuilds%2Fphase_90.endl" in load_redirect.headers["location"]

    rescan_redirect = rescan(q="phase", selected="effects/builds/phase_90.endl")
    assert rescan_redirect.status_code == 303
    assert "q=phase" in rescan_redirect.headers["location"]
    assert "selected=effects%2Fbuilds%2Fphase_90.endl" in rescan_redirect.headers["location"]
