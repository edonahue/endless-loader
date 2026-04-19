"""Small JSON state store."""

from __future__ import annotations

import json
from pathlib import Path

from endless_loader.models import RuntimeState


class StateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> RuntimeState:
        if not self.path.exists():
            return RuntimeState.empty()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return RuntimeState.empty()
        return RuntimeState(
            current_patch_rel_path=payload.get("current_patch_rel_path"),
            current_display_name=payload.get("current_display_name"),
            deployed_at=payload.get("deployed_at"),
            last_status=payload.get("last_status"),
            last_message=payload.get("last_message"),
        )

    def save(self, state: RuntimeState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(state.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
