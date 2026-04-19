import json
from datetime import datetime, timezone
from pathlib import Path

from endless_loader.models import DeploymentOutcome, MountStatus, PatchRecord
from endless_loader.services.deploy import DeploymentService


class FakeBackend:
    def __init__(self, destination: Path):
        self.destination = destination

    def status(self) -> MountStatus:
        return MountStatus(
            ready=True,
            label="Mounted",
            detail="Matched /dev/sdz1 at mountpoint.",
            state="mounted",
            backend="host",
            device_node="/dev/sdz1",
            device_label="ENDLESS",
            mountpoint=str(self.destination.parent),
        )

    def deploy(self, patch: PatchRecord) -> DeploymentOutcome:
        self.destination.write_bytes(patch.abs_path.read_bytes())
        return DeploymentOutcome(
            deployed_at=datetime.now(timezone.utc),
            destination=self.destination,
            message=f"Verified {patch.display_name} on {self.destination.name}.",
            backend="host",
            verified=True,
            device_node="/dev/sdz1",
            device_label="ENDLESS",
            mountpoint=str(self.destination.parent),
        )


def test_deploy_logs_selected_patch(tmp_path: Path) -> None:
    source = tmp_path / "phase_90.endl"
    source.write_bytes(b"patch-bytes")
    mount = tmp_path / "mount"
    mount.mkdir()
    destination = mount / "phase_90.endl"
    log_path = tmp_path / "runtime" / "usb.jsonl"

    service = DeploymentService(FakeBackend(destination), log_path=log_path)
    patch = PatchRecord(
        rel_path="phase_90.endl",
        abs_path=source,
        filename=source.name,
        display_name="Phase 90",
        source_family="custom_sdk",
    )

    outcome = service.deploy(patch)
    log_entry = json.loads(log_path.read_text(encoding="utf-8").strip())

    assert destination.read_bytes() == b"patch-bytes"
    assert outcome.destination == destination
    assert "Verified Phase 90" in outcome.message
    assert log_entry["event"] == "deploy_succeeded"
    assert log_entry["patch"]["display_name"] == "Phase 90"
    assert log_entry["outcome"]["verified"] is True
