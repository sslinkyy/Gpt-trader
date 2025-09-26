from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_browser_recipes import FakeRegistry, _build_runner, RECIPES_DIR


@pytest.mark.parametrize(
    "recipe_name", [
        "app.launch.yml",
        "app.focus.yml",
        "app.minimize.yml",
        "app.maximize.yml",
        "app.restore.yml",
        "app.close.yml",
        "app.kill.yml",
    ],
)
def test_app_recipes_accept_dynamic_context(recipe_name: str) -> None:
    registry = FakeRegistry()
    runner = _build_runner(registry)
    context: dict[str, object] = {"name": "demo-app"}

    # Ensure an instance exists for follow-up actions
    runner.run_recipe(RECIPES_DIR / "app.launch.yml", context=context)
    assert any(call[0] == "start" for call in registry.calls)

    if recipe_name != "app.launch.yml":
        registry.calls.clear()
        runner.run_recipe(RECIPES_DIR / recipe_name, context=context)

    expected_action = {
        "app.launch.yml": "start",
        "app.focus.yml": "focus",
        "app.minimize.yml": "minimize",
        "app.maximize.yml": "maximize",
        "app.restore.yml": "restore",
        "app.close.yml": "close",
        "app.kill.yml": "kill",
    }[recipe_name]

    actions = [call[0] for call in registry.calls]
    assert expected_action in actions
