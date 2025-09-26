from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from agent.runner.chat_bridge import ChatIntentBridge
from agent.runner.intent_watcher import IntentMapping


def test_bridge_writes_intent_file(tmp_path: Path) -> None:
    intents_dir = tmp_path / "intents"
    mapping = {"export_quotes": IntentMapping(recipe=Path("dummy"))}
    bridge = ChatIntentBridge(
        intents_dir=intents_dir,
        mappings=mapping,
        clock=lambda: datetime(2024, 1, 1, 12, 0, 0),
    )

    emitted = bridge.process_transcript("[macro:export_quotes symbol=AAPL qty=10]")

    assert emitted == 1
    files = list(intents_dir.glob("*.yml"))
    assert len(files) == 1
    with files[0].open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert data == {
        "intent": "export_quotes",
        "args": {"symbol": "AAPL", "qty": "10"},
    }


def test_bridge_ignores_unknown_intents(tmp_path: Path) -> None:
    intents_dir = tmp_path / "intents"
    bridge = ChatIntentBridge(
        intents_dir=intents_dir,
        mappings={},
        clock=lambda: datetime(2024, 1, 1, 12, 0, 0),
    )

    emitted = bridge.process_transcript("[macro:unknown]")

    assert emitted == 0
    assert not list(intents_dir.glob("*.yml"))


def test_bridge_handles_multiple_commands(tmp_path: Path) -> None:
    intents_dir = tmp_path / "intents"
    mapping = {
        "export_quotes": IntentMapping(recipe=Path("a")),
        "trade": IntentMapping(recipe=Path("b")),
    }
    bridge = ChatIntentBridge(
        intents_dir=intents_dir,
        mappings=mapping,
        clock=lambda: datetime(2024, 1, 1, 12, 0, 0),
    )

    transcript = "[macro:export_quotes symbol=AAPL]\n[macro:trade symbol=MSFT qty=5]"
    emitted = bridge.process_transcript(transcript)

    assert emitted == 2
    payloads = []
    for path in sorted(intents_dir.glob("*.yml")):
        payloads.append(yaml.safe_load(path.read_text(encoding="utf-8")))
    assert {
        "intent": "export_quotes",
        "args": {"symbol": "AAPL"},
    } in payloads
    assert {
        "intent": "trade",
        "args": {"symbol": "MSFT", "qty": "5"},
    } in payloads