"""Global hotkey helpers for Windows."""
from __future__ import annotations

import ctypes
import logging
import threading
from typing import Callable

import ctypes.wintypes as wintypes

LOGGER = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MODIFIER_MAP = {
    "alt": 0x0001,
    "control": 0x0002,
    "ctrl": 0x0002,
    "shift": 0x0004,
    "win": 0x0008,
    "windows": 0x0008,
    "logo": 0x0008,
}

KEY_ALIASES = {
    "escape": 0x1B,
    "esc": 0x1B,
    "space": 0x20,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
}


def _resolve_key(token: str) -> int:
    lower = token.lower()
    if lower in KEY_ALIASES:
        return KEY_ALIASES[lower]
    if lower.startswith("f") and lower[1:].isdigit():
        index = int(lower[1:])
        if 1 <= index <= 24:
            return 0x70 + (index - 1)
    if len(lower) == 1:
        ch = lower.upper()
        if "A" <= ch <= "Z" or "0" <= ch <= "9":
            return ord(ch)
    raise ValueError(f"Unsupported hotkey token '{token}'.")


def parse_hotkey(sequence: str) -> tuple[int, int]:
    if not sequence:
        raise ValueError("Hotkey sequence must be provided.")

    tokens = [token.strip() for token in sequence.split("+") if token.strip()]
    if not tokens:
        raise ValueError("Hotkey sequence must include at least one token.")

    modifiers = 0
    key_code: int | None = None

    for token in tokens:
        lower = token.lower()
        if lower in MODIFIER_MAP:
            modifiers |= MODIFIER_MAP[lower]
            continue
        if key_code is not None:
            raise ValueError("Hotkey sequence may only include one non-modifier key.")
        key_code = _resolve_key(token)

    if key_code is None:
        raise ValueError("Hotkey sequence must include a non-modifier key.")

    return modifiers, key_code


class GlobalHotKeyListener:
    """Register a global hotkey and invoke a callback when it fires."""

    _id_lock = threading.Lock()
    _next_id = 0x1FFF

    def __init__(
        self,
        sequence: str,
        callback: Callable[[], None],
        *,
        user32_module=user32,
        kernel32_module=kernel32,
    ) -> None:
        if not callable(callback):
            raise ValueError("Hotkey callback must be callable.")
        self._sequence = sequence
        self._callback = callback
        self._user32 = user32_module
        self._kernel32 = kernel32_module
        self._modifiers, self._vk = parse_hotkey(sequence)
        self._id = self._allocate_id()
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._registered = False
        self._error: Exception | None = None

    @classmethod
    def _allocate_id(cls) -> int:
        with cls._id_lock:
            cls._next_id += 1
            if cls._next_id >= 0xBFFF:
                cls._next_id = 0x2000
            return cls._next_id

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._ready_event.clear()
        self._error = None

        thread = threading.Thread(target=self._run_loop, name="global-hotkey-listener", daemon=True)
        thread.start()
        self._thread = thread

        if not self._ready_event.wait(timeout=2):
            self.stop()
            raise RuntimeError(f"Timed out registering hotkey '{self._sequence}'.")

        if self._error:
            error = self._error
            self.stop()
            raise error

    def stop(self) -> None:
        self._stop_event.set()
        thread_id = self._thread_id
        if thread_id:
            self._user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=1)
        self._thread = None
        self._thread_id = None
        self._registered = False

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run_loop(self) -> None:
        self._thread_id = self._kernel32.GetCurrentThreadId()
        ctypes.set_last_error(0)
        try:
            if not self._user32.RegisterHotKey(None, self._id, self._modifiers, self._vk):
                err = ctypes.get_last_error()
                self._error = RuntimeError(
                    f"RegisterHotKey failed for '{self._sequence}' (error {err})."
                )
                self._ready_event.set()
                return

            self._registered = True
            self._ready_event.set()

            msg = wintypes.MSG()
            while not self._stop_event.is_set():
                result = self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == 0 or self._stop_event.is_set():
                    break
                if result == -1:
                    LOGGER.warning(
                        "Hotkey listener GetMessageW failed (error %s)",
                        ctypes.get_last_error(),
                    )
                    break
                if msg.message == WM_HOTKEY and msg.wParam == self._id:
                    self._invoke_callback()
        finally:
            if self._registered:
                self._user32.UnregisterHotKey(None, self._id)
                self._registered = False
            self._thread_id = None
            if not self._ready_event.is_set():
                self._ready_event.set()

    def _invoke_callback(self) -> None:
        try:
            self._callback()
        except Exception:  # pragma: no cover - defensive logging
            LOGGER.exception("Hotkey callback raised an exception.")

    def __enter__(self) -> "GlobalHotKeyListener":
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()


__all__ = ["parse_hotkey", "GlobalHotKeyListener"]


