"""Target lock overlay implementation (platform-aware stub)."""
from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from typing import Optional

try:
    import keyboard  # type: ignore
except Exception:  # pragma: no cover - optional dependency on non-Windows hosts
    keyboard = None

LOGGER = logging.getLogger(__name__)

SUPPORTED_PLATFORM = platform.system() == "Windows"


@dataclass
class SelectorPreview:
    """Represents a selector captured by the overlay."""

    name: Optional[str]
    control_type: Optional[str]
    automation_id: Optional[str]
    ancestry: tuple[str, ...] = ()


class OverlayNotSupported(RuntimeError):
    """Raised when attempting to use the overlay on unsupported platforms."""


class TargetOverlay:
    """Minimal overlay that exposes the hotkeys specified in the design."""

    def __init__(self) -> None:
        if not SUPPORTED_PLATFORM:
            LOGGER.warning("Target overlay is currently a no-op on non-Windows hosts.")
        self._active = False
        self._frozen = False
        self._last_selector: Optional[SelectorPreview] = None

    def start(self) -> None:
        if not SUPPORTED_PLATFORM:
            raise OverlayNotSupported("Overlay features require Windows UI Automation APIs.")
        if keyboard is None:
            raise OverlayNotSupported("keyboard module is required for overlay hotkeys.")
        if self._active:
            return
        self._register_hotkeys()
        self._active = True
        LOGGER.info("Target overlay activated (Ctrl+Alt+. to toggle).")

    def stop(self) -> None:
        if not self._active:
            return
        if keyboard:
            keyboard.unhook_all_hotkeys()
        self._active = False
        LOGGER.info("Target overlay stopped.")

    def _register_hotkeys(self) -> None:
        assert keyboard is not None
        keyboard.add_hotkey("ctrl+alt+.", self.toggle)
        keyboard.add_hotkey("ctrl+shift+.", self.freeze)
        keyboard.add_hotkey("enter", self.copy_selector)
        keyboard.add_hotkey("space", self.dry_run_invoke)
        keyboard.add_hotkey("esc", self.cancel)

    def toggle(self) -> None:
        self._frozen = False
        LOGGER.info("Overlay toggled. Frozen set to %s", self._frozen)

    def freeze(self) -> None:
        self._frozen = True
        LOGGER.info("Overlay frozen for selector capture.")

    def copy_selector(self) -> None:
        if not self._last_selector:
            LOGGER.info("No selector captured yet.")
            return
        LOGGER.info("Selector copied: %s", self._last_selector)

    def dry_run_invoke(self) -> None:
        LOGGER.info("Dry-run invoke triggered for last selector.")

    def cancel(self) -> None:
        LOGGER.info("Overlay cancelled by user.")
        self.stop()

    def set_preview(self, selector: SelectorPreview) -> None:
        self._last_selector = selector
        LOGGER.debug("Preview updated: %s", selector)


__all__ = ["TargetOverlay", "SelectorPreview", "OverlayNotSupported"]
