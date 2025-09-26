from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agent.apps.registry import WindowRecord
from agent.runner.steps import RecipeRunner
from agent.schemas.config import StateSchema
from agent.state.store import StateStore

RECIPES_DIR = Path("agent/examples/recipes")


def _build_runner(apps: object) -> RecipeRunner:
    state_schema = StateSchema(
        accounts={"main": {"cash_free": 100_000.0}},
        market={"session": "open"},
    )
    store = StateStore(state_schema)
    return RecipeRunner(apps=apps, state=store, allow_focus_tap=False)


@dataclass
class _FakeRecord:
    definition: SimpleNamespace
    process: SimpleNamespace | None
    preset: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_focused_at: datetime | None = None
    instance_id: str = field(default_factory=lambda: uuid4().hex)
    pid: int | None = None
    windows: dict[int, WindowRecord] = field(default_factory=dict)

    def has_live_process(self) -> bool:
        return True


class FakeRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []
        self._pid = 4000
        self._instances: dict[str, list[_FakeRecord]] = {}

    def _new_record(self, name: str) -> _FakeRecord:
        self._pid += 1
        window = WindowRecord(
            hwnd=100 + self._pid,
            title=f"{name.title()} Window",
            class_name="DemoClass",
            bounds=(0, 0, 100, 100),
            is_visible=True,
            is_minimized=False,
            process_name="demo.exe",
            pid=self._pid,
            last_seen=datetime.now(timezone.utc),
        )
        record = _FakeRecord(
            definition=SimpleNamespace(name=name),
            process=SimpleNamespace(pid=self._pid),
            pid=self._pid,
            windows={window.hwnd: window},
        )
        self._instances.setdefault(name, []).append(record)
        return record

    def _select(self, name: str, target: object) -> _FakeRecord:
        records = self._instances.get(name, [])
        if not records:
            raise RuntimeError(f"No records for {name}")
        if target in ("latest", None):
            return records[-1]
        if target == "first":
            return records[0]
        if isinstance(target, str):
            for record in records:
                if record.instance_id == target:
                    return record
        return records[-1]

    def _log(self, action: str, name: str, target: object) -> None:
        self.calls.append((action, name, target))

    def start(self, name: str, **_: object) -> _FakeRecord:
        record = self._new_record(name)
        self._log("start", name, None)
        return record

    def focus(self, name: str, *, target: object = "latest") -> _FakeRecord:
        record = self._select(name, target)
        record.last_focused_at = datetime.now(timezone.utc)
        self._log("focus", name, target)
        return record

    def minimize(self, name: str, *, target: object = "latest") -> _FakeRecord:
        record = self._select(name, target)
        self._log("minimize", name, target)
        return record

    def maximize(self, name: str, *, target: object = "latest") -> _FakeRecord:
        record = self._select(name, target)
        self._log("maximize", name, target)
        return record

    def restore(self, name: str, *, target: object = "latest") -> _FakeRecord:
        record = self._select(name, target)
        self._log("restore", name, target)
        return record

    def close(self, name: str, *, all_instances: bool = False, **_: object) -> list[_FakeRecord]:
        records = list(self._instances.get(name, []))
        if not records:
            raise RuntimeError("no records")
        if all_instances:
            self._instances[name] = []
            self._log("close", name, "all")
            return records
        record = records[-1]
        self._instances[name] = records[:-1]
        self._log("close", name, "latest")
        return [record]

    def kill(self, name: str, *, all_instances: bool = False, **_: object) -> list[_FakeRecord]:
        records = list(self._instances.get(name, []))
        if not records:
            raise RuntimeError("no records")
        if all_instances:
            self._instances[name] = []
            self._log("kill", name, "all")
            return records
        record = records[-1]
        self._instances[name] = records[:-1]
        self._log("kill", name, "latest")
        return [record]

    def running_processes(self, name: str) -> list[_FakeRecord]:
        return list(self._instances.get(name, []))


@pytest.mark.parametrize(
    "recipe, expected_action",
    [
        ("browser.open_home.yml", "start"),
        ("browser.focus.yml", "focus"),
        ("browser.refresh_quotes.yml", "focus"),
        ("browser.close.yml", "close"),
        ("browser.force_kill.yml", "kill"),
        ("browser.minimize.yml", "minimize"),
        ("browser.restore.yml", "restore"),
        ("browser.maximize.yml", "maximize"),
    ],
)
def test_browser_recipes_invoke_expected_registry_method(recipe: str, expected_action: str) -> None:
    registry = FakeRegistry()
    runner = _build_runner(registry)

    if recipe != "browser.open_home.yml":
        runner.run_recipe(RECIPES_DIR / "browser.open_home.yml", context={})
        registry.calls.clear()

    runner.run_recipe(RECIPES_DIR / recipe, context={})

    actions = [call[0] for call in registry.calls]
    assert expected_action in actions


def test_focus_and_minimize_recipe_uses_tracked_instance() -> None:
    registry = FakeRegistry()
    runner = _build_runner(registry)

    runner.run_recipe(RECIPES_DIR / "browser.open_home.yml", context={})
    instance_id = runner._state.latest_instance_for("browser")
    assert instance_id

    runner.run_recipe(RECIPES_DIR / "browser.focus_and_minimize.yml", context={})

    focus_call = next(call for call in registry.calls if call[0] == "focus" and call[1] == "browser")
    minimize_call = next(call for call in registry.calls if call[0] == "minimize")
    assert focus_call[2] in (instance_id, "latest")
    assert minimize_call[2] in (instance_id, "latest")


def test_latest_instance_fallback_when_no_payload_target() -> None:
    registry = FakeRegistry()
    runner = _build_runner(registry)
    runner.run_recipe(RECIPES_DIR / "browser.open_home.yml", context={})
    instance_id = runner._state.latest_instance_for("browser")
    assert instance_id

    runner.run_recipe(RECIPES_DIR / "browser.minimize.yml", context={})

    minimize_call = next(call for call in registry.calls if call[0] == "minimize")
    assert minimize_call[2] in (instance_id, "latest")
