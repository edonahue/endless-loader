"""LCD helpers and optional I2C display adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

from endless_loader.config import LcdConfig
from endless_loader.models import KnobMetadata, LCD_WIDTH, PatchRecord

try:
    from smbus2 import SMBus  # type: ignore
except ImportError:  # pragma: no cover - exercised indirectly in tests
    SMBus = None


LCD_CHR = 1
LCD_CMD = 0
LCD_LINE_1 = 0x80
LCD_LINE_2 = 0xC0
ENABLE = 0b00000100
BACKLIGHT = 0b00001000


def truncate_lcd_text(text: str, width: int = LCD_WIDTH) -> str:
    return (text or "")[:width].ljust(width)


def build_knob_line(knobs: tuple[KnobMetadata, ...], width: int = LCD_WIDTH) -> str:
    labels: list[str] = []
    for index in range(3):
        if index < len(knobs):
            knob = knobs[index]
            labels.append((knob.lcd_label if knob.active else "----")[:4].ljust(4, "-"))
        else:
            labels.append("----")
    return "/".join(labels)[:width].ljust(width)


def build_patch_lines(patch: PatchRecord) -> tuple[str, str]:
    return truncate_lcd_text(patch.display_name), build_knob_line(patch.knobs)


class DisplayAdapter:
    def show_lines(self, line_1: str, line_2: str) -> None:
        raise NotImplementedError

    def show_loading(self, patch: PatchRecord) -> None:
        self.show_lines(truncate_lcd_text(patch.display_name), build_knob_line(patch.knobs))

    def show_ready(self, patch: PatchRecord) -> None:
        self.show_lines(*build_patch_lines(patch))

    def show_error(self, message: str) -> None:
        self.show_lines("Load Error".ljust(LCD_WIDTH), truncate_lcd_text(message))


@dataclass
class NullDisplayAdapter(DisplayAdapter):
    last_lines: tuple[str, str] = (" " * LCD_WIDTH, " " * LCD_WIDTH)

    def show_lines(self, line_1: str, line_2: str) -> None:
        self.last_lines = (truncate_lcd_text(line_1), truncate_lcd_text(line_2))


class Hd44780I2cDisplayAdapter(DisplayAdapter):
    """Simple HD44780 1602 driver for common PCF8574 backpacks."""

    def __init__(self, *, bus: int, address: int):
        if SMBus is None:
            raise RuntimeError("smbus2 is not available.")
        self._bus = SMBus(bus)
        self._address = address
        self._initialize()

    def show_lines(self, line_1: str, line_2: str) -> None:
        self._send_string(truncate_lcd_text(line_1), LCD_LINE_1)
        self._send_string(truncate_lcd_text(line_2), LCD_LINE_2)

    def _initialize(self) -> None:
        for command in (0x33, 0x32, 0x06, 0x0C, 0x28, 0x01):
            self._send(command, LCD_CMD)
            time.sleep(0.005)

    def _send_string(self, message: str, line: int) -> None:
        self._send(line, LCD_CMD)
        for char in message:
            self._send(ord(char), LCD_CHR)

    def _send(self, data: int, mode: int) -> None:
        high = mode | (data & 0xF0) | BACKLIGHT
        low = mode | ((data << 4) & 0xF0) | BACKLIGHT
        self._write_with_enable(high)
        self._write_with_enable(low)

    def _write_with_enable(self, value: int) -> None:
        self._bus.write_byte(self._address, value)
        time.sleep(0.0005)
        self._bus.write_byte(self._address, value | ENABLE)
        time.sleep(0.0005)
        self._bus.write_byte(self._address, value & ~ENABLE)
        time.sleep(0.0005)


def build_display_adapter(config: LcdConfig) -> DisplayAdapter:
    if not config.enabled:
        return NullDisplayAdapter()

    device = Path(f"/dev/i2c-{config.bus}")
    if not device.exists():
        return NullDisplayAdapter()

    try:
        return Hd44780I2cDisplayAdapter(bus=config.bus, address=config.address)
    except Exception:
        return NullDisplayAdapter()
