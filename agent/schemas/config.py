"""Lightweight configuration schemas for the local RPA agent.

The original project uses Pydantic for configuration validation. For the
purposes of the kata we provide small dataclass-based replacements that offer
just enough structure and validation for the surrounding modules and tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional


def _ensure_list(values: Optional[Iterable[str]]) -> List[str]:
    if values is None:
        return []
    return list(values)


@dataclass
class SelectorSchema:
    name: Optional[str] = None
    control_type: Optional[str] = None
    automation_id: Optional[str] = None
    role: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SelectorSchema":
        data = data or {}
        return cls(
            name=data.get("name"),
            control_type=data.get("controlType", data.get("control_type")),
            automation_id=data.get("automationId", data.get("automation_id")),
            role=data.get("role"),
        )


@dataclass
class WindowSchema:
    title_match: Optional[str] = None
    class_match: Optional[str] = None
    process_name: Optional[str] = None
    must_appear_within_ms: int = 10000
    bring_to_front: bool = True
    single_instance: Literal["detect", "force", "allow"] = "detect"
    activation_retry_ms: int = 250

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "WindowSchema":
        data = data or {}
        return cls(
            title_match=data.get("title_match"),
            class_match=data.get("class_match"),
            process_name=data.get("process_name"),
            must_appear_within_ms=int(data.get("must_appear_within_ms", 10000)),
            bring_to_front=bool(data.get("bring_to_front", True)),
            single_instance=data.get("single_instance", "detect"),
            activation_retry_ms=int(data.get("activation_retry_ms", 250)),
        )


@dataclass
class SandboxPolicySchema:
    filesystem_read: List[str] = field(default_factory=list)
    filesystem_write: List[str] = field(default_factory=list)
    network_allowlist: List[str] = field(default_factory=list)
    block_clipboard: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SandboxPolicySchema":
        data = data or {}
        return cls(
            filesystem_read=_ensure_list(data.get("filesystem_read")),
            filesystem_write=_ensure_list(data.get("filesystem_write")),
            network_allowlist=_ensure_list(data.get("network_allowlist")),
            block_clipboard=bool(data.get("block_clipboard", False)),
        )


@dataclass
class ElevationPolicySchema:
    allow: bool = False
    require_approval: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ElevationPolicySchema":
        data = data or {}
        return cls(
            allow=bool(data.get("allow", False)),
            require_approval=bool(data.get("require_approval", False)),
        )


@dataclass
class PolicySchema:
    idle_only: bool = True
    foreground_required: bool = True
    coordinate_clicks_allowed: bool = False
    max_runtime_sec: int = 0
    kill_on_timeout: bool = True
    approval_labels: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "PolicySchema":
        data = data or {}
        return cls(
            idle_only=bool(data.get("idle_only", True)),
            foreground_required=bool(data.get("foreground_required", True)),
            coordinate_clicks_allowed=bool(data.get("coordinate_clicks_allowed", False)),
            max_runtime_sec=int(data.get("max_runtime_sec", 0)),
            kill_on_timeout=bool(data.get("kill_on_timeout", True)),
            approval_labels=_ensure_list(data.get("approval_labels")),
        )


@dataclass
class HealthSchema:
    ready_selector: SelectorSchema = field(default_factory=SelectorSchema)
    ready_timeout_ms: int = 15000
    liveness_cpu_hung_ms: int = 20000
    liveness_window_unresponsive_ms: int = 8000

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "HealthSchema":
        data = data or {}
        return cls(
            ready_selector=SelectorSchema.from_dict(data.get("ready_selector")),
            ready_timeout_ms=int(data.get("ready_timeout_ms", 15000)),
            liveness_cpu_hung_ms=int(data.get("cpu_hung_ms", data.get("liveness_cpu_hung_ms", 20000))),
            liveness_window_unresponsive_ms=int(
                data.get("window_unresponsive_ms", data.get("liveness_window_unresponsive_ms", 8000))
            ),
        )


@dataclass
class AppHooksSchema:
    pre_start: List[str] = field(default_factory=list)
    post_start: List[str] = field(default_factory=list)
    pre_close: List[str] = field(default_factory=list)
    post_close: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "AppHooksSchema":
        data = data or {}
        return cls(
            pre_start=_ensure_list(data.get("pre_start")),
            post_start=_ensure_list(data.get("post_start")),
            pre_close=_ensure_list(data.get("pre_close")),
            post_close=_ensure_list(data.get("post_close")),
        )


@dataclass
class AppConfigSchema:
    description: str = ""
    enabled: bool = True
    path: Optional[str] = None
    shell: Optional[str] = None
    protocol: Optional[str] = None
    store: Optional[str] = None
    args: List[str] = field(default_factory=list)
    working_dir: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    inherit_env: bool = True
    window: WindowSchema = field(default_factory=WindowSchema)
    elevation: ElevationPolicySchema = field(default_factory=ElevationPolicySchema)
    sandbox: SandboxPolicySchema = field(default_factory=SandboxPolicySchema)
    policies: PolicySchema = field(default_factory=PolicySchema)
    hooks: AppHooksSchema = field(default_factory=AppHooksSchema)
    health: HealthSchema = field(default_factory=HealthSchema)
    presets: Dict[str, List[str]] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        launch_vectors = [self.path, self.shell, self.protocol, self.store]
        if not any(launch_vectors):
            raise ValueError("App configuration requires at least one launch vector (path/shell/protocol/store).")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AppConfigSchema":
        return cls(
            description=data.get("description", ""),
            enabled=bool(data.get("enabled", True)),
            path=data.get("path"),
            shell=data.get("shell"),
            protocol=data.get("protocol"),
            store=data.get("store"),
            args=list(data.get("args", [])),
            working_dir=data.get("working_dir"),
            env=dict(data.get("env", {})),
            inherit_env=bool(data.get("inherit_env", True)),
            window=WindowSchema.from_dict(data.get("window")),
            elevation=ElevationPolicySchema.from_dict(data.get("elevation")),
            sandbox=SandboxPolicySchema.from_dict(data.get("sandbox")),
            policies=PolicySchema.from_dict(data.get("policies")),
            hooks=AppHooksSchema.from_dict(data.get("hooks")),
            health=HealthSchema.from_dict(data.get("health")),
            presets={key: list(value) for key, value in dict(data.get("presets", {})).items()},
            tags=list(data.get("tags", [])),
        )


@dataclass
class AppRegistrySchema:
    apps: Dict[str, AppConfigSchema] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AppRegistrySchema":
        apps = {name: AppConfigSchema.from_dict(cfg) for name, cfg in dict(data).items()}
        return cls(apps=apps)

    @property
    def root(self) -> Dict[str, AppConfigSchema]:
        return self.apps


@dataclass
class LLMProviderSchema:
    type: Literal["api", "ui"]
    provider: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    endpoint: Optional[str] = None
    app: Optional[str] = None
    selectors: Dict[str, SelectorSchema] = field(default_factory=dict)
    scrape_strategy: Optional[Literal["uia", "clipboard", "ocr"]] = None
    max_chars: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LLMProviderSchema":
        selectors = {
            name: SelectorSchema.from_dict(selector)
            for name, selector in dict(data.get("selectors", {})).items()
        }
        return cls(
            type=data.get("type", "api"),
            provider=data.get("provider", ""),
            model=data.get("model"),
            api_key=data.get("api_key"),
            endpoint=data.get("endpoint"),
            app=data.get("app"),
            selectors=selectors,
            scrape_strategy=data.get("scrape_strategy"),
            max_chars=data.get("max_chars"),
        )


@dataclass
class LLMConfigSchema:
    active_provider: str
    providers: Dict[str, LLMProviderSchema]

    def __post_init__(self) -> None:
        if self.active_provider not in self.providers:
            raise ValueError(f"Active provider '{self.active_provider}' is not defined in providers list.")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LLMConfigSchema":
        providers = {
            name: LLMProviderSchema.from_dict(cfg)
            for name, cfg in dict(data.get("providers", {})).items()
        }
        return cls(active_provider=data.get("active_provider", ""), providers=providers)


@dataclass
class ProfileToggleSchema:
    idle_only: bool
    foreground_required: bool
    coordinate_clicks: bool
    elevation: bool
    network_allow: List[str]
    filesystem_allow: List[str]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProfileToggleSchema":
        return cls(
            idle_only=bool(data.get("idle_only", True)),
            foreground_required=bool(data.get("foreground_required", True)),
            coordinate_clicks=bool(data.get("coordinate_clicks", False)),
            elevation=bool(data.get("elevation", False)),
            network_allow=_ensure_list(data.get("network_allow")),
            filesystem_allow=_ensure_list(data.get("filesystem_allow")),
        )


@dataclass
class ProfileDefinitionSchema:
    description: str
    toggles: ProfileToggleSchema

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProfileDefinitionSchema":
        return cls(
            description=data.get("description", ""),
            toggles=ProfileToggleSchema.from_dict(data.get("toggles", {})),
        )


@dataclass
class ProfilesSchema:
    default: str
    definitions: Dict[str, ProfileDefinitionSchema]

    def __post_init__(self) -> None:
        if self.default not in self.definitions:
            raise ValueError("Default profile must exist in definitions.")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProfilesSchema":
        definitions = {
            name: ProfileDefinitionSchema.from_dict(cfg)
            for name, cfg in dict(data.get("definitions", {})).items()
        }
        return cls(default=data.get("default", ""), definitions=definitions)


@dataclass
class StateAccountSchema:
    cash_free: float = 0.0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "StateAccountSchema":
        data = data or {}
        return cls(cash_free=float(data.get("cash_free", 0.0)))


@dataclass
class StateSchema:
    accounts: Dict[str, StateAccountSchema] = field(default_factory=dict)
    market: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.accounts = {
            name: account if isinstance(account, StateAccountSchema) else StateAccountSchema.from_dict(account)
            for name, account in self.accounts.items()
        }
        self.market = dict(self.market)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StateSchema":
        accounts = {
            name: StateAccountSchema.from_dict(account)
            for name, account in dict(data.get("accounts", {})).items()
        }
        market = dict(data.get("market", {}))
        return cls(accounts=accounts, market=market)


@dataclass
class SafetySchema:
    panic_hotkey: str = "ctrl+alt+shift+esc"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SafetySchema":
        data = data or {}
        value = data.get("panic_hotkey", "ctrl+alt+shift+esc")
        if not isinstance(value, str):
            raise ValueError("Safety panic_hotkey must be a string.")
        value = value.strip()
        if not value:
            raise ValueError("Safety panic_hotkey must be a non-empty string.")
        return cls(panic_hotkey=value)
@dataclass
class FeatureFlagsSchema:
    chat_bridge: bool = True
    ocr_intents: bool = True

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "FeatureFlagsSchema":
        data = data or {}
        return cls(
            chat_bridge=bool(data.get("chat_bridge", True)),
            ocr_intents=bool(data.get("ocr_intents", True)),
        )

@dataclass
class IntentsSchema:
    directory: Path
    archive_directory: Path

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "IntentsSchema":
        return cls(
            directory=Path(data.get("directory")),
            archive_directory=Path(data.get("archive_directory")),
        )


@dataclass
class RecipesSchema:
    directory: Path

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RecipesSchema":
        return cls(directory=Path(data.get("directory")))


@dataclass
class ConnectorConfigSchema:
    profiles: ProfilesSchema
    intents: IntentsSchema
    recipes: RecipesSchema
    apps: AppRegistrySchema
    llm: LLMConfigSchema
    state: StateSchema
    safety: SafetySchema = field(default_factory=SafetySchema)
    features: FeatureFlagsSchema = field(default_factory=FeatureFlagsSchema)
    intent_map: Dict[str, Dict[str, str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ConnectorConfigSchema":
        return cls(
            profiles=ProfilesSchema.from_dict(data.get("profiles", {})),
            intents=IntentsSchema.from_dict(data.get("intents", {})),
            recipes=RecipesSchema.from_dict(data.get("recipes", {})),
            apps=AppRegistrySchema.from_dict(data.get("apps", {})),
            llm=LLMConfigSchema.from_dict(data.get("llm", {})),
            state=StateSchema.from_dict(data.get("state", {})),
            safety=SafetySchema.from_dict(data.get("safety", {})),
            features=FeatureFlagsSchema.from_dict(data.get("features", {})),
            intent_map={key: dict(value) for key, value in dict(data.get("intent_map", {})).items()},
        )

    @classmethod
    def parse_obj(cls, data: Mapping[str, Any]) -> "ConnectorConfigSchema":
        """Compatibility helper mirroring the original Pydantic API."""

        return cls.from_dict(data)


__all__ = [
    "ConnectorConfigSchema",
    "AppRegistrySchema",
    "AppConfigSchema",
    "ProfilesSchema",
    "LLMConfigSchema",
    "SafetySchema",
    "FeatureFlagsSchema",
    "IntentsSchema",
    "RecipesSchema",
    "StateSchema",
]
