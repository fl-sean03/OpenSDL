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
  if (root.apiVersion !== "opensdl.dev/v0alpha1" || root.kind !== "DigitalTwin") {
    throw new TypeError("unsupported twin definition kind or API version");
  }
  const frame = record(root.coordinateFrame, "coordinateFrame");
  const scene = record(root.scene, "scene");
  const sceneSha256 = string(scene.sha256, "scene.sha256").toLocaleLowerCase();
  if (!/^[0-9a-f]{64}$/.test(sceneSha256)) {
    throw new TypeError("scene.sha256 must contain 64 hexadecimal characters");
  }
  if (!Array.isArray(root.entities) || !Array.isArray(root.anchors)) {
    throw new TypeError("entities and anchors must be arrays");
  }

  const entities = root.entities.map((item, index) => {
    const entity = record(item, `entities[${index}]`);
    return {
      id: string(entity.id, `entities[${index}].id`),
      node: string(entity.node, `entities[${index}].node`),
      resources: strings(entity.resources ?? [], `entities[${index}].resources`),
    };
  });
  const anchors = root.anchors.map((item, index) => {
    const anchor = record(item, `anchors[${index}]`);
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
    const action = string(cue.action, `cues[${index}].action`);
    if (!ACTIONS.has(action as TwinAction)) {
      throw new TypeError(`cues[${index}].action is unsupported`);
    }
    if (typeof cue.sequence !== "number" || !Number.isInteger(cue.sequence) || cue.sequence < 0) {
      throw new TypeError(`cues[${index}].sequence must be a non-negative integer`);
    }
    const parameters = record(cue.parameters ?? {}, `cues[${index}].parameters`);
    const runId = cue.runId;
    if (runId !== null && typeof runId !== "string") {
      throw new TypeError(`cues[${index}].runId must be a string or null`);
    }
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
