# Troubleshooting

## USB Status Says Identity Needed

Set at least one USB identity value in `config.toml`:

```toml
[usb]
expected_label = "ENDLESS"
expected_uuid = ""
```

Use `expected_uuid` when possible because it is less ambiguous than a label.

## USB Status Says Endless Not Found

Check that the pedal is exposing its storage volume and that the host sees it:

```bash
lsblk -o NAME,LABEL,UUID,FSTYPE,TRAN,MOUNTPOINTS
```

If the device appears with a different label or UUID, update `config.toml`.

## USB Status Says Multiple Matches

More than one removable volume matches the configured identity. Set `usb.expected_uuid` to the exact Endless volume UUID.

## USB Status Says Read-Only

The matched volume is mounted, but the app cannot write to it. Check mount options:

```bash
findmnt -S /dev/sdX1 -o TARGET,SOURCE,FSTYPE,OPTIONS
```

Unmount and reconnect the pedal if needed. Replace `/dev/sdX1` with the matched device shown in the web UI.

## Helper Mode Says Helper Offline

Start the helper on the host:

```bash
ENDLESS_LOADER_CONFIG=compose.helper.toml venv/bin/endless-loader-usb-helper
```

Then check:

```bash
curl http://127.0.0.1:8755/healthz
```

In Docker, confirm `compose.config.toml` points at `http://host.docker.internal:8755`.

## Companion Metadata Is Not Loaded

If the UI shows local-library fallback metadata, verify the companion path:

```toml
[companion]
fxpatchsdk_path = "/home/erich/projects/FxPatchSDK"
manifest_relpath = "metadata/endless_loader_companion.json"
```

The app can still load patches without companion metadata; the UI will use filename-derived names and default knob labels.

## LCD Does Not Update

Confirm the LCD is enabled in config:

```toml
[lcd]
enabled = true
bus = 1
address = "0x27"
```

On Raspberry Pi OS, confirm I2C is enabled and the device file exists:

```bash
ls /dev/i2c-1
```

The app falls back to a null display adapter when I2C is unavailable.
