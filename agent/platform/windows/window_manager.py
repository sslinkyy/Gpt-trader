"""Win32 window management helpers."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import time
from dataclasses import dataclass
from typing import Iterable, Optional

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

def _rect_to_tuple(rect: wintypes.RECT) -> tuple[int, int, int, int]:
    return rect.left, rect.top, rect.right, rect.bottom

SW_RESTORE = 9
SW_MINIMIZE = 6
SW_SHOWMAXIMIZED = 3
WM_CLOSE = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_TERMINATE = 0x0001


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    pid: int
    bounds: tuple[int, int, int, int]
    is_visible: bool
    is_minimized: bool


@dataclass
class WindowSnapshot(WindowInfo):
    process_name: str
    last_seen: float


def _get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value.strip()


def _get_class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value.strip()


def _get_process_name(pid: int) -> str:
    process = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not process:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(len(buffer))
        if psapi.GetModuleBaseNameW(process, None, buffer, size):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(process)


def _get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return _rect_to_tuple(rect)
    return (0, 0, 0, 0)


def _is_iconic(hwnd: int) -> bool:
    return bool(user32.IsIconic(hwnd))


def enumerate_windows() -> Iterable[WindowInfo]:
    results: list[WindowInfo] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> bool:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        info = WindowInfo(
            hwnd=hwnd,
            title=_get_window_text(hwnd),
            class_name=_get_class_name(hwnd),
            pid=pid.value,
            bounds=_get_window_rect(hwnd),
            is_visible=bool(user32.IsWindowVisible(hwnd)),
            is_minimized=_is_iconic(hwnd),
        )
        results.append(info)
        return True

    user32.EnumWindows(callback, 0)
    return results


def _matches(
    info: WindowInfo,
    *,
    title_match: str | None,
    class_match: str | None,
    process_name: str | None,
    pid: int | None,
    require_visible: bool,
) -> bool:
    if pid is not None and info.pid != pid:
        return False
    if require_visible and not info.is_visible:
        return False
    if title_match and title_match.lower() not in info.title.lower():
        return False
    if class_match and info.class_name.lower() != class_match.lower():
        return False
    if process_name and _get_process_name(info.pid).lower() != process_name.lower():
        return False
    return True


def _find_candidates(
    definition,
    pid: int | None,
    *,
    require_visible: bool,
    include_hidden: bool,
) -> list[WindowInfo]:
    title_match = getattr(definition.config.window, "title_match", None)
    class_match = getattr(definition.config.window, "class_match", None)
    process_name = getattr(definition.config.window, "process_name", None)

    candidates = [
        info
        for info in enumerate_windows()
        if _matches(
            info,
            title_match=title_match or None,
            class_match=class_match or None,
            process_name=process_name or None,
            pid=pid,
            require_visible=require_visible,
        )
    ]
    if not candidates and pid is not None and include_hidden:
        candidates = [
            info
            for info in enumerate_windows()
            if _matches(
                info,
                title_match=title_match or None,
                class_match=class_match or None,
                process_name=process_name or None,
                pid=None,
                require_visible=require_visible,
            )
        ]
    return candidates


def find_window(definition, pid: int | None = None, *, require_visible: bool = True) -> Optional[WindowInfo]:
    candidates = _find_candidates(definition, pid, require_visible=require_visible, include_hidden=True)
    return candidates[0] if candidates else None


def wait_for_window(
    definition,
    pid: int | None = None,
    *,
    timeout: float = 5.0,
    interval: float = 0.2,
    require_visible: bool = True,
) -> Optional[WindowInfo]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = find_window(definition, pid=pid, require_visible=require_visible)
        if info:
            return info
        time.sleep(interval)
    return None


def snapshot_windows(definition) -> list[WindowSnapshot]:
    matches = _find_candidates(
        definition,
        pid=None,
        require_visible=False,
        include_hidden=True,
    )
    snapshots = [
        WindowSnapshot(
            hwnd=info.hwnd,
            title=info.title,
            class_name=info.class_name,
            pid=info.pid,
            bounds=info.bounds,
            is_visible=info.is_visible,
            is_minimized=info.is_minimized,
            process_name=_get_process_name(info.pid),
            last_seen=time.time(),
        )
        for info in matches
    ]
    return snapshots


def is_window(hwnd: int | None) -> bool:
    if not hwnd:
        return False
    return bool(user32.IsWindow(hwnd))


def bring_to_foreground(hwnd: int) -> bool:
    if not is_window(hwnd):
        return False
    user32.ShowWindow(hwnd, SW_RESTORE)
    return bool(user32.SetForegroundWindow(hwnd))


def show_window(hwnd: int, command: str) -> bool:
    mapping = {
        "restore": SW_RESTORE,
        "minimize": SW_MINIMIZE,
        "maximize": SW_SHOWMAXIMIZED,
    }
    cmd = mapping.get(command.lower())
    if cmd is None:
        raise ValueError(f"Unsupported show command '{command}'")
    if not is_window(hwnd):
        return False
    return bool(user32.ShowWindow(hwnd, cmd))


def close_window(hwnd: int) -> bool:
    if not is_window(hwnd):
        return False
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    return True


def terminate_process(pid: int) -> bool:
    if not pid:
        return False
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        return bool(kernel32.TerminateProcess(handle, 1))
    finally:
        kernel32.CloseHandle(handle)


__all__ = [
    "WindowInfo",
    "WindowSnapshot",
    "wait_for_window",
    "find_window",
    "snapshot_windows",
    "is_window",
    "bring_to_foreground",
    "show_window",
    "close_window",
    "terminate_process",
]
