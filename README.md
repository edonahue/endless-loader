# Endless Loader

`Endless Loader` is a phone-first web server for browsing local `.endl` patches and loading one selected patch onto a connected Polyend Endless pedal. The app is designed for Raspberry Pi OS on Pi 3B/4/5, and the same codebase is intended to run on Ubuntu-family Linux systems including Pop!_OS and standard Ubuntu desktops or mini PCs.

## What It Does

- Scans a configured patch library for `.endl` files.
- Groups patches into `Custom SDK`, `Official Plates`, and `Local Library` families when metadata is available.
- Presents the current or selected patch as a pedal-shaped hero card with labeled knobs.
- Uses knob labels as UI affordances: tapping a knob reveals its description and expression-role notes instead of pretending to live-edit pedal parameters.
- Discovers the correct Endless USB volume by configured label or UUID, mounts it when needed, copies the selected patch, and verifies the write with a read-back hash.
- Updates an optional 1602 I2C LCD:
  - line 1: patch name, truncated to 16 characters
  - line 2: fixed `4/4/4` knob labels, e.g. `Sust/Tone/Blen`
- Supports optional companion metadata from `edonahue/FxPatchSDK` through a small manifest file or a GitHub raw fallback with local caching.
- Supports two deployment modes:
  - `host`: direct discovery and `udisksctl` control on Raspberry Pi OS or Ubuntu-family Linux
  - `helper`: Docker-friendly mode where the web app delegates USB operations to a small host-side helper

## Platform Support

The current app code is portable across:

- Raspberry Pi OS on Pi 3B/4/5
- Ubuntu 22.04+ and other Ubuntu-family distributions with Python 3.10+
- Pop!_OS as one Ubuntu-family example, not a special-case target

For `usb.mode = "host"`, the host needs these standard Linux tools available:

- `lsblk`
- `findmnt`
- `udisksctl`

On Ubuntu-family systems, those normally come from:

- `util-linux`
- `udisks2`
- `python3-venv` for local virtualenv setup

## Quick Start

1. Create a virtualenv and install the app:

   ```bash
   python3 -m venv venv
   venv/bin/pip install -e ".[dev]"
   ```

   On a fresh Ubuntu-family host, install the common prerequisites first:

   ```bash
   sudo apt install python3 python3-venv udisks2 util-linux
   ```

2. Copy the sample config and edit it:

   ```bash
   cp config.example.toml config.toml
   ```

3. Point `library_root` at a directory containing real `.endl` files.

   Useful local paths from `FxPatchSDK` include:

   - `/home/erich/projects/FxPatchSDK/effects/builds`
   - `/home/erich/projects/FxPatchSDK/playground/polyend_plates`

4. Configure the USB identity in `config.toml`.

   Use `usb.expected_uuid` for the strongest match, or `usb.expected_label` if the Endless volume label is stable on your machines.

5. Run the server:

   ```bash
   ENDLESS_LOADER_CONFIG=config.toml venv/bin/python -m endless_loader.main
   ```

6. Open `http://localhost:8080`.

## Config

`config.example.toml` is the host-run reference.

Important settings:

- `library_root`: directory tree to scan for `.endl` files
- `pedal_mount_path`: legacy compatibility path for local development
- `state_path`: JSON state file written by the app
- `lcd.enabled`, `lcd.bus`, `lcd.address`: optional 1602 I2C backpack settings
- `companion.fxpatchsdk_path`: optional local checkout of `FxPatchSDK`
- `usb.mode`: `host` for direct USB control, `helper` for Docker-backed deployments
- `usb.expected_label` / `usb.expected_uuid`: identity used to select the correct Endless volume
- `usb.verify_hash`: read the file back and compare hashes after copy
- `usb.auto_eject_after_write`: optional safe eject after a verified write
- `usb.helper_endpoint`: helper URL for containerized deployments

## USB Certainty Model

When `usb.mode = "host"`, the app uses:

- `lsblk --json` to discover candidate block devices and partitions
- `findmnt --json` to determine the current mountpoint and read-only state
- `udisksctl mount` to mount the matched Endless volume when needed
- a temp-file copy plus atomic `os.replace` on the target volume
- `fsync` on the file and containing directory
- a read-back SHA-256 check when `usb.verify_hash = true`
- optional `udisksctl unmount` and `power-off` when `usb.auto_eject_after_write = true`

That same flow works on Raspberry Pi OS, Ubuntu, Pop!_OS, and similar Ubuntu-derived systems because they expose the same `util-linux` and `udisks2` tools. If you want the highest confidence, set `usb.expected_uuid` instead of relying on a label alone.

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

In Docker, the web app should not manage host USB mounts directly. The included `compose.config.toml` sets `usb.mode = "helper"` and routes deployment calls to `http://host.docker.internal:8755`.

Run the helper on the host first:

```bash
ENDLESS_LOADER_CONFIG=compose.helper.toml venv/bin/endless-loader-usb-helper
```

Then start the app container:

```bash
docker compose up --build
```

The compose file already adds `host.docker.internal:host-gateway` so Linux Docker can reach the host helper reliably.

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
