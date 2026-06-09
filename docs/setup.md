# Setup

This guide covers the repeatable setup paths for Endless Loader on Raspberry Pi OS, Ubuntu-family Linux, and Docker.

## Host Mode

Use host mode when the web server runs directly on the machine that can see the Endless USB storage device.

Install system prerequisites:

```bash
sudo apt install python3 python3-venv udisks2 util-linux
```

Install the app:

```bash
python3 -m venv venv
venv/bin/pip install -e ".[dev]"
cp config.example.toml config.toml
```

Edit `config.toml`:

```toml
library_root = "/path/to/endl/patches"

[usb]
mode = "host"
expected_label = "ENDLESS"
expected_uuid = ""
```

Prefer `expected_uuid` once you know the Endless volume UUID:

```bash
lsblk -o NAME,LABEL,UUID,FSTYPE,TRAN,MOUNTPOINTS
```

Run the app:

```bash
ENDLESS_LOADER_CONFIG=config.toml venv/bin/endless-loader
```

Open `http://localhost:8080`.

## Raspberry Pi Notes

The target Pi path is Raspberry Pi OS on a Pi 3B, 4, or 5. The Pi should be on the same network as the phone or desktop browser.

For the optional 1602 I2C LCD:

```toml
[lcd]
enabled = true
bus = 1
address = "0x27"
```

If the LCD does not appear, confirm I2C is enabled in Raspberry Pi OS and that `/dev/i2c-1` exists.

## Docker Helper Mode

Use helper mode when the web app runs in Docker. The container should not control host USB mounts directly.

Run the USB helper on the host:

```bash
ENDLESS_LOADER_CONFIG=compose.helper.toml venv/bin/endless-loader-usb-helper
```

Run the container:

```bash
docker compose up --build
```

The app container uses `compose.config.toml`, which points `usb.helper_endpoint` at `http://host.docker.internal:8755`.

## Screenshot Capture

Screenshots in `docs/assets/` are generated from a temporary demo app:

```bash
venv/bin/python scripts/capture_screenshots.py
```

The script requires Firefox on `PATH` because it uses Firefox headless screenshot support.
