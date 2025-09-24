"""Recipe step dispatch for the local RPA agent."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

import yaml

from agent.apps.registry import ApplicationRegistry
from agent.runner.ui_engine import UIClickEngine, UIElementHandle
from agent.state.store import StateStore

LOGGER = logging.getLogger(__name__)


class RecipeExecutionError(RuntimeError):
    pass


class RecipeRunner:
    """Execute YAML recipes using typed step handlers."""

    def __init__(
        self,
        apps: ApplicationRegistry,
        state: StateStore,
        allow_focus_tap: bool,
    ) -> None:
        self._apps = apps
        self._state = state
        self._ui_engine = UIClickEngine(allow_focus_tap=allow_focus_tap)

    def run_recipe(self, recipe_path: Path, context: Dict[str, Any]) -> None:
        with recipe_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        steps = data.get("steps", [])
        if not isinstance(steps, list):
            raise RecipeExecutionError("Recipe steps must be a list.")

        for idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                raise RecipeExecutionError(f"Step {idx} must be a mapping.")
            if len(step) != 1:
                raise RecipeExecutionError(f"Step {idx} must contain exactly one instruction.")
            name, payload = next(iter(step.items()))
            LOGGER.info("Executing step %s (%s)", idx, name)
            handler = getattr(self, f"step_{name.replace('.', '_')}", None)
            if handler is None:
                raise RecipeExecutionError(f"Unsupported step '{name}'")
            payload_data = payload or {}
            if not isinstance(payload_data, dict):
                raise RecipeExecutionError(f"Step {name} payload must be a mapping.")
            handler(payload_data, context)

    # --- Step handlers -------------------------------------------------

    def step_app_start(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        app_name = payload.get("name")
        if not app_name:
            raise RecipeExecutionError("app.start requires a 'name'.")
        app = self._apps.get(app_name)
        app.require_enabled()
        LOGGER.info("[demo] Would start app %s with config %s", app_name, app.config)

    def step_app_focus(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        app_name = payload.get("name")
        if not app_name:
            raise RecipeExecutionError("app.focus requires a 'name'.")
        LOGGER.info("[demo] Would focus app window for %s", app_name)

    def step_app_close(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        app_name = payload.get("name")
        LOGGER.info("[demo] Would close app %s", app_name)

    def step_app_kill(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        app_name = payload.get("name")
        LOGGER.info("[demo] Would kill app %s", app_name)

    def step_ui_click(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        selector = payload.get("selector", {})
        identifier = selector.get("automation_id") or selector.get("name") or "unknown"
        element = UIElementHandle(identifier=identifier)
        method = self._ui_engine.click(element)
        LOGGER.info("ui.click resolved via %s", method)

    def step_ui_wait(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would wait for selector %s", payload.get("selector"))

    def step_ui_exists(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would assert existence for selector %s", payload.get("selector"))

    def step_ui_focus(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would focus selector %s", payload.get("selector"))

    def step_ui_read(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would read text from selector %s", payload.get("selector"))

    def step_input_type(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        text = payload.get("text", "")
        LOGGER.info("[demo] Would type text: %s", text)

    def step_input_key(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would press key: %s", payload.get("key"))

    def step_input_hotkey(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would press hotkey: %s", payload.get("combo"))

    def step_browser_launch(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would launch browser context: %s", payload)

    def step_browser_close(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would close browser context")

    def step_page_goto(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would navigate browser to %s", payload.get("url"))

    def step_dom_click(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would click DOM selector %s", payload.get("selector"))

    def step_dom_type(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would type in DOM selector %s", payload.get("selector"))

    def step_download_expect_and_save(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would download file: %s", payload)

    def step_assert_text_contains(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would assert text contains %s", payload)

    def step_assert_expr(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        expr = payload.get("expr")
        if not expr:
            raise RecipeExecutionError("assert.expr requires 'expr'.")
        session = self._state.market_session()
        LOGGER.info("Evaluating guard expression '%s' (session=%s)", expr, session)

    def step_sleep_ms(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would sleep for %sms", payload.get("duration", 0))

    def step_reporter_note(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("REPORTER: %s", payload.get("message"))


__all__ = ["RecipeRunner", "RecipeExecutionError"]
