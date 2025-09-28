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
    if "topic" not in args:
        topic_match = re.search(r"(?:for|about)\s+([\w.-]+)", utterance)
        if topic_match:
            args["topic"] = topic_match.group(1)
    return args




def _score_candidates(utterance: str, manifest: Dict[str, IntentDefinition]) -> List[Tuple[str, int]]:
    scores: List[Tuple[str, int]] = []
    for definition in manifest.values():
        score = definition.match_score(utterance)
        if score > 0:
            scores.append((definition.name, score))
    scores.sort(key=lambda item: item[1], reverse=True)
    return scores

def rank(utterance: str, *, manifest_path: Path) -> List[Tuple[str, int]]:
    utterance_norm = (utterance or "").lower().strip()
    if not utterance_norm:
        return []
    manifest = _get_manifest(manifest_path)
    return _score_candidates(utterance_norm, manifest)

def route(
    utterance: str,
    *,
    manifest_path: Path,
    minimum_score: int = 2,
) -> Optional[Tuple[str, Dict[str, str]]]:
    utterance_norm = (utterance or "").lower().strip()
    if not utterance_norm:
        return None

    manifest = _get_manifest(manifest_path)
    candidates = _score_candidates(utterance_norm, manifest)
    if not candidates:
        return None

    best_name, best_score = candidates[0]
    if best_score < minimum_score:
        return None

    definition = manifest[best_name]
    args = parse_args(utterance_norm)
    if definition.args:
        args = {key: value for key, value in args.items() if key in definition.args}
    return best_name, args


__all__ = ["route", "load_intents", "IntentDefinition"]
