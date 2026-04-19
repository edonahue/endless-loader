import json
from pathlib import Path

from endless_loader.config import UsbConfig
from endless_loader.models import PatchRecord
from endless_loader.services.usb import CommandResult, HostUsbBackend


class ScriptedRunner:
    def __init__(self, script: list[tuple[list[str], CommandResult]]):
        self.script = list(script)
        self.calls: list[list[str]] = []

    def run(self, args: list[str]) -> CommandResult:
        self.calls.append(args)
        expected_args, result = self.script.pop(0)
        assert args == expected_args
        return result


def _lsblk_payload(*, mounted: str | None = None, duplicate: bool = False) -> str:
    blockdevices = [
        {
            "path": "/dev/sda",
            "kname": "sda",
            "pkname": None,
            "label": None,
            "uuid": None,
            "fstype": None,
            "tran": "usb",
            "hotplug": 1,
            "rm": 1,
            "mountpoints": [None],
            "children": [
                {
                    "path": "/dev/sda1",
                    "kname": "sda1",
                    "pkname": "sda",
                    "label": "ENDLESS",
                    "uuid": "ABCD-1234",
                    "fstype": "vfat",
                    "tran": None,
                    "hotplug": None,
                    "rm": None,
                    "mountpoints": [mounted],
                }
            ],
        }
    ]
    if duplicate:
        blockdevices.append(
            {
                "path": "/dev/sdb",
                "kname": "sdb",
                "pkname": None,
                "label": None,
                "uuid": None,
                "fstype": None,
                "tran": "usb",
                "hotplug": 1,
                "rm": 1,
                "mountpoints": [None],
                "children": [
                    {
                        "path": "/dev/sdb1",
                        "kname": "sdb1",
                        "pkname": "sdb",
                        "label": "ENDLESS",
                        "uuid": "ABCD-1234",
                        "fstype": "vfat",
                        "tran": None,
                        "hotplug": None,
                        "rm": None,
                        "mountpoints": [None],
                    }
                ],
            }
        )
    return json.dumps({"blockdevices": blockdevices})


def test_host_status_discovers_nested_partition_by_label() -> None:
    runner = ScriptedRunner(
        [
            (
                [
                    "lsblk",
                    "--json",
                    "-o",
                    "PATH,KNAME,PKNAME,LABEL,UUID,FSTYPE,TRAN,HOTPLUG,RM,MOUNTPOINTS",
                ],
                CommandResult(returncode=0, stdout=_lsblk_payload(), stderr=""),
            ),
            (
                ["findmnt", "--json", "-S", "/dev/sda1", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"],
                CommandResult(returncode=1, stdout='{"filesystems":[]}', stderr=""),
            ),
        ]
    )
    backend = HostUsbBackend(UsbConfig(expected_label="ENDLESS"), runner=runner)

    status = backend.status()

    assert status.ready is True
    assert status.state == "discovered"
    assert status.device_node == "/dev/sda1"
    assert status.expected_label == "ENDLESS"


def test_host_status_rejects_multiple_matches() -> None:
    runner = ScriptedRunner(
        [
            (
                [
                    "lsblk",
                    "--json",
                    "-o",
                    "PATH,KNAME,PKNAME,LABEL,UUID,FSTYPE,TRAN,HOTPLUG,RM,MOUNTPOINTS",
                ],
                CommandResult(returncode=0, stdout=_lsblk_payload(duplicate=True), stderr=""),
            ),
        ]
    )
    backend = HostUsbBackend(UsbConfig(expected_label="ENDLESS"), runner=runner)

    status = backend.status()

    assert status.ready is False
    assert status.state == "multiple_matches"


def test_host_deploy_mounts_and_verifies_copy(tmp_path: Path) -> None:
    source = tmp_path / "phase_90.endl"
    source.write_bytes(b"patch-bytes")
    mountpoint = tmp_path / "mnt"
    mountpoint.mkdir()

    runner = ScriptedRunner(
        [
            (
                [
                    "lsblk",
                    "--json",
                    "-o",
                    "PATH,KNAME,PKNAME,LABEL,UUID,FSTYPE,TRAN,HOTPLUG,RM,MOUNTPOINTS",
                ],
                CommandResult(returncode=0, stdout=_lsblk_payload(), stderr=""),
            ),
            (
                ["findmnt", "--json", "-S", "/dev/sda1", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"],
                CommandResult(returncode=1, stdout='{"filesystems":[]}', stderr=""),
            ),
            (
                [
                    "lsblk",
                    "--json",
                    "-o",
                    "PATH,KNAME,PKNAME,LABEL,UUID,FSTYPE,TRAN,HOTPLUG,RM,MOUNTPOINTS",
                ],
                CommandResult(returncode=0, stdout=_lsblk_payload(), stderr=""),
            ),
            (
                ["findmnt", "--json", "-S", "/dev/sda1", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"],
                CommandResult(returncode=1, stdout='{"filesystems":[]}', stderr=""),
            ),
            (
                ["udisksctl", "mount", "-b", "/dev/sda1"],
                CommandResult(returncode=0, stdout="Mounted /dev/sda1", stderr=""),
            ),
            (
                ["findmnt", "--json", "-S", "/dev/sda1", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"],
                CommandResult(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "filesystems": [
                                {
                                    "target": str(mountpoint),
                                    "source": "/dev/sda1",
                                    "fstype": "vfat",
                                    "options": "rw,nosuid,nodev",
                                }
                            ]
                        }
                    ),
                    stderr="",
                ),
            ),
        ]
    )
    backend = HostUsbBackend(UsbConfig(expected_label="ENDLESS"), runner=runner)
    patch = PatchRecord(
        rel_path="effects/builds/phase_90.endl",
        abs_path=source,
        filename=source.name,
        display_name="Phase 90",
        source_family="custom_sdk",
    )

    outcome = backend.deploy(patch)

    assert (mountpoint / "phase_90.endl").read_bytes() == b"patch-bytes"
    assert outcome.verified is True
    assert outcome.destination == mountpoint / "phase_90.endl"
