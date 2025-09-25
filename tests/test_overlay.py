"""Tests for the TargetOverlay controls and helper APIs."""
from __future__ import annotations

from collections import deque
from typing import Optional

import pytest

from agent.ui.overlay import OverlayAction, SelectorPreview, TargetOverlay


def build_selector(name: str = "Button") -> SelectorPreview:
    return SelectorPreview(
        name=name,
        control_type="Button",
        automation_id="ok",
        ancestry=("Window", "Dialog"),
    )


def test_set_preview_respects_freeze() -> None:
    overlay = TargetOverlay(keyboard_module=None, clipboard_writer=lambda _: None)
    overlay.set_preview(build_selector("First"))
    overlay.freeze()
    overlay.set_preview(build_selector("Second"))

    history = overlay.iter_history()
    assert len(history) == 1
    assert history[0].name == "First"
    assert overlay.last_selector is not None
    assert overlay.last_selector.name == "First"


def test_bind_and_notify_actions() -> None:
    overlay = TargetOverlay(keyboard_module=None, clipboard_writer=lambda _: None)
    triggered: deque[OverlayAction] = deque()

    def recorder(_, __):
        triggered.append(OverlayAction.TOGGLE)

    overlay.bind(OverlayAction.TOGGLE, recorder)
    overlay.toggle()

    assert list(triggered) == [OverlayAction.TOGGLE]


def test_copy_selector_uses_formatter() -> None:
    captured: Optional[str] = None

    def writer(value: str) -> None:
        nonlocal captured
        captured = value

    overlay = TargetOverlay(keyboard_module=None, clipboard_writer=writer)
    overlay.set_preview(build_selector("CopyTarget"))
    overlay.copy_selector()

    assert captured is not None
    assert "CopyTarget" in captured
    assert "Button" in captured
    assert "ok" in captured


def test_iter_history_returns_copy() -> None:
    overlay = TargetOverlay(keyboard_module=None, clipboard_writer=lambda _: None)
    overlay.set_preview(build_selector("Alpha"))
    overlay.set_preview(build_selector("Beta"))
    history = overlay.iter_history()

    assert len(history) == 2
    assert history[0].name == "Alpha"
    assert history[1].name == "Beta"

    with pytest.raises(AttributeError):
        history.append  # type: ignore[attr-defined]
