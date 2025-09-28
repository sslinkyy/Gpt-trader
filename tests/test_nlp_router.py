"""Tests for the natural-language router."""
from __future__ import annotations

from pathlib import Path

from agent.nlp import router

MANIFEST = Path("intent_catalog/manifest.yml")


def test_router_matches_synonym():
    result = router.route("please browser minimize", manifest_path=MANIFEST)
    assert result is not None
    intent, args = result
    assert intent == "browser_minimize"
    assert args == {}


def test_router_extracts_args():
    utterance = "launch app name=notepad"
    result = router.route(utterance, manifest_path=MANIFEST)
    assert result is not None
    intent, args = result
    assert intent == "app_launch"
    assert args == {"name": "notepad"}


def test_router_respects_minimum_score():
    result = router.route("open something", manifest_path=MANIFEST, minimum_score=5)
    assert result is None


def test_router_returns_none_for_empty_input():
    assert router.route("   ", manifest_path=MANIFEST) is None
