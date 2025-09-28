from __future__ import annotations

from pathlib import Path

from agent.nlp import llm_router

MANIFEST = Path("intent_catalog/manifest.yml")


def test_llm_route_parses_successful_response(tmp_path: Path) -> None:
    def fake_model(prompt: str) -> str:
        assert "Utterance" in prompt
        return '{"intent": "app_launch", "args": {"name": "notepad"}}'

    result = llm_router.llm_route(
        "launch notepad",
        manifest_path=MANIFEST,
        call_model=fake_model,
    )
    assert result == ("app_launch", {"name": "notepad"})


def test_llm_route_handles_invalid_json(tmp_path: Path) -> None:
    result = llm_router.llm_route(
        "do something",
        manifest_path=MANIFEST,
        call_model=lambda prompt: "not json",
    )
    assert result is None
