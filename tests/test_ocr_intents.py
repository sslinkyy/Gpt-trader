from __future__ import annotations

from pathlib import Path

import threading
import types

import yaml

from agent.runner.chat_bridge import ChatIntentBridge
from agent.runner.intent_watcher import IntentMapping
from agent.vision.ocr_intents import OCRIntentScanner


def test_ocr_scanner_emits_intent(tmp_path: Path) -> None:
    intents_dir = tmp_path / "intents"
    intents_dir.mkdir()
    recipe_path = tmp_path / "demo.yml"
    recipe_path.write_text("steps: []", encoding="utf-8")

    bridge = ChatIntentBridge(intents_dir=intents_dir, mappings={"demo": IntentMapping(recipe=recipe_path)})
    scanner = OCRIntentScanner(chat_bridge=bridge, text_provider=lambda: "*#intent#* [demo]")

    emitted = scanner.process_text(scanner._text_provider())

    assert emitted == 1
    files = list(intents_dir.glob("*.yml"))
    assert len(files) == 1
    payload = yaml.safe_load(files[0].read_text(encoding="utf-8"))
    assert payload == {"intent": "demo"}


def test_ocr_scanner_deduplicates_commands(tmp_path: Path) -> None:
    intents_dir = tmp_path / "intents"
    intents_dir.mkdir()
    recipe_path = tmp_path / "demo.yml"
    recipe_path.write_text("steps: []", encoding="utf-8")

    bridge = ChatIntentBridge(intents_dir=intents_dir, mappings={"demo": IntentMapping(recipe=recipe_path)})
    scanner = OCRIntentScanner(chat_bridge=bridge, text_provider=lambda: "*#intent#* [demo]")

    scanner.process_text(scanner._text_provider())
    emitted_second = scanner.process_text(scanner._text_provider())

    assert emitted_second == 0
    files = list(intents_dir.glob("*.yml"))
    assert len(files) == 1


def test_ocr_scanner_supports_action_id_markup(tmp_path: Path) -> None:
    intents_dir = tmp_path / "intents"
    intents_dir.mkdir()
    recipe_path = tmp_path / "demo.yml"
    recipe_path.write_text("steps: []", encoding="utf-8")

    bridge = ChatIntentBridge(intents_dir=intents_dir, mappings={"demo": IntentMapping(recipe=recipe_path)})
    scanner = OCRIntentScanner(
        chat_bridge=bridge,
        text_provider=lambda: "#intent# + 42 + [demo symbol=AAPL]",
    )

    emitted = scanner.process_text(scanner._text_provider())

    assert emitted == 1
    files = list(intents_dir.glob("*.yml"))
    assert len(files) == 1
    payload = yaml.safe_load(files[0].read_text(encoding="utf-8"))
    assert payload == {"intent": "demo", "args": {"symbol": "AAPL", "action_id": "42"}}




def test_screen_text_provider_thread_local_instances(monkeypatch):
    from agent.vision.ocr_intents import ScreenTextProvider

    class DummyGrab:
        width = 1
        height = 1
        rgb = b"\x00\x00\x00"

    class DummyMSS:
        def __init__(self):
            self.monitors = [object()]

        def grab(self, monitor):
            return DummyGrab()

    clients = {}

    def factory():
        client = DummyMSS()
        clients[threading.get_ident()] = client
        return client

    image_factory = types.SimpleNamespace(frombytes=lambda mode, size, data: object())
    ocr_engine = types.SimpleNamespace(image_to_string=lambda image: "TEXT")

    provider = ScreenTextProvider.__new__(ScreenTextProvider)
    provider._mss_factory = factory
    provider._image_factory = image_factory
    provider._ocr = ocr_engine
    provider._thread_local = threading.local()

    assert provider.capture_text() == "TEXT"

    results = {}

    def worker():
        results['thread'] = threading.get_ident()
        results['text'] = provider.capture_text()

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert results['text'] == "TEXT"
    assert len(clients) == 2
    assert threading.get_ident() in clients
    assert results['thread'] in clients and results['thread'] != threading.get_ident()
