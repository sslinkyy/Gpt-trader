"""Watch a directory for new intents and dispatch recipes."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Dict

_YAML_HELP = "The 'pyyaml' package is required to parse intents. Install it with `pip install pyyaml`."
_WATCHDOG_HELP = "The 'watchdog' package is required to watch intents. Install it with `pip install watchdog`."

try:
    import yaml  # type: ignore[import]
    _YAML_IMPORT_ERROR: ModuleNotFoundError | None = None
except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
    yaml = None  # type: ignore[assignment]
    _YAML_IMPORT_ERROR = exc

try:
    from agent.runner.steps import RecipeRunner
except ModuleNotFoundError as exc:
    if exc.name != "agent" or __package__ not in (None, ""):
        raise
    import sys

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))

    try:
        from agent.runner.steps import RecipeRunner  # type: ignore[assignment]
    except ModuleNotFoundError:
        raise exc

try:
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent
    from watchdog.observers import Observer
    _WATCHDOG_IMPORT_ERROR: ModuleNotFoundError | None = None
except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
    FileSystemEventHandler = object  # type: ignore[assignment]
    FileCreatedEvent = Any  # type: ignore[assignment]
    _WATCHDOG_IMPORT_ERROR = exc

    class _ObserverStub:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(_WATCHDOG_HELP) from _WATCHDOG_IMPORT_ERROR

    Observer = _ObserverStub  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)

_READ_RETRY_ATTEMPTS = 10
_READ_RETRY_DELAY = 0.1


@dataclass
class IntentMapping:
    recipe: Path


class IntentWatcher(FileSystemEventHandler):
    """Watch an intents directory and execute mapped recipes on arrival."""

    def __init__(
        self,
        intents_dir: Path,
        archive_dir: Path,
        mappings: Dict[str, IntentMapping],
        recipe_runner: RecipeRunner,
    ) -> None:
        if _YAML_IMPORT_ERROR is not None:
            raise RuntimeError(_YAML_HELP) from _YAML_IMPORT_ERROR
        if _WATCHDOG_IMPORT_ERROR is not None:
            raise RuntimeError(_WATCHDOG_HELP) from _WATCHDOG_IMPORT_ERROR

        self._intents_dir = intents_dir
        self._archive_dir = archive_dir
        self._mappings = mappings
        self._runner = recipe_runner
        self._observer: Observer | None = None
        self._stop_event = Event()

    def start(self) -> None:
        self._intents_dir.mkdir(parents=True, exist_ok=True)
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        observer = Observer()
        observer.schedule(self, str(self._intents_dir), recursive=False)
        observer.start()
        self._observer = observer
        LOGGER.info("Intent watcher started for %s", self._intents_dir)

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()
        self._stop_event.set()
        LOGGER.info("Intent watcher stopped.")

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if getattr(event, "is_directory", False):
            return
        path = Path(event.src_path)
        LOGGER.info("New intent detected: %s", path.name)
        try:
            self._process_intent(path)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Failed to process intent %s: %s", path, exc)

    def _load_intent_payload(self, path: Path) -> Dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(_READ_RETRY_ATTEMPTS):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    data = yaml.safe_load(handle)
            except Exception as exc:
                last_error = exc
                LOGGER.debug(
                    "Intent read failed on attempt %s for %s: %s",
                    attempt + 1,
                    path,
                    exc,
                )
                time.sleep(_READ_RETRY_DELAY)
                continue

            if data in (None, ""):
                time.sleep(_READ_RETRY_DELAY)
                continue
            if not isinstance(data, dict):
                raise TypeError(f"Intent file must deserialize to a mapping, got {type(data)!r}.")
            return data

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Intent file {path} is empty or could not be parsed after retries.")

    def _process_intent(self, path: Path) -> None:
        data = self._load_intent_payload(path)

        intent_name = data.get("intent")
        if not intent_name:
            raise RuntimeError(f"Intent file {path} missing required 'intent' field.")
        if intent_name not in self._mappings:
            raise RuntimeError(f"Intent '{intent_name}' is not mapped to a recipe.")

        mapping = self._mappings[intent_name]
        context = data.get("args") or {}
        if not isinstance(context, dict):
            raise TypeError("Intent args must be a mapping if provided.")
        if not mapping.recipe.exists():
            raise FileNotFoundError(f"Recipe file not found: {mapping.recipe}")
        self._runner.run_recipe(mapping.recipe, context)

        archive_path = self._archive_dir / path.name
        path.rename(archive_path)
        LOGGER.info("Intent %s archived to %s", intent_name, archive_path)


__all__ = ["IntentWatcher", "IntentMapping"]