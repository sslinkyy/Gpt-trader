"""Centralized logging utilities for the local RPA agent."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

_DEFAULT_FORMAT = (
    "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)


def configure_logging(level: int = logging.INFO, logfile: Optional[Path] = None) -> None:
    """Configure logging for the agent.

    Parameters
    ----------
    level:
        Logging level to configure. Defaults to :data:`logging.INFO`.
    logfile:
        Optional path to write a rotating log. When omitted, logs are emitted to
        stdout only.
    """

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicate logs when re-configuring.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    root_logger.addHandler(stream_handler)

    if logfile is not None:
        logfile.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(logfile, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
        root_logger.addHandler(file_handler)


__all__ = ["configure_logging"]
