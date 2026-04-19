"""Deployment service with USB backend orchestration and audit logging."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

from endless_loader.models import DeploymentOutcome, MountStatus, PatchRecord
from endless_loader.services.usb import DeploymentError, UsbBackend


class DeploymentService:
    def __init__(self, backend: UsbBackend, *, log_path: Path):
        self.backend = backend
        self.log_path = log_path
        self._last_outcome: DeploymentOutcome | None = None

    def mount_status(self) -> MountStatus:
        status = self.backend.status()
        if self._last_outcome is not None and status.last_verified is None:
            status = replace(status, last_verified=self._last_outcome.verified)
        return status

    def deploy(self, patch: PatchRecord) -> DeploymentOutcome:
        started_at = datetime.now(timezone.utc)
        try:
            outcome = self.backend.deploy(patch)
        except DeploymentError as exc:
            self._write_log(
                {
                    "event": "deploy_failed",
                    "started_at": started_at.isoformat(timespec="seconds"),
                    "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "patch": _patch_payload(patch),
                    "error": str(exc),
                    "usb": exc.status.to_dict() if exc.status else None,
                }
            )
            raise

        self._last_outcome = outcome
        self._write_log(
            {
                "event": "deploy_succeeded",
                "started_at": started_at.isoformat(timespec="seconds"),
                "finished_at": outcome.deployed_at.isoformat(timespec="seconds"),
                "patch": _patch_payload(patch),
                "outcome": outcome.to_dict(),
            }
        )
        return outcome

    def _write_log(self, payload: dict[str, object]) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True))
                handle.write("\n")
        except OSError:
            # Audit logging must not block a deploy.
            return


def _patch_payload(patch: PatchRecord) -> dict[str, object]:
    return {
        "rel_path": patch.rel_path,
        "display_name": patch.display_name,
        "filename": patch.filename,
        "source_family": patch.source_family,
    }
