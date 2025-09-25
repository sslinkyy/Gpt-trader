"""Tests for chat command parsing and watching."""
from __future__ import annotations

from typing import List

from agent.runner.chat_commands import ChatCommandParser, ChatCommandWatcher


def test_parser_extracts_commands_with_arguments() -> None:
    parser = ChatCommandParser()
    transcript = "Hello [macro:export_quotes symbol=AAPL qty=10] world"

    commands = parser.parse(transcript)

    assert [command.name for command in commands] == ["export_quotes"]
    assert commands[0].args == {"symbol": "AAPL", "qty": "10"}
    assert commands[0].to_intent_payload() == {
        "intent": "export_quotes",
        "args": {"symbol": "AAPL", "qty": "10"},
    }


def test_parser_supports_quoted_arguments() -> None:
    parser = ChatCommandParser()
    transcript = "[agent:trade symbol=\"MSFT\" note='enter long']"

    commands = parser.parse(transcript)

    assert commands[0].args == {"symbol": "MSFT", "note": "enter long"}


def test_watcher_returns_only_new_commands() -> None:
    parser = ChatCommandParser()
    transcripts = [
        "[macro:export_quotes symbol=AAPL]",
        "[macro:export_quotes symbol=AAPL]\n[macro:trade symbol=MSFT]",
    ]
    index = {"value": 0}

    def provider() -> str:
        return transcripts[index["value"]]

    watcher = ChatCommandWatcher(provider, parser=parser)

    first_batch = watcher.poll()
    assert [command.name for command in first_batch] == ["export_quotes"]

    index["value"] = 1
    second_batch = watcher.poll()

    assert [command.name for command in second_batch] == ["trade"]


def test_watcher_reset_allows_reprocessing() -> None:
    transcripts = ["[macro:export_quotes symbol=AAPL]"]
    provider_calls: List[str] = []

    def provider() -> str:
        provider_calls.append("called")
        return transcripts[0]

    watcher = ChatCommandWatcher(provider)

    assert watcher.poll()  # first pass emits command
    watcher.reset()
    assert watcher.poll()  # second pass emits command again after reset
    assert len(provider_calls) == 2
