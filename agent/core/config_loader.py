"""Configuration loader and validator for the local RPA agent."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

from agent.core.logger import configure_logging
from agent.schemas.config import ConnectorConfigSchema


class ConfigLoader:
    """Load and validate configuration files."""

    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path

    def load(self, filename: str | Path) -> ConnectorConfigSchema:
        """Load a connector configuration from YAML and validate it."""
        path = Path(filename)
        if not path.is_absolute():
            path = self._base_path / path

        with path.open("r", encoding="utf-8") as handle:
            raw_config = yaml.safe_load(handle)

        config = ConnectorConfigSchema.parse_obj(raw_config)
        return config


def bootstrap_config(path: str | Path) -> ConnectorConfigSchema:
    """Convenience helper to configure logging and load configuration."""
    configure_logging()
    loader = ConfigLoader(Path.cwd())
    config = loader.load(path)

    # Expand environment variables after validation for clarity.
    _expand_env_vars(config)
    return config


def _expand_env_vars(config: ConnectorConfigSchema) -> None:
    """Recursively expand environment variables in selected config fields."""

    for provider in config.llm.providers.values():
        if provider.api_key:
            provider.api_key = os.path.expandvars(provider.api_key)
        if provider.endpoint:
            provider.endpoint = os.path.expandvars(provider.endpoint)

    for profile in config.profiles.definitions.values():
        profile.toggles.network_allow = [os.path.expandvars(p) for p in profile.toggles.network_allow]
        profile.toggles.filesystem_allow = [os.path.expandvars(p) for p in profile.toggles.filesystem_allow]

    config.intents.directory = Path(os.path.expandvars(str(config.intents.directory)))
    config.intents.archive_directory = Path(os.path.expandvars(str(config.intents.archive_directory)))
    config.recipes.directory = Path(os.path.expandvars(str(config.recipes.directory)))

    for mapping in config.intent_map.values():
        if "recipe" in mapping:
            mapping["recipe"] = os.path.expandvars(mapping["recipe"])


__all__ = ["ConfigLoader", "bootstrap_config"]
