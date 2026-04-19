"""Patch library scanning and grouping."""

from __future__ import annotations

from pathlib import Path
import threading

from endless_loader.models import (
    PatchGroup,
    PatchRecord,
    KnobMetadata,
    SOURCE_LABELS,
    SOURCE_ORDER,
    compact_lcd_label,
    humanize_stem,
)
from endless_loader.services.companion import CompanionMetadataProvider


class LibraryCatalog:
    """Keep a cached view of the patch library."""

    def __init__(self, library_root: Path, companion: CompanionMetadataProvider):
        self.library_root = library_root
        self.companion = companion
        self._lock = threading.RLock()
        self._patches: list[PatchRecord] = []
        self._companion_source: str | None = None

    @property
    def companion_source(self) -> str | None:
        return self._companion_source

    @property
    def patches(self) -> tuple[PatchRecord, ...]:
        with self._lock:
            return tuple(self._patches)

    def reload(self) -> None:
        with self._lock:
            companion_index, companion_source = self.companion.load_entries()
            self._patches = scan_library(self.library_root, companion_index, companion_source)
            self._companion_source = companion_source

    def first(self) -> PatchRecord | None:
        with self._lock:
            return self._patches[0] if self._patches else None

    def find(self, rel_path: str | None) -> PatchRecord | None:
        if not rel_path:
            return None
        with self._lock:
            for patch in self._patches:
                if patch.rel_path == rel_path:
                    return patch
        return None

    def grouped(self, query: str = "") -> tuple[PatchGroup, ...]:
        query_lower = query.strip().lower()
        with self._lock:
            filtered = [
                patch
                for patch in self._patches
                if not query_lower
                or query_lower in patch.display_name.lower()
                or query_lower in patch.rel_path.lower()
                or query_lower in patch.source_label.lower()
            ]

        groups: list[PatchGroup] = []
        for family in SOURCE_ORDER:
            members = tuple(patch for patch in filtered if patch.source_family == family)
            if members:
                groups.append(PatchGroup(key=family, label=SOURCE_LABELS[family], patches=members))

        leftovers = tuple(
            patch for patch in filtered if patch.source_family not in SOURCE_ORDER
        )
        if leftovers:
            groups.append(PatchGroup(key="other", label="Other", patches=leftovers))
        return tuple(groups)


def scan_library(
    library_root: Path,
    companion_index: dict[str, dict[str, object]],
    companion_source: str | None,
) -> list[PatchRecord]:
    if not library_root.exists():
        return []

    records: list[PatchRecord] = []
    for path in sorted(library_root.rglob("*.endl"), key=lambda item: item.as_posix().lower()):
        rel_path = path.relative_to(library_root).as_posix()
        metadata = _lookup_metadata(path, rel_path, companion_index)
        source_family = _classify_source(rel_path, metadata)
        controls = metadata.get("controls") if metadata else None
        knobs = tuple(_build_knob(control) for control in controls) if controls else _default_knobs()
        record = PatchRecord(
            rel_path=rel_path,
            abs_path=path.resolve(),
            filename=path.name,
            display_name=str(metadata.get("display_name") if metadata else humanize_stem(path.stem)),
            source_family=source_family,
            description=str(metadata.get("description")) if metadata and metadata.get("description") else None,
            knobs=knobs,
            short_action=str(metadata.get("short_action")) if metadata and metadata.get("short_action") else None,
            long_action=str(metadata.get("long_action")) if metadata and metadata.get("long_action") else None,
            source_url=str(metadata.get("source_url")) if metadata and metadata.get("source_url") else None,
            doc_url=str(metadata.get("doc_url")) if metadata and metadata.get("doc_url") else None,
            metadata_source=companion_source,
        )
        records.append(record)
    return records


def _lookup_metadata(
    path: Path,
    rel_path: str,
    companion_index: dict[str, dict[str, object]],
) -> dict[str, object]:
    for key in (rel_path.lower(), path.name.lower(), path.stem.lower()):
        value = companion_index.get(key)
        if value:
            return value
    return {}


def _classify_source(rel_path: str, metadata: dict[str, object]) -> str:
    family = metadata.get("source_family")
    if isinstance(family, str) and family:
        return family

    lower = rel_path.lower()
    if "polyend_plates" in lower or "/plates/" in lower:
        return "official_plates"
    if "effects/builds" in lower or lower.startswith("effects/"):
        return "custom_sdk"
    return "local_library"


def _build_knob(control: dict[str, object]) -> KnobMetadata:
    active = bool(control.get("active", True))
    label = str(control.get("label", "Unused"))
    return KnobMetadata(
        slot=str(control.get("slot", "left")),
        label=label,
        description=str(
            control.get("description")
            or ("Not used in this patch." if not active else "No companion details yet.")
        ),
        lcd_label=str(control.get("lcd_label") or compact_lcd_label(label, active=active)),
        active=active,
        expression_note=str(control.get("expression_note")) if control.get("expression_note") else None,
    )


def _default_knobs() -> tuple[KnobMetadata, ...]:
    knobs = []
    for slot in ("left", "mid", "right"):
        label = slot.title()
        knobs.append(
            KnobMetadata(
                slot=slot,
                label=label,
                description="No companion metadata is available for this patch yet.",
                lcd_label=compact_lcd_label(label),
            )
        )
    return tuple(knobs)
