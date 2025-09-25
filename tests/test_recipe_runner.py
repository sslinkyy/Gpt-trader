"""Tests for recipe runner step handlers."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent.runner.steps import RecipeExecutionError, RecipeRunner
from agent.schemas.config import StateSchema
from agent.state.store import StateStore


def _build_runner(session: str = "open", cash: float = 100_000.0) -> RecipeRunner:
    state_schema = StateSchema(
        accounts={"main": {"cash_free": cash}},
        market={"session": session},
    )
    state_store = StateStore(state_schema)
    return RecipeRunner(apps=MagicMock(), state=state_store, allow_focus_tap=False)


def test_assert_expr_allows_state_access() -> None:
    runner = _build_runner(session="open")

    runner.step_assert_expr({"expr": "${STATE.market.session == 'open'}"}, {})


def test_assert_expr_allows_context_access() -> None:
    runner = _build_runner()

    runner.step_assert_expr({"expr": "CTX.symbol == 'AAPL'"}, {"symbol": "AAPL"})


def test_assert_expr_raises_when_false() -> None:
    runner = _build_runner(cash=1_000.0)

    with pytest.raises(RecipeExecutionError):
        runner.step_assert_expr(
            {"expr": "${STATE.accounts['main'].cash_free > 5000}"},
            {},
        )


def test_run_recipe_tracks_activity(tmp_path: Path) -> None:
    recipe_path = tmp_path / "demo.yaml"
    recipe_path.write_text(
        """steps:\n  - app.start:\n      name: trader\n  - sleep.ms:\n      duration: 100\n""",
        encoding="utf-8",
    )
    runner = _build_runner()

    runner.run_recipe(recipe_path, {"symbol": "AAPL"})

    snapshot = runner._state.snapshot()
    activity = snapshot["activity"]
    history = activity["history"]

    assert activity["current"] is None
    assert [record["name"] for record in history] == ["app.start", "sleep.ms"]
    assert history[0]["metadata"]["step_index"] == 1
    assert history[1]["status"] == "succeeded"


def test_run_recipe_records_failures(tmp_path: Path) -> None:
    recipe_path = tmp_path / "failing.yaml"
    recipe_path.write_text(
        """steps:\n  - assert.expr:\n      expr: \"${1 == 0}\"\n""",
        encoding="utf-8",
    )
    runner = _build_runner()

    with pytest.raises(RecipeExecutionError):
        runner.run_recipe(recipe_path, {})

    snapshot = runner._state.snapshot()
    history = snapshot["activity"]["history"]

    assert history[-1]["name"] == "assert.expr"
    assert history[-1]["status"] == "failed"
    assert "Expression" in (history[-1]["error"] or "")
