"""LLM-assisted natural language routing."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import yaml


@dataclass
class LLMRouteResult:
    intent: str
    args: Dict[str, str]


def build_prompt(utterance: str, manifest_path: Path) -> str:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    snippets = []
    for entry in manifest.get("intents", [])[:20]:
        snippets.append(
            {
                "intent": entry.get("intent"),
                "description": entry.get("description"),
                "args": entry.get("args", []),
                "synonyms": entry.get("synonyms", []),
            }
        )
    manifest_text = json.dumps(snippets, indent=2)
    return (
        "You are a routing assistant. Given an utterance, choose the most appropriate intent\n"
        "and return a JSON object with keys 'intent' and optional 'args'.\n"
        "If no intent matches, respond with an empty JSON object {}.\n\n"
        f"Utterance: {utterance}\n\n"
        f"Intent catalog: {manifest_text}\n"
    )


def parse_response(response: str) -> Optional[LLMRouteResult]:
    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "intent" not in data or not data["intent"]:
        return None
    args = data.get("args")
    if args is None or not isinstance(args, dict):
        args = {}
    return LLMRouteResult(intent=str(data["intent"]).strip(), args={str(k): str(v) for k, v in args.items()})


def llm_route(
    utterance: str,
    *,
    manifest_path: Path,
    call_model: Callable[[str], str],
) -> Optional[Tuple[str, Dict[str, str]]]:
    if not utterance.strip():
        return None
    prompt = build_prompt(utterance, manifest_path)
    try:
        raw = call_model(prompt)
    except Exception:
        return None
    result = parse_response(raw)
    if not result:
        return None
    return result.intent, result.args


__all__ = ["LLMRouteResult", "build_prompt", "llm_route"]
