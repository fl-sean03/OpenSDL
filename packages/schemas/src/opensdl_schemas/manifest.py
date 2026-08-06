from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ConfigDict, Field, model_validator

from opensdl_core import CapabilityDefinition, LabMetadata, OpenSDLModel, Resource


class DatabaseConfig(OpenSDLModel):
    url: str = "sqlite:///./.opensdl/opensdl.db"


class ArtifactStoreConfig(OpenSDLModel):
    root: str = ".opensdl/artifacts"


class StorageConfig(OpenSDLModel):
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    artifacts: ArtifactStoreConfig = Field(default_factory=ArtifactStoreConfig)


class RuntimeConfig(OpenSDLModel):
    max_concurrency: int = Field(default=4, gt=0)
    default_timeout_seconds: float = Field(default=60.0, gt=0)
    lease_ttl_seconds: float = Field(default=300.0, gt=0)


class AdapterConfig(OpenSDLModel):
    name: str
    plugin: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class CapabilityBinding(OpenSDLModel):
    """Binds one capability identifier to the adapter that must provide it.

    A binding selects and enables; it carries no configuration. Configuration reaches an executor
    through `spec.adapters[].config`, which the composition root passes to the plugin factory.

    There was a `config` field here. Nothing ever read it, and a per-capability `config:` is
    precisely where an operator writes operating limits — the deployment obligation `SAFETY.md`
    describes. Enforcing an operating envelope is unbuilt design work, so the field is removed
    rather than left absorbing safety configuration in silence.
    """

    capability: str
    adapter: str
    enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def reject_binding_configuration(cls, data: Any) -> Any:
        if isinstance(data, dict) and "config" in data:
            raise ValueError(
                "capability bindings carry no configuration: 'config' was accepted and never "
                "read. Adapter configuration belongs in spec.adapters[].config. OpenSDL has no "
                "operating-envelope mechanism, so operating limits belong in the deployment "
                "controls SAFETY.md describes, not in this manifest."
            )
        return data


class PolicyRuleSpec(OpenSDLModel):
    id: str
    effect: Literal["allow", "deny"]
    capability: str = "*"
    environments: list[str] = Field(default_factory=lambda: ["*"])
    operators: list[str] = Field(default_factory=lambda: ["*"])
    risk_classes: list[str] = Field(default_factory=lambda: ["*"])
    reason: str = ""
    priority: int = 100


class PolicyConfig(OpenSDLModel):
    default_effect: Literal["allow", "deny"] = "deny"
    version: str = "local/v0alpha1"
    rules: list[PolicyRuleSpec] = Field(default_factory=list)


class DomainPackConfig(OpenSDLModel):
    name: str
    plugin: str
    config: dict[str, Any] = Field(default_factory=dict)


class TwinConfig(OpenSDLModel):
    definition: str
    viewer_root: str | None = None


class LabSpec(OpenSDLModel):
    environment: str = "simulation"
    storage: StorageConfig = Field(default_factory=StorageConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    adapters: list[AdapterConfig] = Field(default_factory=list)
    capabilities: list[CapabilityBinding] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    domain_packs: list[DomainPackConfig] = Field(default_factory=list)
    twin: TwinConfig | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)


class LabManifest(OpenSDLModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_assignment=True)

    api_version: Literal["opensdl.dev/v0alpha1"] = Field(
        default="opensdl.dev/v0alpha1", alias="apiVersion"
    )
    kind: Literal["Laboratory"] = "Laboratory"
    metadata: LabMetadata
    spec: LabSpec


def load_manifest(path: str | Path) -> LabManifest:
    source = Path(path)
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest must contain a mapping: {source}")
    return LabManifest.model_validate(data)


def dump_manifest(manifest: LabManifest, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = manifest.model_dump(mode="json", by_alias=True, exclude_none=True)
    target.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def embedded_capability_schema() -> dict[str, Any]:
    return CapabilityDefinition.model_json_schema()
