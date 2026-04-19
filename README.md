# Endless Loader

`Endless Loader` is a phone-first web server for browsing local `.endl` patches and loading one selected patch onto a connected Polyend Endless pedal. The app is designed for Raspberry Pi OS on Pi 3B/4/5, but the same codebase also runs on Pop!_OS for development and host-side testing.

## What It Does

- Scans a configured patch library for `.endl` files.
- Groups patches into `Custom SDK`, `Official Plates`, and `Local Library` families when metadata is available.
- Presents the current or selected patch as a pedal-shaped hero card with labeled knobs.
- Uses knob labels as UI affordances: tapping a knob reveals its description and expression-role notes instead of pretending to live-edit pedal parameters.
- Copies one selected patch file onto the mounted Endless USB volume.
- Updates an optional 1602 I2C LCD:
  - line 1: patch name, truncated to 16 characters
  - line 2: fixed `4/4/4` knob labels, e.g. `Sust/Tone/Blen`
- Supports optional companion metadata from `edonahue/FxPatchSDK` through a small manifest file or a GitHub raw fallback with local caching.

## Quick Start

1. Create a virtualenv and install the app:

   ```bash
   python3 -m venv venv
   venv/bin/pip install -e ".[dev]"
   ```

2. Copy the sample config and edit it:

   ```bash
   cp config.example.toml config.toml
   ```

3. Point `library_root` at a directory containing real `.endl` files.

   Useful local paths from `FxPatchSDK` include:

   - `/home/erich/projects/FxPatchSDK/effects/builds`
   - `/home/erich/projects/FxPatchSDK/playground/polyend_plates`

4. Run the server:

   ```bash
   ENDLESS_LOADER_CONFIG=config.toml venv/bin/python -m endless_loader.main
   ```

5. Open `http://localhost:8080`.

## Config

`config.example.toml` is the host-run reference.

Important settings:

- `library_root`: directory tree to scan for `.endl` files
- `pedal_mount_path`: mounted Endless USB volume
- `state_path`: JSON state file written by the app
- `lcd.enabled`, `lcd.bus`, `lcd.address`: optional 1602 I2C backpack settings
- `companion.fxpatchsdk_path`: optional local checkout of `FxPatchSDK`

## Companion Metadata

The app does not require `FxPatchSDK`, but it can show richer patch detail when a companion manifest exists at:

```text
metadata/endless_loader_companion.json
```

inside the `FxPatchSDK` checkout, or at the corresponding raw GitHub URL.

The expected manifest shape is:

```json
{
  "version": 1,
  "patches": {
    "phase_90.endl": {
      "display_name": "Phase 90",
      "source_family": "custom_sdk",
      "description": "One-knob Phase 90 style phaser.",
      "controls": [
        {
          "slot": "left",
          "label": "Unused",
          "lcd_label": "----",
          "active": false,
          "description": "Intentionally unused."
        }
      ]
    }
  }
}
```

A sample companion tree is included under [`samples/fxpatchsdk-companion`](samples/fxpatchsdk-companion).

## Docker Compose

The repository includes:

- `compose.yaml` for the base app
- `compose.pi.yaml` for Raspberry Pi I2C device passthrough
- `compose.config.toml` as the container-oriented config sample

Base run:

```bash
docker build -t endless-loader .
```

Compose run:

```bash
docker compose up --build
```

If your host still uses older Docker packaging without the `docker compose` subcommand, use direct Python execution or install the Compose plugin first.

## LCD Behavior

When the LCD adapter is enabled and available:

- successful load: line 1 shows patch name, line 2 shows knob labels
- load error: line 1 shows `Load Error`, line 2 shows the truncated error message

## Tests

Run the test suite with:

```bash
venv/bin/pytest
```

