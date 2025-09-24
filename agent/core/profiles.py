"""Runtime profile and toggle management."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Iterator

from agent.schemas.config import ConnectorConfigSchema, ProfileDefinitionSchema


@dataclass(frozen=True)
class RuntimeToggles:
    idle_only: bool
    foreground_required: bool
    coordinate_clicks: bool
    elevation: bool
    network_allow: tuple[str, ...]
    filesystem_allow: tuple[str, ...]


class ProfileManager:
    """Manage active profile and runtime toggles for the agent."""

    def __init__(self, profiles: Dict[str, ProfileDefinitionSchema], default: str) -> None:
        if default not in profiles:
            raise ValueError(f"Default profile '{default}' is not defined.")
        self._profiles = profiles
        self._active = default
        self._overrides: Dict[str, bool | tuple[str, ...]] = {}

    @property
    def active_profile(self) -> str:
        return self._active

    def activate(self, profile: str) -> None:
        if profile not in self._profiles:
            raise KeyError(f"Profile '{profile}' not defined")
        self._active = profile
        self._overrides.clear()

    def iter_profiles(self) -> Iterator[str]:
        yield from self._profiles

    def set_toggle(self, name: str, value: bool) -> None:
        definition = getattr(self.current_toggles(), name, None)
        if definition is None:
            raise AttributeError(f"Unknown toggle '{name}'")
        self._overrides[name] = value

    def current_toggles(self) -> RuntimeToggles:
        profile = self._profiles[self._active]
        toggles = profile.toggles
        override_idle = self._overrides.get("idle_only", toggles.idle_only)
        override_fg = self._overrides.get("foreground_required", toggles.foreground_required)
        override_coord = self._overrides.get("coordinate_clicks", toggles.coordinate_clicks)
        override_elev = self._overrides.get("elevation", toggles.elevation)
        override_network = self._overrides.get("network_allow", tuple(toggles.network_allow))
        override_fs = self._overrides.get("filesystem_allow", tuple(toggles.filesystem_allow))
        return RuntimeToggles(
            idle_only=bool(override_idle),
            foreground_required=bool(override_fg),
            coordinate_clicks=bool(override_coord),
            elevation=bool(override_elev),
            network_allow=tuple(override_network),
            filesystem_allow=tuple(override_fs),
        )

    @classmethod
    def from_config(cls, config: ConnectorConfigSchema) -> "ProfileManager":
        return cls(config.profiles.definitions, config.profiles.default)


__all__ = ["ProfileManager", "RuntimeToggles"]
