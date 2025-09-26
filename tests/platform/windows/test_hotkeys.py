"""Tests for Windows hotkey utilities."""
from __future__ import annotations

import threading

import pytest

from agent.platform.windows.hotkeys import GlobalHotKeyListener, parse_hotkey

WM_HOTKEY = 0x0312


def test_parse_hotkey_ctrl_alt_shift_esc() -> None:
    modifiers, key_code = parse_hotkey("ctrl+alt+shift+esc")
    assert modifiers == (0x0002 | 0x0001 | 0x0004)
    assert key_code == 0x1B


def test_parse_hotkey_rejects_multiple_keys() -> None:
    with pytest.raises(ValueError):
        parse_hotkey("ctrl+a+b")


class _StubUser32:
    def __init__(self) -> None:
        self.registered: list[tuple[int, int, int]] = []
        self.unregistered: list[tuple[object | None, int]] = []
        self._messages: list[tuple[int, int, int]] = []
        self._lock = threading.Lock()
        self._event = threading.Event()

    def RegisterHotKey(self, hwnd, identifier, modifiers, vk) -> int:  # noqa: N802
        self.registered.append((identifier, modifiers, vk))
        return 1

    def UnregisterHotKey(self, hwnd, identifier) -> int:  # noqa: N802
        self.unregistered.append((hwnd, identifier))
        return 1

    def PostThreadMessageW(self, thread_id: int, message: int, wparam: int, lparam: int) -> int:
        self._enqueue((0, message, wparam))
        return 1

    def enqueue_hotkey(self, identifier: int) -> None:
        self._enqueue((1, WM_HOTKEY, identifier))

    def _enqueue(self, payload: tuple[int, int, int]) -> None:
        with self._lock:
            self._messages.append(payload)
            self._event.set()

    def GetMessageW(self, msg_ptr, hwnd, min_msg, max_msg) -> int:  # noqa: N802
        if not self._event.wait(timeout=0.5):
            return 0
        with self._lock:
            result, message, wparam = self._messages.pop(0)
            if not self._messages:
                self._event.clear()
        target = getattr(msg_ptr, "contents", None)
        if target is None:
            target = msg_ptr._obj
        target.message = message
        target.wParam = wparam
        return result


class _StubKernel32:
    def GetCurrentThreadId(self) -> int:  # noqa: N802
        return 1234


def test_hotkey_listener_invokes_callback() -> None:
    user32 = _StubUser32()
    kernel32 = _StubKernel32()
    triggered = threading.Event()

    def _callback() -> None:
        triggered.set()

    listener = GlobalHotKeyListener(
        "ctrl+esc",
        _callback,
        user32_module=user32,
        kernel32_module=kernel32,
    )

    try:
        listener.start()
        user32.enqueue_hotkey(listener._id)
        assert triggered.wait(timeout=1.0), "hotkey callback not invoked"
    finally:
        listener.stop()

    assert user32.registered, "hotkey was not registered"
    assert user32.unregistered, "hotkey was not unregistered"



