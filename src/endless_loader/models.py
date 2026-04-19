"""Shared models and small formatting helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
import re

LCD_WIDTH = 16
SOURCE_LABELS = {
    "custom_sdk": "Custom SDK",
    "official_plates": "Official Plates",
    "local_library": "Local Library",
}
SOURCE_ORDER = ("custom_sdk", "official_plates", "local_library")


def compact_lcd_label(label: str, *, active: bool = True) -> str:
    """Return a stable 4-character LCD label."""

    if not active:
        return "----"

    clean = re.sub(r"[^A-Za-z0-9]+", "", label or "")
    if not clean:
        return "----"
    if len(clean) >= 4:
        return clean[:4].title()
    return clean.title().ljust(4, "-")


def humanize_stem(stem: str) -> str:
    """Turn a filename stem into a readable display name."""

    parts = [piece for piece in re.split(r"[_\-]+", stem) if piece]
    if not parts:
        return stem

    def _format_piece(piece: str) -> str:
        if piece.isupper():
            return piece
        if piece.lower() in {"fx", "wdf", "ts", "mxr"}:
            return piece.upper()
        return piece.capitalize()

    return " ".join(_format_piece(piece) for piece in parts)


@dataclass(frozen=True)
class KnobMetadata:
    slot: str
    label: str
    description: str
    lcd_label: str
    active: bool = True
    expression_note: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PatchRecord:
    rel_path: str
    abs_path: Path
    filename: str
    display_name: str
    source_family: str
    description: str | None = None
    knobs: tuple[KnobMetadata, ...] = field(default_factory=tuple)
    short_action: str | None = None
    long_action: str | None = None
    source_url: str | None = None
    doc_url: str | None = None
    metadata_source: str | None = None

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS.get(self.source_family, "Local Library")

    @property
    def active_knob_count(self) -> int:
        return sum(1 for knob in self.knobs if knob.active)

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.display_name.lower()).strip("-")


@dataclass(frozen=True)
class PatchGroup:
    key: str
    label: str
    patches: tuple[PatchRecord, ...]


@dataclass
class RuntimeState:
    current_patch_rel_path: str | None = None
    current_display_name: str | None = None
    deployed_at: str | None = None
    last_status: str | None = None
    last_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def empty(cls) -> "RuntimeState":
        return cls()

    @classmethod
    def loaded(
        cls,
        patch: PatchRecord,
        *,
        deployed_at: datetime,
        message: str,
    ) -> "RuntimeState":
        return cls(
            current_patch_rel_path=patch.rel_path,
            current_display_name=patch.display_name,
            deployed_at=deployed_at.isoformat(timespec="seconds"),
            last_status="success",
            last_message=message,
        )


@dataclass(frozen=True)
class DeploymentOutcome:
    deployed_at: datetime
    destination: Path
    message: str


@dataclass(frozen=True)
class MountStatus:
    ready: bool
    label: str
    detail: str

