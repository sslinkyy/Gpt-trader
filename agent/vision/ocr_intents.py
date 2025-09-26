"""OCR-driven intent scanner that watches the screen for command markers."""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from typing import Callable, Deque

from agent.runner.chat_commands import ChatCommandParser

LOGGER = logging.getLogger(__name__)

_MARKER_PATTERN = re.compile(
    r'(?:\*#intent#\*|#intent#)[\s+:-]*(?:(?P<action_id>\d+)[\s+:-]*)?\[(?P<command>[^\]]+)\]',
    re.IGNORECASE,
)


class ScreenTextProvider:
    """Capture the current desktop and run OCR to extract text."""

    def __init__(self) -> None:
        try:
            import mss  # type: ignore[import-not-found]
            from PIL import Image  # type: ignore[import-not-found]
            import pytesseract  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - defended by runtime check
            raise RuntimeError(
                "OCR intent scanning requires 'pytesseract', 'pillow', and 'mss'. Install them to enable this feature."
            ) from exc

        self._mss_factory = mss.mss
        self._image_factory = Image
        self._ocr = pytesseract
        self._thread_local = threading.local()

    def _client(self):
        client = getattr(self._thread_local, "mss", None)
        if client is None:
            client = self._mss_factory()
            self._thread_local.mss = client
        return client

    def capture_text(self) -> str:
        client = self._client()
        screenshot = client.grab(client.monitors[0])
        image = self._image_factory.frombytes("RGB", (screenshot.width, screenshot.height), screenshot.rgb)
        return self._ocr.image_to_string(image)


class OCRIntentScanner:
    """Scan screen text for intent markers and emit matching commands."""

    def __init__(
        self,
        *,
        chat_bridge,
        text_provider: Callable[[], str] | None = None,
        poll_interval: float = 2.0,
        history_limit: int = 50,
    ) -> None:
        self._bridge = chat_bridge
        self._parser = ChatCommandParser()
        self._text_provider = text_provider or ScreenTextProvider().capture_text
        self._poll_interval = max(0.1, poll_interval)
        self._fired_history: Deque[tuple[str, tuple[tuple[str, str], ...]]] = deque(maxlen=history_limit)
        self._fired_lookup: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _record_fired(self, key: tuple[str, tuple[tuple[str, str], ...]]) -> None:
        if self._fired_history.maxlen and len(self._fired_history) == self._fired_history.maxlen:
            expired = self._fired_history.popleft()
            self._fired_lookup.discard(expired)
        self._fired_history.append(key)
        self._fired_lookup.add(key)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="OCRIntentScanner", daemon=True)
        self._thread.start()
        LOGGER.info("OCR intent scanner started.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        LOGGER.info("OCR intent scanner stopped.")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                text = self._text_provider()
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("OCR capture failed: %s", exc)
                time.sleep(self._poll_interval)
                continue

            if text:
                emitted = self.process_text(text)
                if emitted:
                    LOGGER.debug("OCR bridge emitted %s intents.", emitted)
            time.sleep(self._poll_interval)

    def process_text(self, text: str) -> int:
        """Examine *text* for intent markers and emit new commands."""

        emitted = 0
        for match in _MARKER_PATTERN.finditer(text):
            command_text = (match.group('command') or '').strip()
            if not command_text:
                continue
            action_id = (match.group('action_id') or '').strip()
            payload_command = command_text.rstrip()
            if action_id and 'action_id=' not in command_text.lower():
                payload_command = f"{command_text.rstrip()} action_id={action_id}"

            transcript = f"[macro:{payload_command}]"
            commands = self._parser.parse(transcript)
            if not commands:
                LOGGER.debug("OCR marker produced no parsable commands: %s", payload_command)
                continue
            command = commands[0]
            key = (command.name, tuple(sorted(command.args.items())))
            if key in self._fired_lookup:
                continue

            if self._bridge.process_transcript(transcript):
                self._record_fired(key)
                emitted += 1

        return emitted


__all__ = ["OCRIntentScanner", "ScreenTextProvider"]
