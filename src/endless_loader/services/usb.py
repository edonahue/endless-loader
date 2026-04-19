"""USB discovery, mount, verified deploy, and helper transport backends."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Protocol
from uuid import uuid4

import httpx

from endless_loader.config import UsbConfig
from endless_loader.models import DeploymentOutcome, MountStatus, PatchRecord, UsbVolume


class DeploymentError(RuntimeError):
    """Raised when the pedal volume cannot be safely written."""

    def __init__(self, message: str, *, status: MountStatus | None = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, args: list[str]) -> CommandResult: ...


class SystemCommandRunner:
    def run(self, args: list[str]) -> CommandResult:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
        )
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class UsbBackend(Protocol):
    def status(self) -> MountStatus: ...

    def deploy(self, patch: PatchRecord) -> DeploymentOutcome: ...


class HostUsbBackend:
    def __init__(self, config: UsbConfig, runner: CommandRunner | None = None):
        self.config = config
        self.runner = runner or SystemCommandRunner()

    def status(self) -> MountStatus:
        if not self._identity_configured():
            return MountStatus(
                ready=False,
                label="Identity Missing",
                detail="Configure usb.expected_label or usb.expected_uuid before loading patches.",
                state="identity_missing",
                backend="host",
                expected_label=self.config.expected_label,
                expected_uuid=self.config.expected_uuid,
            )

        try:
            volume = self._select_volume()
        except DeploymentError as exc:
            return exc.status or MountStatus(
                ready=False,
                label="USB Error",
                detail=str(exc),
                state="error",
                backend="host",
                expected_label=self.config.expected_label,
                expected_uuid=self.config.expected_uuid,
            )

        mount_info = self._find_mount_info(volume.device_node)
        if mount_info is not None:
            volume = self._merge_volume(volume, mount_info)
            if volume.is_read_only or not os.access(volume.mountpoint or "", os.W_OK):
                return self._build_status(
                    volume,
                    ready=False,
                    label="Mounted Read-Only",
                    detail=f"{volume.mountpoint} is mounted read-only.",
                    state="read_only",
                )
            return self._build_status(
                volume,
                ready=True,
                label="Mounted",
                detail=f"Matched {volume.device_node} at {volume.mountpoint}.",
                state="mounted",
            )

        return self._build_status(
            volume,
            ready=True,
            label="Discovered",
            detail=f"Matched {volume.device_node}; it will be mounted on load.",
            state="discovered",
        )

    def deploy(self, patch: PatchRecord) -> DeploymentOutcome:
        status = self.status()
        if not status.ready:
            raise DeploymentError(status.detail, status=status)

        volume = self._select_volume()
        mounted = self._mount_if_needed(volume)
        if mounted.is_read_only or not mounted.mountpoint or not os.access(mounted.mountpoint, os.W_OK):
            status = self._build_status(
                mounted,
                ready=False,
                label="Mounted Read-Only",
                detail=f"{mounted.mountpoint or mounted.device_node} is not writable.",
                state="read_only",
            )
            raise DeploymentError(status.detail, status=status)

        destination = self._verified_copy(patch.abs_path, Path(mounted.mountpoint), patch.filename)

        ejected = False
        warning: str | None = None
        if self.config.auto_eject_after_write:
            try:
                self._unmount_and_eject(mounted)
                ejected = True
            except DeploymentError as exc:
                warning = str(exc)

        message = f"Verified {patch.display_name} on {destination.name}."
        if ejected:
            message += " Volume ejected."
        elif warning:
            message += f" Verification passed, but eject failed: {warning}"

        return DeploymentOutcome(
            deployed_at=datetime.now(timezone.utc),
            destination=destination,
            message=message,
            backend="host",
            verified=True,
            device_node=mounted.device_node,
            device_label=mounted.label,
            device_uuid=mounted.uuid,
            mountpoint=mounted.mountpoint,
            state="verified",
            ejected=ejected,
            warning=warning,
        )

    def _identity_configured(self) -> bool:
        return bool(self.config.expected_label or self.config.expected_uuid)

    def _select_volume(self) -> UsbVolume:
        matches = [volume for volume in self._discover_volumes() if self._matches_expected_identity(volume)]
        if not matches:
            status = MountStatus(
                ready=False,
                label="No Endless Volume",
                detail="No removable volume matched the configured label/UUID.",
                state="no_match",
                backend="host",
                expected_label=self.config.expected_label,
                expected_uuid=self.config.expected_uuid,
            )
            raise DeploymentError(status.detail, status=status)
        if len(matches) > 1:
            status = MountStatus(
                ready=False,
                label="Multiple Matches",
                detail="More than one removable volume matched the configured label/UUID.",
                state="multiple_matches",
                backend="host",
                expected_label=self.config.expected_label,
                expected_uuid=self.config.expected_uuid,
            )
            raise DeploymentError(status.detail, status=status)
        return matches[0]

    def _discover_volumes(self) -> list[UsbVolume]:
        result = self.runner.run(
            [
                "lsblk",
                "--json",
                "-o",
                "PATH,KNAME,PKNAME,LABEL,UUID,FSTYPE,TRAN,HOTPLUG,RM,MOUNTPOINTS",
            ]
        )
        if result.returncode != 0:
            raise DeploymentError(f"lsblk failed: {result.stderr.strip() or result.stdout.strip()}")

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise DeploymentError(f"Could not parse lsblk output: {exc}") from exc

        volumes: list[UsbVolume] = []
        for item in payload.get("blockdevices", []):
            if isinstance(item, dict):
                volumes.extend(self._flatten_blockdevice(item))
        return volumes

    def _matches_expected_identity(self, volume: UsbVolume) -> bool:
        if not volume.device_node or not volume.fstype:
            return False
        label_match = (
            True
            if not self.config.expected_label
            else volume.label == self.config.expected_label
        )
        uuid_match = (
            True
            if not self.config.expected_uuid
            else volume.uuid == self.config.expected_uuid
        )
        return label_match and uuid_match

    def _flatten_blockdevice(
        self,
        item: dict[str, Any],
        *,
        inherited_transport: str | None = None,
        inherited_hotplug: bool = False,
        inherited_removable: bool = False,
    ) -> list[UsbVolume]:
        mountpoints = item.get("mountpoints") or []
        mountpoint = next((point for point in mountpoints if point), None)
        transport = str(item.get("tran")) if item.get("tran") else inherited_transport
        hotplug = _bool_or_default(item.get("hotplug"), inherited_hotplug)
        removable = _bool_or_default(item.get("rm"), inherited_removable)
        current = UsbVolume(
            device_node=str(item.get("path") or ""),
            parent_device_node=(
                f"/dev/{item['pkname']}" if item.get("pkname") else None
            ),
            label=item.get("label"),
            uuid=item.get("uuid"),
            fstype=item.get("fstype"),
            transport=transport,
            hotplug=hotplug,
            removable=removable,
            mountpoint=mountpoint,
        )
        flattened = [current] if current.device_node else []
        for child in item.get("children", []):
            if isinstance(child, dict):
                flattened.extend(
                    self._flatten_blockdevice(
                        child,
                        inherited_transport=transport,
                        inherited_hotplug=hotplug,
                        inherited_removable=removable,
                    )
                )
        return flattened

    def _find_mount_info(self, device_node: str) -> UsbVolume | None:
        result = self.runner.run(
            [
                "findmnt",
                "--json",
                "-S",
                device_node,
                "-o",
                "TARGET,SOURCE,FSTYPE,OPTIONS",
            ]
        )
        if result.returncode != 0:
            return None
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
        filesystems = payload.get("filesystems") or []
        if not filesystems:
            return None
        fs = filesystems[0]
        options = tuple((fs.get("options") or "").split(","))
        return UsbVolume(
            device_node=device_node,
            label=None,
            uuid=None,
            fstype=fs.get("fstype"),
            mountpoint=fs.get("target"),
            mount_options=tuple(option for option in options if option),
        )

    def _mount_if_needed(self, volume: UsbVolume) -> UsbVolume:
        mounted = self._find_mount_info(volume.device_node)
        if mounted is not None and mounted.mountpoint:
            return self._merge_volume(volume, mounted)

        mount_result = self.runner.run(["udisksctl", "mount", "-b", volume.device_node])
        if mount_result.returncode != 0:
            status = self._build_status(
                volume,
                ready=False,
                label="Mount Failed",
                detail=mount_result.stderr.strip() or mount_result.stdout.strip() or "udisksctl mount failed.",
                state="mount_failed",
            )
            raise DeploymentError(status.detail, status=status)

        mounted = self._find_mount_info(volume.device_node)
        if mounted is None or not mounted.mountpoint:
            status = self._build_status(
                volume,
                ready=False,
                label="Mount Missing",
                detail="The volume reported mounted, but no mountpoint was found.",
                state="mount_missing",
            )
            raise DeploymentError(status.detail, status=status)
        return self._merge_volume(volume, mounted)

    def _verified_copy(self, source: Path, mountpoint: Path, filename: str) -> Path:
        destination = mountpoint / filename
        temp_path = mountpoint / f".{filename}.tmp-{uuid4().hex}"

        with source.open("rb") as src, temp_path.open("wb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(temp_path, destination)

        dir_fd = os.open(mountpoint, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

        if self.config.verify_hash:
            src_size = source.stat().st_size
            dst_size = destination.stat().st_size
            if src_size != dst_size or self._sha256(source) != self._sha256(destination):
                raise DeploymentError("Read-back verification failed after copy.")
        return destination

    def _unmount_and_eject(self, volume: UsbVolume) -> None:
        unmount_result = self.runner.run(["udisksctl", "unmount", "-b", volume.device_node])
        if unmount_result.returncode != 0:
            raise DeploymentError(unmount_result.stderr.strip() or "Could not unmount the Endless volume.")

        power_target = volume.parent_device_node or volume.device_node
        power_result = self.runner.run(["udisksctl", "power-off", "-b", power_target])
        if power_result.returncode != 0:
            raise DeploymentError(power_result.stderr.strip() or "Could not power off the Endless USB volume.")

    def _build_status(
        self,
        volume: UsbVolume,
        *,
        ready: bool,
        label: str,
        detail: str,
        state: str,
    ) -> MountStatus:
        return MountStatus(
            ready=ready,
            label=label,
            detail=detail,
            state=state,
            backend="host",
            expected_label=self.config.expected_label,
            expected_uuid=self.config.expected_uuid,
            device_node=volume.device_node,
            device_label=volume.label,
            device_uuid=volume.uuid,
            mountpoint=volume.mountpoint,
            last_verified=True if state == "verified" else None,
        )

    @staticmethod
    def _merge_volume(original: UsbVolume, mounted: UsbVolume) -> UsbVolume:
        return UsbVolume(
            device_node=original.device_node,
            parent_device_node=original.parent_device_node,
            label=original.label,
            uuid=original.uuid,
            fstype=original.fstype or mounted.fstype,
            transport=original.transport,
            hotplug=original.hotplug,
            removable=original.removable,
            mountpoint=mounted.mountpoint,
            mount_options=mounted.mount_options,
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()


class HelperUsbBackend:
    def __init__(self, config: UsbConfig):
        self.config = config

    def status(self) -> MountStatus:
        try:
            with httpx.Client(timeout=self.config.discovery_timeout_seconds) as client:
                response = client.get(f"{self.config.helper_endpoint.rstrip('/')}/v1/usb/status")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return MountStatus(
                ready=False,
                label="Helper Offline",
                detail=f"USB helper unavailable: {exc}",
                state="helper_offline",
                backend="helper",
                expected_label=self.config.expected_label,
                expected_uuid=self.config.expected_uuid,
            )
        payload["backend"] = "helper"
        return MountStatus(**payload)

    def deploy(self, patch: PatchRecord) -> DeploymentOutcome:
        try:
            with patch.abs_path.open("rb") as handle, httpx.Client(
                timeout=max(30, self.config.discovery_timeout_seconds)
            ) as client:
                response = client.post(
                    f"{self.config.helper_endpoint.rstrip('/')}/v1/usb/deploy",
                    data={
                        "display_name": patch.display_name,
                        "rel_path": patch.rel_path,
                    },
                    files={"file": (patch.filename, handle, "application/octet-stream")},
                )
                payload = response.json()
        except (OSError, httpx.HTTPError, ValueError) as exc:
            raise DeploymentError(f"USB helper deploy failed: {exc}") from exc

        if response.status_code >= 400:
            status_payload = payload.get("usb") if isinstance(payload, dict) else None
            status = None
            if isinstance(status_payload, dict):
                status_payload["backend"] = "helper"
                status = MountStatus(**status_payload)
            error = (
                payload.get("error")
                if isinstance(payload, dict) and payload.get("error")
                else f"USB helper deploy failed with status {response.status_code}."
            )
            raise DeploymentError(str(error), status=status)

        return DeploymentOutcome(
            deployed_at=datetime.fromisoformat(payload["deployed_at"]),
            destination=Path(payload["destination"]),
            message=str(payload["message"]),
            backend="helper",
            verified=bool(payload.get("verified", False)),
            device_node=payload.get("device_node"),
            device_label=payload.get("device_label"),
            device_uuid=payload.get("device_uuid"),
            mountpoint=payload.get("mountpoint"),
            state=str(payload.get("state", "verified")),
            ejected=bool(payload.get("ejected", False)),
            warning=payload.get("warning"),
        )


def build_usb_backend(config: UsbConfig, runner: CommandRunner | None = None) -> UsbBackend:
    if config.mode == "helper":
        return HelperUsbBackend(config)
    return HostUsbBackend(config, runner=runner)


def _bool_or_default(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)
