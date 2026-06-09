"""Capture README screenshots from a temporary demo Endless Loader app."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time

import uvicorn

from endless_loader.main import create_app
from endless_loader.models import DeploymentOutcome, MountStatus, PatchRecord
from endless_loader.services.deploy import DeploymentService


REPO_ROOT = Path(__file__).resolve().parents[1]


class DemoUsbBackend:
    def __init__(self, mount: Path, *, ready: bool):
        self.mount = mount
        self.ready = ready

    def status(self) -> MountStatus:
        if not self.ready:
            return MountStatus(
                ready=False,
                label="No Endless Volume",
                detail="No removable volume matched the configured label/UUID.",
                state="no_match",
                backend="host",
                expected_label="ENDLESS",
            )
        return MountStatus(
            ready=True,
            label="Mounted",
            detail=f"Matched /dev/sda1 at {self.mount}.",
            state="mounted",
            backend="host",
            expected_label="ENDLESS",
            device_node="/dev/sda1",
            device_label="ENDLESS",
            mountpoint=str(self.mount),
        )

    def deploy(self, patch: PatchRecord) -> DeploymentOutcome:
        destination = self.mount / patch.filename
        shutil.copyfile(patch.abs_path, destination)
        return DeploymentOutcome(
            deployed_at=datetime.now(timezone.utc),
            destination=destination,
            message=f"Verified {patch.display_name} on {destination.name}.",
            backend="host",
            verified=True,
            device_node="/dev/sda1",
            device_label="ENDLESS",
            mountpoint=str(self.mount),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture Endless Loader screenshots.")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "docs" / "assets",
        help="Directory for generated PNG screenshots.",
    )
    parser.add_argument(
        "--firefox",
        default=shutil.which("firefox"),
        help="Path to Firefox with --headless --screenshot support.",
    )
    args = parser.parse_args()

    if not args.firefox:
        raise SystemExit("Firefox was not found on PATH.")

    args.output.mkdir(parents=True, exist_ok=True)
    captures = [
        ("desktop-console.png", 1440, 1200, True),
        ("mobile-console.png", 390, 1200, True),
        ("mobile-usb-not-ready.png", 390, 1200, False),
    ]

    for name, width, height, ready in captures:
        with tempfile.TemporaryDirectory(prefix="endless-loader-shot-") as raw_tmp:
            tmp = Path(raw_tmp)
            config_path = _write_demo_config(tmp)
            _write_demo_library(tmp)
            app = create_app(config_path)
            app.state.services.deployment = DeploymentService(
                DemoUsbBackend(tmp / "pedal_mount", ready=ready),
                log_path=tmp / "runtime" / "usb_operations.jsonl",
            )
            port = _free_port()
            server = uvicorn.Server(
                uvicorn.Config(
                    app,
                    host="127.0.0.1",
                    port=port,
                    log_level="warning",
                    lifespan="off",
                )
            )
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            _wait_for_server(port)
            try:
                _capture(
                    args.firefox,
                    args.output / name,
                    f"http://127.0.0.1:{port}/?selected=effects/builds/phase_90.endl",
                    width=width,
                    height=height,
                )
            finally:
                server.should_exit = True
                thread.join(timeout=5)
    return 0


def _write_demo_config(tmp: Path) -> Path:
    config = tmp / "config.toml"
    config.write_text(
        f"""
library_root = "{(tmp / "library").as_posix()}"
pedal_mount_path = "{(tmp / "pedal_mount").as_posix()}"
state_path = "{(tmp / "runtime" / "state.json").as_posix()}"

[companion]
fxpatchsdk_path = "{(REPO_ROOT / "samples" / "fxpatchsdk-companion").as_posix()}"
cache_path = "{(tmp / "runtime" / "companion_cache.json").as_posix()}"

[usb]
mode = "host"
expected_label = "ENDLESS"
""".strip(),
        encoding="utf-8",
    )
    return config


def _write_demo_library(tmp: Path) -> None:
    for rel_path in (
        "effects/builds/phase_90.endl",
        "effects/builds/tube_screamer.endl",
        "polyend_plates/Wax.endl",
        "local/ambient_cloud.endl",
    ):
        path = tmp / "library" / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"demo-patch")
    (tmp / "pedal_mount").mkdir(parents=True, exist_ok=True)
    (tmp / "runtime").mkdir(parents=True, exist_ok=True)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(port: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"Server on port {port} did not become ready.")


def _capture(
    firefox: str,
    output: Path,
    url: str,
    *,
    width: int,
    height: int,
) -> None:
    subprocess.run(
        [
            firefox,
            "--headless",
            "--window-size",
            f"{width},{height}",
            "--screenshot",
            str(output),
            url,
        ],
        check=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
