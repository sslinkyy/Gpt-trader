"""Tests for the application registry runtime behaviour."""
from __future__ import annotations

import sys
from typing import List

import pytest

from agent.apps.registry import ApplicationRegistry
from agent.platform.windows.window_manager import WindowSnapshot
from agent.schemas.config import AppRegistrySchema


class _StubWindowManager:
    def __init__(self) -> None:
        self._snapshots: dict[str, List[WindowSnapshot]] = {}
        self._next_handle = 100

    def snapshot_windows(self, definition) -> List[WindowSnapshot]:
        return list(self._snapshots.get(definition.name, []))

    def wait_for_window(self, definition, pid=None, *, timeout=5.0, interval=0.2):
        snapshot = WindowSnapshot(
            hwnd=self._next_handle,
            title=f"{definition.name.title()} Window",
            class_name="DemoClass",
            pid=pid or 0,
            bounds=(0, 0, 100, 100),
            is_visible=True,
            is_minimized=False,
            process_name="demo.exe",
            last_seen=0.0,
        )
        self._snapshots.setdefault(definition.name, []).append(snapshot)
        self._next_handle += 1
        return snapshot

    def find_window(self, definition, pid=None, require_visible=True):
        snapshots = self.snapshot_windows(definition)
        return snapshots[0] if snapshots else None

    def is_window(self, hwnd):
        return True

    def bring_to_foreground(self, hwnd):
        return True

    def show_window(self, hwnd, command):
        return True

    def close_window(self, hwnd):
        for name, snapshots in self._snapshots.items():
            self._snapshots[name] = [snap for snap in snapshots if snap.hwnd != hwnd]
        return True

    def terminate_process(self, pid):
        return True


def _registry(single_instance: str = "detect") -> ApplicationRegistry:
    config = {
        "demo": {
            "path": sys.executable,
            "args": [
                "-c",
                "import time; time.sleep(60)",
            ],
            "window": {"single_instance": single_instance},
        }
    }
    schema = AppRegistrySchema.from_dict(config)
    return ApplicationRegistry(schema.root, wm=_StubWindowManager())


def _cleanup(registry: ApplicationRegistry) -> None:
    if registry.is_running("demo"):
        try:
            registry.kill("demo", all_instances=True)
        except RuntimeError:
            pass


def test_start_focus_and_close_process() -> None:
    registry = _registry()
    try:
        record = registry.start("demo")
        assert registry.is_running("demo")
        assert record.instance_id

        focused = registry.focus("demo")
        assert focused.last_focused_at is not None
        assert focused.process.poll() is None

        registry.close("demo", timeout=1.0)
        assert not registry.is_running("demo")
    finally:
        _cleanup(registry)


def test_single_instance_detect_blocks_second_start() -> None:
    registry = _registry(single_instance="detect")
    try:
        registry.start("demo")
        with pytest.raises(RuntimeError):
            registry.start("demo")
    finally:
        _cleanup(registry)


def test_single_instance_force_restarts_process() -> None:
    registry = _registry(single_instance="force")
    try:
        first = registry.start("demo")
        pid_one = first.process.pid

        second = registry.start("demo")
        pid_two = second.process.pid

        assert pid_one != pid_two
        assert first.process.wait(timeout=5) is not None
    finally:
        _cleanup(registry)


def test_select_record_by_instance_id() -> None:
    registry = _registry(single_instance="detect")
    try:
        record = registry.start("demo")
        fetched = registry.focus("demo", target=record.instance_id)
        assert fetched.instance_id == record.instance_id
    finally:
        _cleanup(registry)
