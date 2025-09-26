"""Recipe step dispatch for the local RPA agent."""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:  # pragma: no cover - import guard exercised in tests via fallback
    import yaml  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - handled by fallback loader below
    yaml = None

from agent.apps.registry import ApplicationProcess, ApplicationRegistry, WindowRecord
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
            data = _load_recipe(handle)
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
            metadata = {"step_index": idx, "payload_keys": sorted(payload_data.keys())}
            with self._state.activity(name, metadata=metadata):
                handler(payload_data, context)

    def _require_app_name(self, payload: Dict[str, Any], context: Dict[str, Any], action: str) -> str:
        app_name = payload.get("name")
        if not app_name:
            for key in ("name", "app", "application"):
                value = context.get(key)
                if value:
                    app_name = value
                    break
        if not app_name:
            raise RecipeExecutionError(f"{action} requires a 'name'.")
        return str(app_name)

    def _resolve_target(self, app_name: str, payload: Dict[str, Any], context: Dict[str, Any]) -> Any:
        if "instance_id" in payload:
            return payload["instance_id"]
        if "instance" in payload:
            return payload["instance"]
        if "pid" in payload:
            return int(payload["pid"])
        if "instance_id" in context:
            return context["instance_id"]
        if "instance" in context:
            return context["instance"]
        if "pid" in context:
            return int(context["pid"])
        target = payload.get("target") if "target" in payload else context.get("target")
        if target:
            return target
        latest = self._state.latest_instance_for(app_name)
        if latest:
            return latest
        return "latest"

    def _record_process(self, record: ApplicationProcess, *, status: str | None = None) -> None:
        self._state.register_process(
            app=record.definition.name,
            instance_id=record.instance_id,
            pid=record.pid or -1,
            preset=record.preset,
            started_at=record.started_at,
            last_focused_at=record.last_focused_at,
            status=status or "running",
            windows=self._serialize_windows(record.windows),
        )

    @staticmethod
    def _serialize_windows(windows: Dict[int, WindowRecord]) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = []
        for hwnd, info in windows.items():
            serialized.append(
                {
                    "hwnd": hwnd,
                    "title": info.title,
                    "class_name": info.class_name,
                    "bounds": info.bounds,
                    "is_visible": info.is_visible,
                    "is_minimized": info.is_minimized,
                    "process_name": info.process_name,
                    "pid": info.pid,
                    "last_seen": info.last_seen.isoformat() if isinstance(info.last_seen, datetime) else info.last_seen,
                }
            )
        return serialized

    def step_app_start(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        app_name = self._require_app_name(payload, context, "app.start")
        preset = payload.get("preset") if "preset" in payload else context.get("preset")
        extra_args = payload.get("args") if "args" in payload else context.get("args")
        env = payload.get("env") if "env" in payload else context.get("env")
        working_dir = payload.get("working_dir") if "working_dir" in payload else context.get("working_dir")
        inherit_env = payload.get("inherit_env") if "inherit_env" in payload else context.get("inherit_env")

        if extra_args is not None and not isinstance(extra_args, (list, tuple)):
            raise RecipeExecutionError("app.start 'args' must be a list of strings.")
        if env is not None and not isinstance(env, dict):
            raise RecipeExecutionError("app.start 'env' must be a mapping.")

        record = self._apps.start(
            app_name,
            preset=preset,
            args=list(extra_args or []),
            env=env,
            inherit_env=inherit_env,
            working_dir=working_dir,
        )
        self._record_process(record)
        context["instance_id"] = record.instance_id
        context["pid"] = record.pid
        _attach_process_metadata(context, record)
        LOGGER.info(
            "App %s started with pid=%s (instance=%s)",
            app_name,
            record.pid,
            record.instance_id,
        )

    def step_app_focus(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        app_name = self._require_app_name(payload, context, "app.focus")
        target = self._resolve_target(app_name, payload, context)
        record = self._apps.focus(app_name, target=target)
        self._state.update_process(
            record.instance_id,
            windows=self._serialize_windows(record.windows),
            timestamp=_utcnow(),
        )
        context["instance_id"] = record.instance_id
        context["pid"] = record.pid
        _attach_process_metadata(context, record)
        LOGGER.info("Focused app %s (pid=%s)", app_name, record.pid)

    def step_app_minimize(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        app_name = self._require_app_name(payload, context, "app.minimize")
        target = self._resolve_target(app_name, payload, context)
        record = self._apps.minimize(app_name, target=target)
        now = _utcnow()
        self._state.update_process(
            record.instance_id,
            last_action="minimize",
            timestamp=now,
            windows=self._serialize_windows(record.windows),
        )
        context["instance_id"] = record.instance_id
        context["pid"] = record.pid
        _attach_process_metadata(context, record)
        LOGGER.info("Minimized app %s (pid=%s)", app_name, record.pid)

    def step_app_maximize(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        app_name = self._require_app_name(payload, context, "app.maximize")
        target = self._resolve_target(app_name, payload, context)
        record = self._apps.maximize(app_name, target=target)
        now = _utcnow()
        self._state.update_process(
            record.instance_id,
            last_action="maximize",
            timestamp=now,
            windows=self._serialize_windows(record.windows),
        )
        context["instance_id"] = record.instance_id
        context["pid"] = record.pid
        _attach_process_metadata(context, record)
        LOGGER.info("Maximized app %s (pid=%s)", app_name, record.pid)

    def step_app_restore(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        app_name = self._require_app_name(payload, context, "app.restore")
        target = self._resolve_target(app_name, payload, context)
        record = self._apps.restore(app_name, target=target)
        now = _utcnow()
        self._state.update_process(
            record.instance_id,
            last_action="restore",
            timestamp=now,
            windows=self._serialize_windows(record.windows),
        )
        context["instance_id"] = record.instance_id
        context["pid"] = record.pid
        _attach_process_metadata(context, record)
        LOGGER.info("Restored app %s (pid=%s)", app_name, record.pid)

    def step_app_close(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        app_name = self._require_app_name(payload, context, "app.close")
        timeout_ms = payload.get("timeout_ms") if "timeout_ms" in payload else context.get("timeout_ms")
        force_flag = payload.get("force") if "force" in payload else context.get("force")
        all_flag = payload.get("all") if "all" in payload else context.get("all")
        force = bool(force_flag) if force_flag is not None else False
        all_instances = bool(all_flag) if all_flag is not None else False
        timeout = float(timeout_ms) / 1000.0 if timeout_ms is not None else 5.0
        records = self._apps.running_processes(app_name)
        self._apps.close(app_name, timeout=timeout, force=force, all_instances=all_instances)
        timestamp = _utcnow()
        for record in records:
            self._state.update_process(
                record.instance_id,
                status="closed",
                closed_at=timestamp,
                timestamp=timestamp,
                windows=[],
            )
        LOGGER.info("Closed app %s", app_name)

    def step_app_kill(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        app_name = self._require_app_name(payload, context, "app.kill")
        all_flag = payload.get("all") if "all" in payload else context.get("all")
        all_instances = bool(all_flag) if all_flag is not None else False
        records = self._apps.running_processes(app_name)
        self._apps.kill(app_name, all_instances=all_instances)
        timestamp = _utcnow()
        for record in records:
            self._state.update_process(
                record.instance_id,
                status="killed",
                closed_at=timestamp,
                timestamp=timestamp,
                windows=[],
            )
        LOGGER.info("Killed app %s", app_name)

    def step_ui_click(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        selector = payload.get("selector", {})
        identifier = selector.get("identifier", "unknown")
        element = UIElementHandle(identifier=identifier, is_enabled=selector.get("enabled", True))
        method = self._ui_engine.click(element)
        LOGGER.info("UI click succeeded using %s", method)

    def step_ui_type(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would type '%s' into selector %s", payload.get("text"), payload.get("selector"))

    def step_context_snapshot(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        key = payload.get("context_key", "context_snapshot")
        snapshot = self._state.snapshot()
        snapshot.update({
            "context": dict(context),
        })
        context.setdefault("_captures", {})[key] = snapshot
        LOGGER.info("Captured context snapshot under key '%s'", key)

    def step_clipboard_copy(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        try:
            import pyperclip  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - dependency check
            raise RecipeExecutionError("clipboard.copy requires the 'pyperclip' package.") from exc

        key = payload.get("context_key") or context.get("context_key") or payload.get("from_key") or context.get("from_key") or "context_snapshot"
        message = payload.get("message") or context.get("message")

        data = None
        if "_captures" in context and key in context["_captures"]:
            data = context["_captures"][key]
        if data is None:
            data = self._state.snapshot()

        payload_to_send: Any
        if message:
            payload_to_send = {
                "message": message,
                "snapshot": data,
            }
        else:
            payload_to_send = data

        serialized = yaml.safe_dump(payload_to_send, sort_keys=False)
        pyperclip.copy(serialized)
        LOGGER.info("Copied context payload to clipboard (%s)", key)

    def step_clipboard_load_context(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        try:
            import pyperclip  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - dependency check
            raise RecipeExecutionError("clipboard.load_context requires the 'pyperclip' package.") from exc

        raw = pyperclip.paste()
        if not raw:
            raise RecipeExecutionError("Clipboard is empty.")
        try:
            data = yaml.safe_load(raw)
        except Exception as exc:
            raise RecipeExecutionError(f"Failed to parse clipboard content: {exc}") from exc

        if isinstance(data, dict):
            context.update(data)
        context.setdefault("_captures", {})[payload.get("context_key", "clipboard")] = data
        LOGGER.info("Loaded clipboard content into context (%s)", payload.get("context_key", "clipboard"))

    def step_browser_launch(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would configure browser session %s", payload)

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

        expression = _extract_expression(expr)
        state_namespace = _wrap_eval_namespace(self._state.snapshot())
        context_namespace = _wrap_eval_namespace(context)

        safe_builtins = {"len": len, "min": min, "max": max, "sum": sum, "sorted": sorted, "any": any, "all": all}
        try:
            result = eval(  # noqa: S307 - controlled evaluation context
                expression,
                {"__builtins__": safe_builtins},
                {"STATE": state_namespace, "CTX": context_namespace},
            )
        except Exception as exc:  # pragma: no cover - defensive
            raise RecipeExecutionError(f"Failed to evaluate expression '{expr}': {exc}") from exc

        if not result:
            raise RecipeExecutionError(f"Expression '{expr}' evaluated to false.")

        LOGGER.info("Guard expression '%s' evaluated to True", expr)

    def step_sleep_ms(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("[demo] Would sleep for %sms", payload.get("duration", 0))

    def step_reporter_note(self, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        LOGGER.info("REPORTER: %s", payload.get("message"))


__all__ = ["RecipeRunner", "RecipeExecutionError"]


def _extract_expression(expr: str) -> str:
    stripped = expr.strip()
    if stripped.startswith("${") and stripped.endswith("}"):
        return stripped[2:-1].strip()
    return stripped


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _attach_process_metadata(context: Dict[str, Any], record: ApplicationProcess) -> None:
    processes = context.setdefault("_apps", {})
    processes[record.definition.name] = {
        "pid": record.pid,
        "preset": record.preset,
        "instance_id": record.instance_id,
        "windows": RecipeRunner._serialize_windows(record.windows),
        "started_at": record.started_at.isoformat(),
        "last_focused_at": record.last_focused_at.isoformat() if record.last_focused_at else None,
    }


class _EvalNamespace:
    """Provide attribute and key access for nested mappings during eval."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = {key: _wrap_eval_namespace(value) for key, value in data.items()}

    def __getattr__(self, item: str) -> Any:
        try:
            return self._data[item]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(item) from exc

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"_EvalNamespace({self._data!r})"


def _wrap_eval_namespace(value: Any) -> Any:
    if isinstance(value, _EvalNamespace):
        return value
    if isinstance(value, Mapping):
        return _EvalNamespace(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return type(value)(_wrap_eval_namespace(item) for item in value)
    return value


def _load_recipe(handle: Any) -> Dict[str, Any]:
    text = handle.read()

    if yaml is not None:
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise RecipeExecutionError("Recipe must decode to a mapping.")
        return data

    import json

    try:
        data = json.loads(text or "{}")
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise RecipeExecutionError(
            "Failed to parse recipe. Install PyYAML to enable YAML support."
        ) from exc

    if not isinstance(data, dict):
        raise RecipeExecutionError("Recipe must decode to a mapping.")

    return data
