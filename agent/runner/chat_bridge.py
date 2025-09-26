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

LOGGER = logging.getLogger(__name__)


class ChatIntentBridge:
    """Listen for chat-style commands and emit intent files."""

    def __init__(
        self,
        intents_dir: Path,
        mappings: Dict[str, IntentMapping],
        input_func: Callable[[str], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._intents_dir = intents_dir
        self._mappings = mappings
        self._input = input_func or input
        self._clock = clock or datetime.utcnow
        self._parser = ChatCommandParser()
        self._sequence = count()
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

    def stop(self) -> None:
        """Signal the bridge loop to exit."""

        self._stop_event.set()

    def process_transcript(self, transcript: str) -> int:
        """Parse *transcript* and emit intents for known commands."""

        commands = self._parser.parse(transcript)
        if not commands:
            return 0

        emitted = 0
        for command in commands:
            mapping = self._mappings.get(command.name)
            if not mapping:
                LOGGER.warning("Unmapped intent '%s'; ignoring command %s", command.name, command.source)
                continue

            payload = command.to_intent_payload()
            path = self._write_intent(command.name, payload)
            LOGGER.info("Intent %s written to %s", command.name, path)
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