"""Pydantic-based configuration schemas for the local RPA agent."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FieldValidationInfo,
    RootModel,
    field_validator,
    model_validator,
)


class SelectorSchema(BaseModel):
    """Represents a UI selector for UI Automation interactions."""

    name: Optional[str] = None
    control_type: Optional[str] = Field(None, alias="controlType")
    automation_id: Optional[str] = Field(None, alias="automationId")
    role: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class WindowSchema(BaseModel):
    title_match: Optional[str] = None
    class_match: Optional[str] = None
    process_name: Optional[str] = None
    must_appear_within_ms: int = 10000
    bring_to_front: bool = True
    single_instance: Literal["detect", "force", "allow"] = "detect"
    activation_retry_ms: int = 250


class SandboxPolicySchema(BaseModel):
    filesystem_read: List[str] = Field(default_factory=list)
    filesystem_write: List[str] = Field(default_factory=list)
    network_allowlist: List[str] = Field(default_factory=list)
    block_clipboard: bool = False


class ElevationPolicySchema(BaseModel):
    allow: bool = False
    require_approval: bool = False


class PolicySchema(BaseModel):
    idle_only: bool = True
    foreground_required: bool = True
    coordinate_clicks_allowed: bool = False
    max_runtime_sec: int = 0
    kill_on_timeout: bool = True
    approval_labels: List[str] = Field(default_factory=list)


class HealthSchema(BaseModel):
    ready_selector: SelectorSchema = Field(default_factory=SelectorSchema)
    ready_timeout_ms: int = 15000
    liveness_cpu_hung_ms: int = Field(20000, alias="cpu_hung_ms")
    liveness_window_unresponsive_ms: int = Field(8000, alias="window_unresponsive_ms")

    model_config = ConfigDict(populate_by_name=True)


class AppHooksSchema(BaseModel):
    pre_start: List[str] = Field(default_factory=list)
    post_start: List[str] = Field(default_factory=list)
    pre_close: List[str] = Field(default_factory=list)
    post_close: List[str] = Field(default_factory=list)


class AppConfigSchema(BaseModel):
    description: str = ""
    enabled: bool = True
    path: Optional[str] = None
    shell: Optional[str] = None
    protocol: Optional[str] = None
    store: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    working_dir: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    inherit_env: bool = True
    window: WindowSchema = Field(default_factory=WindowSchema)
    elevation: ElevationPolicySchema = Field(default_factory=ElevationPolicySchema)
    sandbox: SandboxPolicySchema = Field(default_factory=SandboxPolicySchema)
    policies: PolicySchema = Field(default_factory=PolicySchema)
    hooks: AppHooksSchema = Field(default_factory=AppHooksSchema)
    health: HealthSchema = Field(default_factory=HealthSchema)
    presets: Dict[str, List[str]] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_launch_vector(cls, values: "AppConfigSchema") -> "AppConfigSchema":
        launch_fields = [values.path, values.shell, values.protocol, values.store]
        if not any(launch_fields):
            raise ValueError("App configuration requires at least one launch vector (path/shell/protocol/store).")
        return values


class AppRegistrySchema(RootModel[Dict[str, AppConfigSchema]]):
    pass


class LLMProviderSchema(BaseModel):
    type: Literal["api", "ui"]
    provider: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    endpoint: Optional[str] = None
    app: Optional[str] = None
    selectors: Dict[str, SelectorSchema] = Field(default_factory=dict)
    scrape_strategy: Optional[Literal["uia", "clipboard", "ocr"]] = None
    max_chars: Optional[int] = None


class LLMConfigSchema(BaseModel):
    active_provider: str
    providers: Dict[str, LLMProviderSchema]

    @model_validator(mode="after")
    def validate_active_provider(self) -> "LLMConfigSchema":
        if self.active_provider not in self.providers:
            raise ValueError(f"Active provider '{self.active_provider}' is not defined in providers list.")
        return self


class ProfileToggleSchema(BaseModel):
    idle_only: bool
    foreground_required: bool
    coordinate_clicks: bool
    elevation: bool
    network_allow: List[str]
    filesystem_allow: List[str]


class ProfileDefinitionSchema(BaseModel):
    description: str
    toggles: ProfileToggleSchema


class ProfilesSchema(BaseModel):
    default: str
    definitions: Dict[str, ProfileDefinitionSchema]

    @model_validator(mode="after")
    def ensure_default_exists(self) -> "ProfilesSchema":
        if self.default not in self.definitions:
            raise ValueError("Default profile must exist in definitions.")
        return self


class StateAccountSchema(BaseModel):
    cash_free: float = 0.0


class StateSchema(BaseModel):
    accounts: Dict[str, StateAccountSchema] = Field(default_factory=dict)
    market: Dict[str, str] = Field(default_factory=dict)


class IntentsSchema(BaseModel):
    directory: Path
    archive_directory: Path


class RecipesSchema(BaseModel):
    directory: Path


class ConnectorConfigSchema(BaseModel):
    profiles: ProfilesSchema
    intents: IntentsSchema
    recipes: RecipesSchema
    apps: AppRegistrySchema
    llm: LLMConfigSchema
    state: StateSchema
    intent_map: Dict[str, Dict[str, str]] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


__all__ = [
    "ConnectorConfigSchema",
    "AppRegistrySchema",
    "AppConfigSchema",
    "ProfilesSchema",
    "LLMConfigSchema",
    "IntentsSchema",
    "RecipesSchema",
    "StateSchema",
]
