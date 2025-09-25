"""Target lock overlay implementation (platform-aware stub)."""
from __future__ import annotations

import logging
import platform
import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Deque, Dict, Iterable, Optional

try:  # pragma: no cover - optional dependency on non-Windows hosts
    import keyboard  # type: ignore
except Exception:  # pragma: no cover - optional dependency on non-Windows hosts
    keyboard = None

try:  # pragma: no cover - optional dependency
    import pyperclip
except Exception:  # pragma: no cover - optional dependency
    pyperclip = None

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


class OverlayAction(StrEnum):
    """Enumeration of overlay actions to allow consistent event bindings."""

    TOGGLE = "toggle"
    FREEZE = "freeze"
    COPY_SELECTOR = "copy_selector"
    DRY_RUN_INVOKE = "dry_run_invoke"
    CANCEL = "cancel"
    PREVIEW_CHANGED = "preview_changed"


Callback = Callable[["TargetOverlay", Optional[SelectorPreview]], None]


def _default_clipboard_writer(text: str) -> None:
    """Write to the clipboard if pyperclip is available."""

    if pyperclip is None:
        raise RuntimeError("pyperclip is not available to copy selectors to the clipboard.")
    pyperclip.copy(text)


class TargetOverlay:
    """Platform-aware overlay that exposes the requested controls and events."""

    DEFAULT_HOTKEYS: Dict[str, OverlayAction] = {
        "ctrl+alt+.": OverlayAction.TOGGLE,
        "ctrl+shift+.": OverlayAction.FREEZE,
        "enter": OverlayAction.COPY_SELECTOR,
        "space": OverlayAction.DRY_RUN_INVOKE,
        "esc": OverlayAction.CANCEL,
    }

    def __init__(
        self,
        *,
        keyboard_module=None,
        clipboard_writer: Optional[Callable[[str], None]] = None,
        history_size: int = 10,
    ) -> None:
        if not SUPPORTED_PLATFORM:
            LOGGER.warning("Target overlay is currently a no-op on non-Windows hosts.")
        self._keyboard = keyboard_module or keyboard
        self._clipboard_writer = clipboard_writer or _default_clipboard_writer
        self._active = False
        self._frozen = False
        self._last_selector: Optional[SelectorPreview] = None
        self._selector_history: Deque[SelectorPreview] = deque(maxlen=max(1, history_size))
        self._callbacks: Dict[OverlayAction, list[Callback]] = defaultdict(list)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Activate the overlay and register all configured hotkeys."""

        if not SUPPORTED_PLATFORM:
            raise OverlayNotSupported("Overlay features require Windows UI Automation APIs.")
        if self._keyboard is None:
            raise OverlayNotSupported("keyboard module is required for overlay hotkeys.")
        with self._lock:
            if self._active:
                return
            self._register_hotkeys()
            self._active = True
        LOGGER.info("Target overlay activated (Ctrl+Alt+. to toggle).")

    def stop(self) -> None:
        """Deactivate the overlay and remove registered hotkeys."""

        with self._lock:
            if not self._active:
                return
            if self._keyboard:
                self._keyboard.unhook_all_hotkeys()
            self._active = False
        LOGGER.info("Target overlay stopped.")

    # ------------------------------------------------------------------
    # Hotkey registration
    # ------------------------------------------------------------------
    def _register_hotkeys(self) -> None:
        assert self._keyboard is not None
        for combo, action in self.DEFAULT_HOTKEYS.items():
            self._keyboard.add_hotkey(combo, self._make_hotkey_handler(action))

    def _make_hotkey_handler(self, action: OverlayAction) -> Callable[[], None]:
        def handler() -> None:
            self._trigger_action(action)

        return handler

    # ------------------------------------------------------------------
    # Action handling
    # ------------------------------------------------------------------
    def bind(self, action: OverlayAction, callback: Callback) -> None:
        """Bind a callback to a specific overlay action."""

        with self._lock:
            self._callbacks[action].append(callback)

    def unbind(self, action: OverlayAction, callback: Optional[Callback] = None) -> None:
        """Remove a callback binding for an action."""

        with self._lock:
            callbacks = self._callbacks.get(action)
            if not callbacks:
                return
            if callback is None:
                callbacks.clear()
                return
            try:
                callbacks.remove(callback)
            except ValueError:
                LOGGER.debug("Callback not found for action %s", action)

    def _trigger_action(self, action: OverlayAction) -> None:
        actions = {
            OverlayAction.TOGGLE: self.toggle,
            OverlayAction.FREEZE: self.freeze,
            OverlayAction.COPY_SELECTOR: self.copy_selector,
            OverlayAction.DRY_RUN_INVOKE: self.dry_run_invoke,
            OverlayAction.CANCEL: self.cancel,
        }
        handler = actions.get(action)
        if handler:
            handler()

    def _notify(self, action: OverlayAction, selector: Optional[SelectorPreview]) -> None:
        for callback in list(self._callbacks.get(action, [])):
            try:
                callback(self, selector)
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("Overlay callback failed for action %s", action)

    # ------------------------------------------------------------------
    # Public controls
    # ------------------------------------------------------------------
    def toggle(self) -> None:
        with self._lock:
            self._frozen = False
            selector = self._last_selector
        LOGGER.info("Overlay toggled. Frozen set to %s", self._frozen)
        self._notify(OverlayAction.TOGGLE, selector)

    def freeze(self) -> None:
        with self._lock:
            self._frozen = True
            selector = self._last_selector
        LOGGER.info("Overlay frozen for selector capture.")
        self._notify(OverlayAction.FREEZE, selector)

    def copy_selector(self) -> None:
        with self._lock:
            selector = self._last_selector
        if not selector:
            LOGGER.info("No selector captured yet.")
            return
        selector_text = self._format_selector(selector)
        try:
            self._clipboard_writer(selector_text)
            LOGGER.info("Selector copied: %s", selector_text)
        except Exception as exc:  # pragma: no cover - clipboard failures are environment-specific
            LOGGER.warning("Failed to copy selector: %s", exc)
        self._notify(OverlayAction.COPY_SELECTOR, selector)

    def dry_run_invoke(self) -> None:
        with self._lock:
            selector = self._last_selector
        LOGGER.info("Dry-run invoke triggered for last selector.")
        self._notify(OverlayAction.DRY_RUN_INVOKE, selector)

    def cancel(self) -> None:
        LOGGER.info("Overlay cancelled by user.")
        self._notify(OverlayAction.CANCEL, self._last_selector)
        self.stop()

    def set_preview(self, selector: SelectorPreview) -> None:
        with self._lock:
            if self._frozen:
                LOGGER.debug("Preview update ignored while frozen: %s", selector)
                return
            self._last_selector = selector
            self._selector_history.append(selector)
        LOGGER.debug("Preview updated: %s", selector)
        self._notify(OverlayAction.PREVIEW_CHANGED, selector)

    # ------------------------------------------------------------------
    # Helpers and accessors
    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return self._active

    @property
    def frozen(self) -> bool:
        return self._frozen

    @property
    def last_selector(self) -> Optional[SelectorPreview]:
        return self._last_selector

    def iter_history(self) -> Iterable[SelectorPreview]:
        with self._lock:
            return tuple(self._selector_history)

    @staticmethod
    def _format_selector(selector: SelectorPreview) -> str:
        parts = [selector.name or "<unknown>"]
        if selector.control_type:
            parts.append(f"[{selector.control_type}]")
        if selector.automation_id:
            parts.append(f"#{selector.automation_id}")
        if selector.ancestry:
            parts.append(" -> ".join(selector.ancestry))
        return " ".join(parts)


__all__ = [
    "TargetOverlay",
    "SelectorPreview",
    "OverlayNotSupported",
    "OverlayAction",
]
