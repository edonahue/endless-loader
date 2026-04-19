"""Patch deployment service."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
from uuid import uuid4

from endless_loader.models import DeploymentOutcome, MountStatus, PatchRecord


class DeploymentError(RuntimeError):
    """Raised when the pedal mount cannot be written."""


class DeploymentService:
    def __init__(self, pedal_mount_path: Path):
        self.pedal_mount_path = pedal_mount_path

    def mount_status(self) -> MountStatus:
        mount = self.pedal_mount_path
        if not mount.exists():
            return MountStatus(False, "Mount Missing", f"{mount} does not exist.")
        if not mount.is_dir():
            return MountStatus(False, "Mount Invalid", f"{mount} is not a directory.")
        if not os.access(mount, os.W_OK):
            return MountStatus(False, "Mount Read-Only", f"{mount} is not writable.")
        return MountStatus(True, "Mount Ready", f"Writing to {mount}.")

    def deploy(self, patch: PatchRecord) -> DeploymentOutcome:
        status = self.mount_status()
        if not status.ready:
            raise DeploymentError(status.detail)

        destination = self.pedal_mount_path / patch.filename
        temp_path = self.pedal_mount_path / f".{patch.filename}.tmp-{uuid4().hex}"
        shutil.copyfile(patch.abs_path, temp_path)
        os.replace(temp_path, destination)

        deployed_at = datetime.now(timezone.utc)
        message = f"Loaded {patch.display_name} to {destination.name}."
        return DeploymentOutcome(
            deployed_at=deployed_at,
            destination=destination,
            message=message,
        )
