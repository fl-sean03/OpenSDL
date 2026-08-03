from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from opensdl_core import EventRecord

from .models import (
    EVENT_PHASES,
    ProjectionRule,
    TwinAction,
    TwinCue,
    TwinDefinition,
    TwinPhase,
    copy_json_value,
)


class TwinProjectionError(ValueError):
    """Durable events could not be projected through a valid twin definition."""


def project_events(
    definition: TwinDefinition,
    events: Iterable[EventRecord],
    task_capabilities: Mapping[str, str],
) -> tuple[TwinCue, ...]:
    """Deterministically project persisted events into immutable visual cues."""

    ordered = sorted(events, key=_event_sort_key)
    event_ids = [item.id for item in ordered]
    if len(event_ids) != len(set(event_ids)):
        raise TwinProjectionError("event identifiers must be unique")

    rules_by_type: dict[str, list[ProjectionRule]] = {}
    for rule in definition.projection_rules:
        rules_by_type.setdefault(rule.match.event_type, []).append(rule)

    anchor_ids = {item.id for item in definition.anchors}
    cues: list[TwinCue] = []
    for event in ordered:
        candidate_rules = rules_by_type.get(event.type, [])
        if not candidate_rules:
            continue
        if event.task_id is None:
            raise TwinProjectionError(
                f"event {event.id!r} matches projection rules but has no task id"
            )
        try:
            capability_id = task_capabilities[event.task_id]
        except KeyError as exc:
            raise TwinProjectionError(
                f"event {event.id!r} references task {event.task_id!r} without a capability mapping"
            ) from exc
        phase = _event_phase(event)
        envelope = {
            "event": event.model_dump(mode="json"),
            "task": {"id": event.task_id, "capability": capability_id},
            "phase": phase.value,
        }
        for rule in candidate_rules:
            if rule.match.capability != capability_id or rule.match.phase != phase:
                continue
            parameters = copy_json_value(rule.parameters)
            for name, pointer in rule.parameter_pointers.items():
                parameters[name] = copy_json_value(resolve_json_pointer(envelope, pointer))
            _validate_resolved_action(rule, parameters, anchor_ids)
            cues.append(
                TwinCue(
                    id=_cue_id(definition.revision, event.id, rule.id),
                    sequence=len(cues),
                    sourceEventId=event.id,
                    runId=event.run_id,
                    taskId=event.task_id,
                    capabilityId=capability_id,
                    occurredAt=event.occurred_at.isoformat(),
                    phase=phase,
                    action=rule.action,
                    target=rule.target,
                    parameters=parameters,
                )
            )
    return tuple(cues)


def resolve_json_pointer(document: Any, pointer: str) -> Any:
    """Resolve a previously validated RFC 6901 JSON Pointer."""

    if pointer == "":
        return document
    current = document
    for encoded in pointer.split("/")[1:]:
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                raise TwinProjectionError(f"JSON Pointer {pointer!r} has no key {token!r}")
            current = current[token]
            continue
        if isinstance(current, list):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                raise TwinProjectionError(
                    f"JSON Pointer {pointer!r} has invalid array index {token!r}"
                )
            index = int(token)
            if index >= len(current):
                raise TwinProjectionError(
                    f"JSON Pointer {pointer!r} array index {index} is out of range"
                )
            current = current[index]
            continue
        raise TwinProjectionError(
            f"JSON Pointer {pointer!r} cannot traverse scalar value at {token!r}"
        )
    return current


def _event_phase(event: EventRecord) -> TwinPhase:
    canonical = EVENT_PHASES.get(event.type)
    if canonical is not None:
        return canonical
    raw = event.payload.get("phase")
    try:
        return TwinPhase(raw)
    except (TypeError, ValueError) as exc:
        raise TwinProjectionError(f"event {event.id!r} has no recognized projection phase") from exc


def _event_sort_key(event: EventRecord) -> tuple[datetime, str]:
    occurred_at = event.occurred_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return occurred_at.astimezone(UTC), event.id


def _validate_resolved_action(
    rule: ProjectionRule,
    parameters: dict[str, Any],
    anchor_ids: set[str],
) -> None:
    try:
        json.dumps(parameters, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TwinProjectionError(
            f"projection rule {rule.id!r} produced non-JSON parameters"
        ) from exc

    if rule.action == TwinAction.TRANSFER:
        for name in ("source", "destination"):
            value = parameters[name]
            if not isinstance(value, str) or value not in anchor_ids:
                raise TwinProjectionError(
                    f"projection rule {rule.id!r} resolved {name} to unknown anchor {value!r}"
                )
    elif rule.action == TwinAction.PLAY_CLIP:
        if not isinstance(parameters["clip"], str) or not parameters["clip"].strip():
            raise TwinProjectionError(
                f"projection rule {rule.id!r} resolved an invalid animation clip"
            )
    elif rule.action == TwinAction.SET_PROPERTY:
        if not isinstance(parameters["property"], str) or not parameters["property"].strip():
            raise TwinProjectionError(
                f"projection rule {rule.id!r} resolved an invalid property name"
            )


def _cue_id(revision: str, event_id: str, rule_id: str) -> str:
    material = f"{revision}\x00{event_id}\x00{rule_id}".encode()
    return f"cue_{hashlib.sha256(material).hexdigest()[:24]}"
