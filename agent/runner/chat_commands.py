"""Utilities for parsing automation commands from chat transcripts."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Callable, Dict, List, Tuple

LOGGER = logging.getLogger(__name__)


_COMMAND_PATTERN = re.compile(
    r"\[(?P<prefix>agent|macro)\s*:(?P<name>[a-zA-Z0-9_.-]+)(?P<args>[^\]]*)\]",
    re.IGNORECASE,
)
_ARG_PATTERN = re.compile(
    r"(?P<key>[a-zA-Z0-9_.-]+)\s*=\s*(?P<value>\"[^\"]*\"|'[^']*'|[^\s]+)"
)


@dataclass(frozen=True)
class ChatCommand:
    """A structured representation of an automation command."""

    name: str
    args: Dict[str, str]
    source: str

    def to_intent_payload(self) -> Dict[str, object]:
        """Convert the command into an intent payload for downstream macros."""

        payload: Dict[str, object] = {"intent": self.name}
        if self.args:
            payload["args"] = self.args
        return payload


class ChatCommandParser:
    """Parse inline commands embedded in chat transcripts."""

    def parse(self, transcript: str) -> List[ChatCommand]:
        """Extract commands from *transcript* preserving their appearance order."""

        commands: List[ChatCommand] = []
        for match in _COMMAND_PATTERN.finditer(transcript):
            raw_args = match.group("args") or ""
            args = self._parse_args(raw_args)
            command = ChatCommand(
                name=match.group("name").lower(),
                args=args,
                source=match.group(0),
            )
            LOGGER.debug("Parsed chat command: %s", command)
            commands.append(command)
        return commands

    @staticmethod
    def _parse_args(raw_args: str) -> Dict[str, str]:
        args: Dict[str, str] = {}
        for match in _ARG_PATTERN.finditer(raw_args):
            key = match.group("key").lower()
            value = ChatCommandParser._strip_quotes(match.group("value"))
            args[key] = value
        return args

    @staticmethod
    def _strip_quotes(value: str) -> str:
        if not value:
            return value
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]
        return value


class ChatCommandWatcher:
    """Poll chat transcripts and emit new automation commands."""

    def __init__(
        self,
        transcript_provider: Callable[[], str],
        parser: ChatCommandParser | None = None,
    ) -> None:
        self._provider = transcript_provider
        self._parser = parser or ChatCommandParser()
        self._seen_tokens: set[Tuple[str, Tuple[Tuple[str, str], ...], str]] = set()

    def poll(self) -> List[ChatCommand]:
        """Return commands that have not been emitted in previous polls."""

        transcript = self._provider()
        commands = self._parser.parse(transcript)
        fresh: List[ChatCommand] = []
        for command in commands:
            token = self._command_token(command)
            if token in self._seen_tokens:
                continue
            self._seen_tokens.add(token)
            fresh.append(command)
        return fresh

    def reset(self) -> None:
        """Clear deduplication state, allowing commands to be re-emitted."""

        self._seen_tokens.clear()

    @staticmethod
    def _command_token(command: ChatCommand) -> Tuple[str, Tuple[Tuple[str, str], ...], str]:
        return (
            command.name,
            tuple(sorted(command.args.items())),
            command.source,
        )


__all__ = ["ChatCommand", "ChatCommandParser", "ChatCommandWatcher"]
