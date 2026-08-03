import { jsonEqual } from "./authored-motion";
import type {
  AnimationTimeline,
  TwinAction,
  TwinCue,
  TwinDefinition,
  TwinProjection,
} from "./types";

const ACTIONS = new Set<TwinAction>(["highlight", "transfer", "play_clip", "set_property"]);
const PHASES = new Set([
  "started",
  "retrying",
  "succeeded",
  "failed",
  "cancelled",
  "intervention_required",
]);

/**
 * Keys each published contract object declares, mirrored from the generated JSON Schemas in
 * `packages/schemas/jsonschema/`.
 *
 * Every object named here sets `additionalProperties: false`, so the viewer rejects anything else.
 * As the reference consumer of these contracts it should not accept documents they forbid: a
 * misspelled or retired key that is silently ignored here is how a viewer ends up rendering
 * something subtly wrong while looking fine.
 *
 * These sets mirror the schemas rather than the viewer's own types, which matters: the definition
 * contract carries `projectionRules`, which the viewer does not model but the API does serve.
 * Deriving from `TwinDefinition` would reject every live response. `validation.test.ts` pins each
 * set against the generated schemas so this cannot drift.
 *
 * Objects the schemas leave open stay open. A cue's `parameters` and an animation binding's
 * `parameterMatch` are free-form by contract, and the envelope carrying `cues` has no published
 * schema at all, so none of them are constrained here.
 */
export const CONTRACT_KEYS = {
  cue: new Set([
    "id",
    "sequence",
    "sourceEventId",
    "runId",
    "taskId",
    "capabilityId",
    "occurredAt",
    "phase",
    "action",
    "target",
    "parameters",
  ]),
  definitionRoot: new Set([
    "apiVersion",
    "kind",
    "version",
    "revision",
    "coordinateFrame",
    "scene",
    "entities",
    "anchors",
    "projectionRules",
    "animationTimeline",
  ]),
  coordinateFrame: new Set(["unit", "handedness", "upAxis", "origin"]),
  scene: new Set(["path", "sha256"]),
  entity: new Set(["id", "node", "resources"]),
  anchor: new Set(["id", "position", "node"]),
  animationTimeline: new Set(["frameRate", "frameStart", "frameEnd", "bindings"]),
  animationBinding: new Set(["id", "action", "parameterMatch", "frameStart", "frameEnd"]),
} as const satisfies Record<string, ReadonlySet<string>>;

function rejectUnknownKeys(
  value: Record<string, unknown>,
  known: ReadonlySet<string>,
  label: string,
): void {
  const unexpected = Object.keys(value)
    .filter((key) => !known.has(key))
    .sort();
  if (unexpected.length > 0) {
    throw new TypeError(`${label} has unsupported keys: ${unexpected.join(", ")}`);
  }
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new TypeError(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function string(value: unknown, label: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new TypeError(`${label} must be a non-empty string`);
  }
  return value;
}

function strings(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new TypeError(`${label} must be a string array`);
  }
  return value;
}

function vector(value: unknown, label: string): [number, number, number] {
  if (
    !Array.isArray(value) ||
    value.length !== 3 ||
    value.some((item) => typeof item !== "number" || !Number.isFinite(item))
  ) {
    throw new TypeError(`${label} must contain three finite numbers`);
  }
  return [value[0] as number, value[1] as number, value[2] as number];
}

function integer(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new TypeError(`${label} must be an integer`);
  }
  return value;
}

function parseAnimationTimeline(value: unknown): AnimationTimeline | undefined {
  if (value === undefined || value === null) return undefined;
  const timeline = record(value, "animationTimeline");
  rejectUnknownKeys(timeline, CONTRACT_KEYS.animationTimeline, "animationTimeline");
  const frameRate = timeline.frameRate;
  if (typeof frameRate !== "number" || !Number.isFinite(frameRate) || frameRate <= 0) {
    throw new TypeError("animationTimeline.frameRate must be a positive finite number");
  }
  const frameStart = integer(timeline.frameStart, "animationTimeline.frameStart");
  const frameEnd = integer(timeline.frameEnd, "animationTimeline.frameEnd");
  if (frameStart < 0 || frameEnd <= frameStart) {
    throw new TypeError("animationTimeline frame range is invalid");
  }
  if (!Array.isArray(timeline.bindings)) {
    throw new TypeError("animationTimeline.bindings must be an array");
  }
  const ids = new Set<string>();
  const bindings = timeline.bindings.map((item, index) => {
    const binding = record(item, `animationTimeline.bindings[${index}]`);
    rejectUnknownKeys(
      binding,
      CONTRACT_KEYS.animationBinding,
      `animationTimeline.bindings[${index}]`,
    );
    const id = string(binding.id, `animationTimeline.bindings[${index}].id`);
    if (ids.has(id)) throw new TypeError("animationTimeline binding ids must be unique");
    ids.add(id);
    const action = string(binding.action, `animationTimeline.bindings[${index}].action`);
    if (!ACTIONS.has(action as TwinAction)) {
      throw new TypeError(`animationTimeline.bindings[${index}].action is unsupported`);
    }
    const parameterMatch = record(
      binding.parameterMatch,
      `animationTimeline.bindings[${index}].parameterMatch`,
    );
    if (Object.keys(parameterMatch).length === 0) {
      throw new TypeError(`animationTimeline.bindings[${index}].parameterMatch cannot be empty`);
    }
    const bindingStart = integer(
      binding.frameStart,
      `animationTimeline.bindings[${index}].frameStart`,
    );
    const bindingEnd = integer(binding.frameEnd, `animationTimeline.bindings[${index}].frameEnd`);
    if (bindingStart < frameStart || bindingEnd > frameEnd || bindingEnd <= bindingStart) {
      throw new TypeError(`animationTimeline.bindings[${index}] frame range is invalid`);
    }
    return {
      id,
      action: action as TwinAction,
      parameterMatch,
      frameStart: bindingStart,
      frameEnd: bindingEnd,
    };
  });
  for (const [index, left] of bindings.entries()) {
    for (const right of bindings.slice(index + 1)) {
      if (left.action !== right.action) continue;
      const shared = Object.keys(left.parameterMatch).filter(
        (name) => name in right.parameterMatch,
      );
      if (
        shared.every((name) => jsonEqual(left.parameterMatch[name], right.parameterMatch[name]))
      ) {
        throw new TypeError(`animationTimeline bindings ${left.id} and ${right.id} are ambiguous`);
      }
    }
  }
  return { frameRate, frameStart, frameEnd, bindings };
}

export function parseTwinDefinition(value: unknown): TwinDefinition {
  const root = record(value, "twin definition");
  rejectUnknownKeys(root, CONTRACT_KEYS.definitionRoot, "twin definition");
  // Deliberate divergence: the schema gives apiVersion and kind defaults, so it does not list them
  // as required. The viewer demands them anyway. It verifies a scene digest and binds named nodes
  // against this contract, and the version gate is what makes rejecting unknown keys safe; reading
  // an absent version as "presumably v0alpha1" would defeat both.
  if (root.apiVersion !== "opensdl.dev/v0alpha1" || root.kind !== "DigitalTwin") {
    throw new TypeError("unsupported twin definition kind or API version");
  }
  const frame = record(root.coordinateFrame, "coordinateFrame");
  rejectUnknownKeys(frame, CONTRACT_KEYS.coordinateFrame, "coordinateFrame");
  const scene = record(root.scene, "scene");
  rejectUnknownKeys(scene, CONTRACT_KEYS.scene, "scene");
  const sceneSha256 = string(scene.sha256, "scene.sha256").toLocaleLowerCase();
  if (!/^[0-9a-f]{64}$/.test(sceneSha256)) {
    throw new TypeError("scene.sha256 must contain 64 hexadecimal characters");
  }
  if (!Array.isArray(root.entities)) {
    throw new TypeError("entities must be an array");
  }
  // The contract defaults anchors to an empty tuple and omits it from `required`, so a producer
  // may leave the key out entirely.
  const rawAnchors = root.anchors ?? [];
  if (!Array.isArray(rawAnchors)) {
    throw new TypeError("anchors must be an array");
  }

  const entities = root.entities.map((item, index) => {
    const entity = record(item, `entities[${index}]`);
    rejectUnknownKeys(entity, CONTRACT_KEYS.entity, `entities[${index}]`);
    return {
      id: string(entity.id, `entities[${index}].id`),
      node: string(entity.node, `entities[${index}].node`),
      resources: strings(entity.resources ?? [], `entities[${index}].resources`),
    };
  });
  const anchors = rawAnchors.map((item, index) => {
    const anchor = record(item, `anchors[${index}]`);
    rejectUnknownKeys(anchor, CONTRACT_KEYS.anchor, `anchors[${index}]`);
    return {
      id: string(anchor.id, `anchors[${index}].id`),
      node:
        anchor.node === undefined || anchor.node === null
          ? undefined
          : string(anchor.node, `anchors[${index}].node`),
      position: vector(anchor.position, `anchors[${index}].position`),
    };
  });

  const handedness = string(frame.handedness, "coordinateFrame.handedness");
  const upAxis = string(frame.upAxis, "coordinateFrame.upAxis");
  if (handedness !== "right") {
    throw new TypeError("coordinateFrame.handedness must be right in v0alpha1");
  }
  if (upAxis !== "X" && upAxis !== "Y" && upAxis !== "Z") {
    throw new TypeError("coordinateFrame.upAxis must be X, Y, or Z");
  }

  const unit = string(frame.unit, "coordinateFrame.unit");
  const origin = vector(frame.origin ?? [0, 0, 0], "coordinateFrame.origin");
  if (unit !== "m") throw new TypeError("coordinateFrame.unit must be m in v0alpha1");
  if (origin.some((component) => component !== 0)) {
    throw new TypeError("coordinateFrame.origin must be [0, 0, 0] in v0alpha1");
  }

  return {
    apiVersion: "opensdl.dev/v0alpha1",
    kind: "DigitalTwin",
    version: string(root.version, "version"),
    revision: string(root.revision, "revision"),
    coordinateFrame: {
      unit,
      handedness: "right",
      upAxis,
      origin,
    },
    scene: {
      path: string(scene.path, "scene.path"),
      sha256: sceneSha256,
    },
    entities,
    anchors,
    animationTimeline: parseAnimationTimeline(root.animationTimeline),
  };
}

export function parseProjection(value: unknown): TwinProjection {
  const root = record(value, "twin projection");
  if (!Array.isArray(root.cues)) {
    throw new TypeError("twin projection cues must be an array");
  }
  const cues = root.cues.map((item, index): TwinCue => {
    const cue = record(item, `cues[${index}]`);
    rejectUnknownKeys(cue, CONTRACT_KEYS.cue, `cues[${index}]`);
    const action = string(cue.action, `cues[${index}].action`);
    if (!ACTIONS.has(action as TwinAction)) {
      throw new TypeError(`cues[${index}].action is unsupported`);
    }
    if (typeof cue.sequence !== "number" || !Number.isInteger(cue.sequence) || cue.sequence < 0) {
      throw new TypeError(`cues[${index}].sequence must be a non-negative integer`);
    }
    const parameters = record(cue.parameters ?? {}, `cues[${index}].parameters`);
    // The contract declares runId optional with a null default, so an absent key means null. The
    // controller currently always emits it, but a producer using exclude_none is equally valid.
    const rawRunId = cue.runId;
    if (rawRunId !== null && rawRunId !== undefined && typeof rawRunId !== "string") {
      throw new TypeError(`cues[${index}].runId must be a string or null`);
    }
    const runId = rawRunId ?? null;
    const phase = string(cue.phase, `cues[${index}].phase`);
    if (!PHASES.has(phase)) {
      throw new TypeError(`cues[${index}].phase is unsupported`);
    }
    return {
      id: string(cue.id, `cues[${index}].id`),
      sequence: cue.sequence,
      sourceEventId: string(cue.sourceEventId, `cues[${index}].sourceEventId`),
      runId,
      taskId: string(cue.taskId, `cues[${index}].taskId`),
      capabilityId: string(cue.capabilityId, `cues[${index}].capabilityId`),
      occurredAt: string(cue.occurredAt, `cues[${index}].occurredAt`),
      phase: phase as TwinCue["phase"],
      action: action as TwinAction,
      target: string(cue.target, `cues[${index}].target`),
      parameters,
    };
  });

  cues.sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id));
  return {
    definition_revision: string(root.definition_revision, "definition_revision"),
    run_id: string(root.run_id, "run_id"),
    cues,
  };
}
