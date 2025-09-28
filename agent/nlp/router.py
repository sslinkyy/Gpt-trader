"""Lightweight natural-language intent router."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import yaml

@dataclass
class IntentDefinition:
    name: str
    recipe: str
    description: str
    args: List[str]
    synonyms: List[str]

    def match_score(self, utterance: str) -> int:
        base = 0
        if self.name in utterance:
            base += 3
        for synonym in self.synonyms:
            if synonym in utterance:
                base += 2
        return base


def load_intents(manifest_path: Path) -> Dict[str, IntentDefinition]:
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    intents: Dict[str, IntentDefinition] = {}
    for row in data.get("intents", []):
        name = row.get("intent", "").strip()
        if not name:
            continue
        intents[name] = IntentDefinition(
            name=name,
            recipe=row.get("recipe", ""),
            description=row.get("description", ""),
            args=list(row.get("args", [])),
            synonyms=[syn.strip() for syn in row.get("synonyms", []) if syn.strip()],
        )
    return intents


_INTENT_CACHE: Dict[Path, Dict[str, IntentDefinition]] = {}


def _get_manifest(manifest_path: Path) -> Dict[str, IntentDefinition]:
    if manifest_path not in _INTENT_CACHE:
        _INTENT_CACHE[manifest_path] = load_intents(manifest_path)
    return _INTENT_CACHE[manifest_path]


_PARAM_PATTERN = re.compile(r"(\w+)\s*[:=]\s*([\w./:-]+)")


def parse_args(utterance: str) -> Dict[str, str]:
    args: Dict[str, str] = {}
    for key, value in _PARAM_PATTERN.findall(utterance):
        args[key.lower()] = value
    return args


def route(
    utterance: str,
    *,
    manifest_path: Path,
    minimum_score: int = 2,
) -> Optional[Tuple[str, Dict[str, str]]]:
    utterance_norm = utterance.lower().strip()
    if not utterance_norm:
        return None

    manifests = _get_manifest(manifest_path)
    best_name: Optional[str] = None
    best_score = minimum_score - 1
    for definition in manifests.values():
        score = definition.match_score(utterance_norm)
        if score > best_score:
            best_name = definition.name
            best_score = score

    if not best_name or best_name not in manifests or best_score < minimum_score:
        return None

    args = parse_args(utterance_norm)
    definition = manifests[best_name]
    # Filter args to known keys unless none specified
    if definition.args:
        args = {key: value for key, value in args.items() if key in definition.args}
    return best_name, args


__all__ = ["route", "load_intents", "IntentDefinition"]
