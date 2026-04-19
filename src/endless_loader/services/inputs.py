"""Future GPIO input placeholders."""

from __future__ import annotations

from collections.abc import Callable


class InputAdapter:
    def __init__(self) -> None:
        self._handlers: list[Callable[[str], None]] = []

    def register_handler(self, handler: Callable[[str], None]) -> None:
        self._handlers.append(handler)

    def emit(self, event_name: str) -> None:
        for handler in list(self._handlers):
            handler(event_name)


class NullInputAdapter(InputAdapter):
    """Placeholder adapter until GPIO controls are added."""

