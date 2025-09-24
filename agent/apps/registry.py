"""Application registry handling launch/focus semantics."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from agent.schemas.config import AppConfigSchema, AppRegistrySchema

LOGGER = logging.getLogger(__name__)


@dataclass
class ApplicationDefinition:
    name: str
    config: AppConfigSchema

    def require_enabled(self) -> None:
        if not self.config.enabled:
            raise RuntimeError(f"Application '{self.name}' is disabled by policy.")


class ApplicationRegistry:
    """Provide access to application definitions and lifecycle hooks."""

    def __init__(self, apps: Dict[str, AppConfigSchema]):
        self._apps = {name: ApplicationDefinition(name, cfg) for name, cfg in apps.items()}

    def get(self, name: str) -> ApplicationDefinition:
        if name not in self._apps:
            raise KeyError(f"Application '{name}' is not registered.")
        return self._apps[name]

    @classmethod
    def from_schema(cls, schema: AppRegistrySchema) -> "ApplicationRegistry":
        return cls(schema.root)


__all__ = ["ApplicationRegistry", "ApplicationDefinition"]
