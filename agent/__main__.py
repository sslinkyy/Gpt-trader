"""Allow running the agent package via ``python -m agent``."""
from __future__ import annotations

from agent.cli import main


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
