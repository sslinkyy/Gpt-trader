"""Interactive bridge to convert chat commands into intents."""
from __future__ import annotations

import logging
from datetime import datetime
from itertools import count
from pathlib import Path
from threading import Event
from typing import Callable, Dict, Iterable

import yaml

from agent.runner.chat_commands import ChatCommandParser
from agent.runner.intent_watcher import IntentMapping
from agent.nlp import router

LOGGER = logging.getLogger(__name__)


class ChatIntentBridge:
    """Listen for chat-style commands and emit intent files."""

    def __init__(
        self,
        intents_dir: Path,
        mappings: Dict[str, IntentMapping],
        input_func: Callable[[str], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        manifest_path: Path | None = None,
    ) -> None:
        self._intents_dir = intents_dir
        self._mappings = mappings
        self._input = input_func or input
        self._clock = clock or datetime.utcnow
        self._parser = ChatCommandParser()
        self._sequence = count()
        default_manifest = Path("intent_catalog/manifest.yml")
        self._manifest_path = manifest_path or (default_manifest if default_manifest.exists() else None)
        self._stop_event = Event()

    def run(self) -> None:
        """Run an interactive loop until interrupted or "quit" received."""

        if not self._mappings:
            LOGGER.warning("Chat bridge enabled but no intent mappings are available.")

        LOGGER.info(
            "Chat bridge ready. Enter commands like [macro:export_quotes symbol=AAPL]; type 'quit' to exit."
        )

        try:
            while not self._stop_event.is_set():
                line = self._input("> ")
                if line is None:  # pragma: no cover - defensive, input() never returns None
                    continue
                if not line.strip():
                    continue

                if line.strip().lower() in {"quit", "exit"}:
                    LOGGER.info("Exit command received; shutting down chat bridge.")
                    break

                processed = self.process_transcript(line)
                if processed == 0:
                    LOGGER.info("No intents emitted. Embed commands with the form [macro:name key=value ...].")
        except KeyboardInterrupt:
            raise
        except EOFError:
            LOGGER.info("Input stream closed; shutting down chat bridge.")
        finally:
            self.stop()
            LOGGER.info("Chat bridge stopped.")

    def _handle_list_intents(self, topic: str | None) -> None:
        if self._manifest_path is None:
            LOGGER.warning("Intent manifest not configured; cannot list intents.")
            return
        definitions = router.load_intents(self._manifest_path).values()
        topic_norm = (topic or "").strip().lower()
        matches = []
        for definition in definitions:
            haystack = [definition.name.lower(), definition.description.lower(), definition.recipe.lower()] + [syn.lower() for syn in definition.synonyms]
            if not topic_norm or any(topic_norm in field for field in haystack if field):
                matches.append(definition)
        if not matches:
            LOGGER.info("No intents matched topic '%s'.", topic)
            return
        suffix = f" for '{topic}'" if topic_norm else ""
        LOGGER.info("Intent catalog (%s matches)%s", len(matches), suffix)
        for definition in matches:
            summary = definition.description or definition.recipe or "(no description)"
            LOGGER.info("- %s: %s", definition.name, summary)

    def stop(self) -> None:
        """Signal the bridge loop to exit."""

        self._stop_event.set()

    def process_transcript(self, transcript: str) -> int:
        """Parse *transcript* and emit intents for known commands."""

        commands = self._parser.parse(transcript)
        emitted = 0

        if not commands and self._manifest_path is not None:
            routed = router.route(transcript, manifest_path=self._manifest_path)
            if routed:
                intent_name, args = routed
                if intent_name == "intent_list":
                    topic = args.get("topic") if args else None
                    self._handle_list_intents(topic)
                    return emitted
                mapping = self._mappings.get(intent_name)
                if not mapping:
                    LOGGER.warning("Routed intent '%s' is not mapped; ignoring", intent_name)
                else:
                    payload: Dict[str, object] = {"intent": intent_name}
                    if args:
                        payload["args"] = args
                    dest = self._write_intent(intent_name, payload)
                    LOGGER.info("Intent %s written to %s via NL router", intent_name, dest)
                    emitted += 1
                    return emitted

        if not commands:
            return emitted

        for command in commands:
            if command.name == "list_intents":
                topic = None
                if command.args:
                    topic = command.args.get("topic") or command.args.get("filter")
                self._handle_list_intents(topic)
                continue

            mapping = self._mappings.get(command.name)
            if not mapping:
                LOGGER.warning("Unmapped intent '%s'; ignoring command %s", command.name, command.source)
                continue

            payload = command.to_intent_payload()
            dest = self._write_intent(command.name, payload)
            LOGGER.info("Intent %s written to %s", command.name, dest)
            emitted += 1
        return emitted

    def _write_intent(self, intent_name: str, payload: Dict[str, object]) -> Path:
        self._intents_dir.mkdir(parents=True, exist_ok=True)

        for _ in range(100):
            timestamp = self._clock().strftime("%Y%m%dT%H%M%S")
            suffix = next(self._sequence)
            filename = f"{timestamp}_{intent_name}_{suffix:03d}.yml"
            destination = self._intents_dir / filename
            if destination.exists():
                continue

            with destination.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(payload, handle, sort_keys=False)
            return destination

        raise RuntimeError("Unable to allocate a unique intent filename after multiple attempts.")


__all__ = ["ChatIntentBridge"]