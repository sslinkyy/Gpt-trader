"""UI automation engine implementing the method:auto resolution order."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

LOGGER = logging.getLogger(__name__)


class ClickMethod(str, Enum):
    """Enumeration of supported UI interaction strategies."""

    INVOKE = "invoke"
    TOGGLE = "toggle"
    SELECTION = "selection_item"
    MSAA = "msaa"
    BM_CLICK = "bm_click"
    FOCUS_TAP = "focus_tap"


@dataclass
class UIElementHandle:
    """Thin abstraction around UI elements to facilitate testing."""

    identifier: str
    is_enabled: bool = True

    def invoke(self) -> bool:
        LOGGER.debug("Invoking element %s via UIA Invoke pattern", self.identifier)
        return True

    def toggle(self) -> bool:
        LOGGER.debug("Toggling element %s via UIA Toggle pattern", self.identifier)
        return True

    def select(self) -> bool:
        LOGGER.debug("Selecting element %s via UIA SelectionItem pattern", self.identifier)
        return True

    def msaa_default_action(self) -> bool:
        LOGGER.debug("Executing MSAA default action for %s", self.identifier)
        return True

    def send_bm_click(self) -> bool:
        LOGGER.debug("Sending BM_CLICK message to %s", self.identifier)
        return True

    def focus_tap(self) -> bool:
        LOGGER.debug("Performing focus-tap fallback for %s", self.identifier)
        return True


class UIClickEngine:
    """Resolve click methods based on guardrails and element state."""

    def __init__(self, allow_focus_tap: bool) -> None:
        self.allow_focus_tap = allow_focus_tap

    def click(self, element: UIElementHandle) -> ClickMethod:
        if not element.is_enabled:
            raise RuntimeError("Cannot interact with disabled element.")

        resolution_order: tuple[tuple[ClickMethod, Callable[[UIElementHandle], bool]], ...] = (
            (ClickMethod.INVOKE, UIElementHandle.invoke),
            (ClickMethod.TOGGLE, UIElementHandle.toggle),
            (ClickMethod.SELECTION, UIElementHandle.select),
            (ClickMethod.MSAA, UIElementHandle.msaa_default_action),
            (ClickMethod.BM_CLICK, UIElementHandle.send_bm_click),
        )

        for method, action in resolution_order:
            try:
                result = action(element)
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.debug("Method %s failed for %s: %s", method, element.identifier, exc)
                continue
            if result:
                LOGGER.info("UI click resolved using %s for %s", method, element.identifier)
                return method

        if self.allow_focus_tap:
            if element.focus_tap():
                LOGGER.info("UI click resolved using %s for %s", ClickMethod.FOCUS_TAP, element.identifier)
                return ClickMethod.FOCUS_TAP

        raise RuntimeError("Unable to resolve click method for element.")


__all__ = ["UIClickEngine", "UIElementHandle", "ClickMethod"]
