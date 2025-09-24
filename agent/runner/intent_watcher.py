"""Watch a directory for new intents and dispatch recipes."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Dict

from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from watchdog.observers import Observer
import yaml

from agent.runner.steps import RecipeRunner

LOGGER = logging.getLogger(__name__)


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
        if event.is_directory:
            return
        path = Path(event.src_path)
        LOGGER.info("New intent detected: %s", path.name)
        try:
            self._process_intent(path)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Failed to process intent %s: %s", path, exc)

    def _process_intent(self, path: Path) -> None:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)

        intent_name = data.get("intent")
        if intent_name not in self._mappings:
            raise RuntimeError(f"Intent '{intent_name}' is not mapped to a recipe.")

        mapping = self._mappings[intent_name]
        context = data.get("args", {})
        if not mapping.recipe.exists():
            raise FileNotFoundError(f"Recipe file not found: {mapping.recipe}")
        self._runner.run_recipe(mapping.recipe, context)

        archive_path = self._archive_dir / path.name
        path.rename(archive_path)
        LOGGER.info("Intent %s archived to %s", intent_name, archive_path)


__all__ = ["IntentWatcher", "IntentMapping"]
