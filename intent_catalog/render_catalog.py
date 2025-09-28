from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import yaml


@dataclass
class IntentEntry:
    name: str
    recipe: str
    description: str = ""
    args: List[str] = None


def load_manifest(path: Path) -> List[IntentEntry]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries: List[IntentEntry] = []
    for row in data.get("intents", []):
        entries.append(
            IntentEntry(
                name=row.get("intent", ""),
                recipe=row.get("recipe", ""),
                description=row.get("description", ""),
                args=list(row.get("args", [])),
            )
        )
    return entries


def format_table(entries: Iterable[IntentEntry]) -> str:
    headers = ["Intent", "Recipe", "Description"]
    rows = [[e.name, e.recipe, e.description] for e in entries]

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(row: List[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) + " |"

    separator = "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"

    lines = [fmt(headers), separator]
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the intent manifest in various formats")
    parser.add_argument("manifest", type=Path, help="Path to manifest.yml")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of markdown table")
    args = parser.parse_args()

    entries = load_manifest(args.manifest)
    if args.json:
        print(json.dumps([e.__dict__ for e in entries], indent=2))
    else:
        print(format_table(entries))


if __name__ == "__main__":
    main()
