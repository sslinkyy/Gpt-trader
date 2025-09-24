"""Tests for recipe runner step handlers."""
from __future__ import annotations

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
