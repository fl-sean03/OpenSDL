from __future__ import annotations

import json
import math
import re
from enum import StrEnum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Literal, Mapping, Self

from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

from opensdl_core import OpenSDLModel


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")


class Handedness(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class UpAxis(StrEnum):
    X = "X"
    Y = "Y"
    Z = "Z"


class TwinPhase(StrEnum):
    STARTED = "started"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERVENTION_REQUIRED = "intervention_required"


class TwinAction(StrEnum):
    HIGHLIGHT = "highlight"
    TRANSFER = "transfer"
    PLAY_CLIP = "play_clip"
    SET_PROPERTY = "set_property"


EVENT_PHASES: dict[str, TwinPhase] = {
    "TaskStarted": TwinPhase.STARTED,
    "TaskRetrying": TwinPhase.RETRYING,
    "TaskSucceeded": TwinPhase.SUCCEEDED,
    "TaskFailed": TwinPhase.FAILED,
    "TaskCancelled": TwinPhase.CANCELLED,
    "TaskInterventionRequired": TwinPhase.INTERVENTION_REQUIRED,
    "TaskRecoveryRequired": TwinPhase.INTERVENTION_REQUIRED,
}


def validate_json_pointer(value: str) -> str:
    """Validate an RFC 6901 JSON Pointer used for read-only value selection."""

    if value == "":
        return value
    if not value.startswith("/"):
        raise ValueError("JSON Pointer must be empty or start with '/'")
    for token in value.split("/")[1:]:
        offset = 0
        while offset < len(token):
            if token[offset] != "~":
                offset += 1
                continue
            if offset + 1 >= len(token) or token[offset + 1] not in {"0", "1"}:
                raise ValueError("JSON Pointer '~' escapes must be '~0' or '~1'")
            offset += 2
    return value


def validate_safe_relative_path(value: str) -> str:
    """Require a normalized POSIX path that cannot escape its definition directory."""

    normalized = value.strip()
    if not normalized:
        raise ValueError("scene path cannot be blank")
    if "\x00" in normalized:
        raise ValueError("scene path cannot contain NUL")
    if "\\" in normalized:
        raise ValueError("scene path must use forward slashes")
    if WINDOWS_DRIVE_PATTERN.match(normalized) or "://" in normalized:
        raise ValueError("scene path must be relative, not a drive path or URI")
    if normalized.startswith("//") or normalized.endswith("/") or "//" in normalized:
        raise ValueError("scene path must be a normalized file path")
    candidate = PurePosixPath(normalized)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("scene path must stay within the definition directory")
    if candidate.as_posix() != normalized or normalized.startswith("./"):
        raise ValueError("scene path must be normalized")
    return normalized


def _nonblank(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} cannot be blank")
    return normalized


def _json_compatible(value: Any, label: str) -> Any:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain finite JSON-compatible values") from exc
    return value


def _freeze_json(value: Any) -> Any:
    """Recursively freeze a value that has already passed JSON validation."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def copy_json_value(value: Any) -> Any:
    """Return a mutable, JSON-serializable copy of a frozen JSON value."""

    if isinstance(value, Mapping):
        return {key: copy_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [copy_json_value(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        copy_json_value(value),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _freeze_json_mapping(value: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    _json_compatible(value, label)
    return _freeze_json(value)


def _finite_vector(
    value: tuple[float, float, float],
    label: str,
) -> tuple[float, float, float]:
    if not all(math.isfinite(component) for component in value):
        raise ValueError(f"{label} must contain only finite coordinates")
    return value


class FrozenTwinModel(OpenSDLModel):
    """Immutable base for the public twin contract."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        """Revalidate copies so updates cannot inject mutable nested values."""

        del deep  # Revalidation already rebuilds every nested contract value.
        data = self.model_dump(mode="python", round_trip=True)
        if update is not None:
            data.update(update)
        return self.__class__.model_validate(data)


class CoordinateFrame(FrozenTwinModel):
    unit: Literal["m"]
    handedness: Handedness
    up_axis: UpAxis = Field(alias="upAxis")
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @field_validator("handedness")
    @classmethod
    def handedness_must_be_supported(cls, value: Handedness) -> Handedness:
        if value != Handedness.RIGHT:
            raise ValueError("v0alpha1 coordinate frames must be right-handed")
        return value

    @field_validator("origin")
    @classmethod
    def origin_must_be_finite_zero(
        cls,
        value: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        _finite_vector(value, "coordinate-frame origin")
        if value != (0.0, 0.0, 0.0):
            raise ValueError("v0alpha1 coordinate-frame origin must be [0, 0, 0]")
        return value


class TwinScene(FrozenTwinModel):
    path: str
    sha256: str

    @field_validator("path")
    @classmethod
    def path_must_be_safe_and_relative(cls, value: str) -> str:
        return validate_safe_relative_path(value)

    @field_validator("sha256", mode="before")
    @classmethod
    def sha256_must_be_hex(cls, value: Any) -> str:
        normalized = str(value).strip().lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("scene sha256 must contain exactly 64 hexadecimal characters")
        return normalized


class TwinEntity(FrozenTwinModel):
    id: str
    node: str
    resources: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("id", "node")
    @classmethod
    def identifiers_must_not_be_blank(cls, value: str, info: Any) -> str:
        return _nonblank(value, info.field_name)

    @field_validator("resources")
    @classmethod
    def resources_must_be_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_nonblank(item, "resource identifier") for item in value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("entity resources must be unique")
        return normalized


class TwinAnchor(FrozenTwinModel):
    id: str
    position: tuple[float, float, float]
    node: str | None = None

    @field_validator("id")
    @classmethod
    def id_must_not_be_blank(cls, value: str) -> str:
        return _nonblank(value, "anchor id")

    @field_validator("node")
    @classmethod
    def node_must_not_be_blank(cls, value: str | None) -> str | None:
        return _nonblank(value, "anchor node") if value is not None else None

    @field_validator("position")
    @classmethod
    def position_must_be_finite(
        cls,
        value: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        return _finite_vector(value, "anchor position")


class ProjectionMatch(FrozenTwinModel):
    event_type: str = Field(alias="eventType")
    capability: str
    phase: TwinPhase

    @field_validator("event_type", "capability")
    @classmethod
    def values_must_not_be_blank(cls, value: str, info: Any) -> str:
        return _nonblank(value, info.field_name)

    @model_validator(mode="after")
    def canonical_event_phase_must_agree(self) -> "ProjectionMatch":
        canonical = EVENT_PHASES.get(self.event_type)
        if canonical is not None and canonical != self.phase:
            raise ValueError(
                f"event type {self.event_type!r} has phase {canonical.value!r}, "
                f"not {self.phase.value!r}"
            )
        return self


class ProjectionRule(FrozenTwinModel):
    id: str
    match: ProjectionMatch
    action: TwinAction
    target: str
    parameters: Mapping[str, Any] = Field(default_factory=lambda: MappingProxyType({}))
    parameter_pointers: Mapping[str, str] = Field(
        default_factory=lambda: MappingProxyType({}),
        alias="parameterPointers",
    )

    @field_validator("id", "target")
    @classmethod
    def identifiers_must_not_be_blank(cls, value: str, info: Any) -> str:
        return _nonblank(value, info.field_name)

    @field_validator("parameters")
    @classmethod
    def parameters_must_be_json(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return _freeze_json_mapping(value, "projection parameters")

    @field_serializer("parameters")
    def serialize_parameters(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return copy_json_value(value)

    @field_validator("parameter_pointers")
    @classmethod
    def pointers_must_be_valid(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        normalized: dict[str, str] = {}
        for name, pointer in value.items():
            key = _nonblank(name, "projection parameter name")
            normalized[key] = validate_json_pointer(pointer)
        return MappingProxyType(normalized)

    @field_serializer("parameter_pointers")
    def serialize_parameter_pointers(self, value: Mapping[str, str]) -> dict[str, str]:
        return dict(value)

    @model_validator(mode="after")
    def action_parameters_must_be_complete(self) -> "ProjectionRule":
        overlap = set(self.parameters) & set(self.parameter_pointers)
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ValueError(f"static and pointer parameters overlap: {names}")
        available = set(self.parameters) | set(self.parameter_pointers)
        required: dict[TwinAction, set[str]] = {
            TwinAction.HIGHLIGHT: set(),
            TwinAction.TRANSFER: {"source", "destination"},
            TwinAction.PLAY_CLIP: {"clip"},
            TwinAction.SET_PROPERTY: {"property", "value"},
        }
        missing = required[self.action] - available
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"action {self.action.value!r} requires parameters: {names}")
        return self


class AnimationBinding(FrozenTwinModel):
    id: str
    action: TwinAction
    parameter_match: Mapping[str, Any] = Field(alias="parameterMatch")
    frame_start: int = Field(ge=0, alias="frameStart")
    frame_end: int = Field(ge=0, alias="frameEnd")

    @field_validator("id")
    @classmethod
    def id_must_not_be_blank(cls, value: str) -> str:
        return _nonblank(value, "animation binding id")

    @field_validator("parameter_match")
    @classmethod
    def parameter_match_must_be_nonempty_json(
        cls,
        value: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if not value:
            raise ValueError("animation parameterMatch cannot be empty")
        return _freeze_json_mapping(value, "animation parameterMatch")

    @field_serializer("parameter_match")
    def serialize_parameter_match(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return copy_json_value(value)

    @model_validator(mode="after")
    def frame_range_must_increase(self) -> "AnimationBinding":
        if self.frame_end <= self.frame_start:
            raise ValueError("animation binding frameEnd must be greater than frameStart")
        return self


class AnimationTimeline(FrozenTwinModel):
    frame_rate: float = Field(gt=0, alias="frameRate")
    frame_start: int = Field(ge=0, alias="frameStart")
    frame_end: int = Field(ge=0, alias="frameEnd")
    bindings: tuple[AnimationBinding, ...] = Field(min_length=1)

    @field_validator("frame_rate", mode="before")
    @classmethod
    def frame_rate_must_be_finite(cls, value: Any) -> Any:
        try:
            finite = math.isfinite(float(value))
        except (TypeError, ValueError, OverflowError):
            return value
        if not finite:
            raise ValueError("animation frameRate must be finite")
        return value

    @model_validator(mode="after")
    def bindings_must_be_unique_and_in_range(self) -> "AnimationTimeline":
        if self.frame_end <= self.frame_start:
            raise ValueError("animation timeline frameEnd must be greater than frameStart")
        binding_ids = [binding.id for binding in self.bindings]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("animation binding ids must be unique")
        for binding in self.bindings:
            if binding.frame_start < self.frame_start or binding.frame_end > self.frame_end:
                raise ValueError(
                    f"animation binding {binding.id!r} must stay within the timeline range"
                )
        for index, left in enumerate(self.bindings):
            for right in self.bindings[index + 1 :]:
                if left.action != right.action:
                    continue
                shared = set(left.parameter_match) & set(right.parameter_match)
                compatible = all(
                    _canonical_json(left.parameter_match[name])
                    == _canonical_json(right.parameter_match[name])
                    for name in shared
                )
                if compatible:
                    raise ValueError(
                        f"animation bindings {left.id!r} and {right.id!r} are ambiguous"
                    )
        return self


class TwinDefinition(FrozenTwinModel):
    api_version: Literal["opensdl.dev/v0alpha1"] = Field(
        default="opensdl.dev/v0alpha1",
        alias="apiVersion",
    )
    kind: Literal["DigitalTwin"] = "DigitalTwin"
    version: str
    revision: str
    coordinate_frame: CoordinateFrame = Field(alias="coordinateFrame")
    scene: TwinScene
    entities: tuple[TwinEntity, ...]
    anchors: tuple[TwinAnchor, ...] = Field(default_factory=tuple)
    projection_rules: tuple[ProjectionRule, ...] = Field(
        default_factory=tuple,
        alias="projectionRules",
    )
    animation_timeline: AnimationTimeline | None = Field(
        default=None,
        alias="animationTimeline",
    )

    @field_validator("version", "revision")
    @classmethod
    def versions_must_not_be_blank(cls, value: str, info: Any) -> str:
        return _nonblank(value, info.field_name)

    @model_validator(mode="after")
    def references_must_be_unique_and_resolved(self) -> "TwinDefinition":
        entity_ids = [item.id for item in self.entities]
        entity_nodes = [item.node for item in self.entities]
        anchor_ids = [item.id for item in self.anchors]
        anchor_nodes = [item.node for item in self.anchors if item.node is not None]
        rule_ids = [item.id for item in self.projection_rules]

        for label, values in (
            ("entity ids", entity_ids),
            ("entity nodes", entity_nodes),
            ("anchor ids", anchor_ids),
            ("anchor nodes", anchor_nodes),
            ("projection rule ids", rule_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
        overlap = set(entity_ids) & set(anchor_ids)
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ValueError(f"entity and anchor ids overlap: {names}")

        known_entities = set(entity_ids)
        known_anchors = set(anchor_ids)
        for rule in self.projection_rules:
            if rule.target not in known_entities:
                raise ValueError(
                    f"projection rule {rule.id!r} targets unknown entity {rule.target!r}"
                )
            if rule.action == TwinAction.TRANSFER:
                for name in ("source", "destination"):
                    if name not in rule.parameters:
                        continue
                    value = rule.parameters[name]
                    if not isinstance(value, str) or value not in known_anchors:
                        raise ValueError(
                            f"projection rule {rule.id!r} uses unknown static {name} "
                            f"anchor {value!r}"
                        )
        return self


class TwinCue(FrozenTwinModel):
    id: str
    sequence: int = Field(ge=0)
    source_event_id: str = Field(alias="sourceEventId")
    run_id: str | None = Field(default=None, alias="runId")
    task_id: str = Field(alias="taskId")
    capability_id: str = Field(alias="capabilityId")
    occurred_at: str = Field(alias="occurredAt", json_schema_extra={"format": "date-time"})
    phase: TwinPhase
    action: TwinAction
    target: str
    parameters: Mapping[str, Any] = Field(default_factory=lambda: MappingProxyType({}))

    @field_validator("id", "source_event_id", "task_id", "capability_id", "occurred_at", "target")
    @classmethod
    def identifiers_must_not_be_blank(cls, value: str, info: Any) -> str:
        return _nonblank(value, info.field_name)

    @field_validator("parameters")
    @classmethod
    def cue_parameters_must_be_json(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return _freeze_json_mapping(value, "cue parameters")

    @field_serializer("parameters")
    def serialize_parameters(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return copy_json_value(value)
