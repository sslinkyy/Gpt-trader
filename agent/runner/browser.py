"""Playwright-based browser helper (stub implementation)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger(__name__)


@dataclass
class BrowserContextConfig:
    download_dir: Path
    headless: bool = False


class BrowserManager:
    """Simplified wrapper around Playwright actions."""

    def __init__(self, config: BrowserContextConfig) -> None:
        self._config = config
        self._page = None

    def launch(self) -> None:
        LOGGER.info(
            "[demo] Would launch Playwright browser headless=%s download_dir=%s",
            self._config.headless,
            self._config.download_dir,
        )
        self._config.download_dir.mkdir(parents=True, exist_ok=True)

    def goto(self, url: str) -> None:
        LOGGER.info("[demo] Would navigate browser to %s", url)

    def click(self, selector: str) -> None:
        LOGGER.info("[demo] Would click DOM selector %s", selector)

    def type(self, selector: str, text: str) -> None:
        LOGGER.info("[demo] Would type '%s' into selector %s", text, selector)

    def expect_download(self, filename: str) -> Path:
        path = self._config.download_dir / filename
        LOGGER.info("[demo] Would wait for download and save to %s", path)
        return path

    def close(self) -> None:
        LOGGER.info("[demo] Would close browser context")


__all__ = ["BrowserManager", "BrowserContextConfig"]
