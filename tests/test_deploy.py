from pathlib import Path

from endless_loader.models import PatchRecord
from endless_loader.services.deploy import DeploymentService


def test_deploy_copies_selected_patch(tmp_path: Path) -> None:
    source = tmp_path / "phase_90.endl"
    source.write_bytes(b"patch-bytes")
    mount = tmp_path / "mount"
    mount.mkdir()

    service = DeploymentService(mount)
    patch = PatchRecord(
        rel_path="phase_90.endl",
        abs_path=source,
        filename=source.name,
        display_name="Phase 90",
        source_family="custom_sdk",
    )

    outcome = service.deploy(patch)

    assert (mount / "phase_90.endl").read_bytes() == b"patch-bytes"
    assert outcome.destination == mount / "phase_90.endl"
    assert "Loaded Phase 90" in outcome.message

