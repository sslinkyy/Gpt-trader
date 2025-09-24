"""Windows-first local RPA agent scaffold."""

from __future__ import annotations

from typing import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Entry-point helper that defers importing heavy CLI dependencies."""

    from agent.cli import main as _cli_main

    return _cli_main(list(argv) if argv is not None else None)


__all__ = ["main"]
