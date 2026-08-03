import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { DEMO_DEFINITION, DEMO_PROJECTION } from "./demo";
import type { TwinDefinition } from "./types";
import { CONTRACT_KEYS, parseProjection, parseTwinDefinition } from "./validation";

interface SchemaObject {
  additionalProperties?: unknown;
  properties?: Record<string, { additionalProperties?: unknown }>;
  $defs?: Record<string, SchemaObject>;
}

/** Reads a generated contract straight from the schema package so drift cannot go unnoticed. */
function loadSchema(name: string): SchemaObject {
  const url = new URL(
    `../../../../packages/schemas/jsonschema/${name}.schema.json`,
    import.meta.url,
  );
  return JSON.parse(readFileSync(url, "utf8")) as SchemaObject;
}

/** A definition shaped loosely enough to plant keys the contract forbids. */
type LooseDefinition = Record<string, unknown> & {
  coordinateFrame: Record<string, unknown>;
  scene: Record<string, unknown>;
  entities: Array<Record<string, unknown>>;
  anchors?: Array<Record<string, unknown>>;
  animationTimeline: Record<string, unknown> & {
    bindings: Array<Record<string, unknown>>;
  };
};

function looseDefinition(): LooseDefinition {
  return structuredClone(DEMO_DEFINITION) as unknown as LooseDefinition;
}

describe("API payload validation", () => {
  it("accepts the included definition and projection", () => {
    const definition = parseTwinDefinition(DEMO_DEFINITION);
    expect(definition.entities).toHaveLength(7);
    expect(definition.animationTimeline?.bindings).toHaveLength(7);
    expect(parseProjection(DEMO_PROJECTION).cues).toHaveLength(20);
  });

  it("rejects command-like actions outside the read-only cue contract", () => {
    const projection = structuredClone(DEMO_PROJECTION) as unknown as {
      cues: Array<{ action: string }>;
    };
    const firstCue = projection.cues[0];
    if (!firstCue) throw new Error("demo projection has no cues");
    firstCue.action = "execute";

    expect(() => parseProjection(projection)).toThrow(/unsupported/);
  });

  it("accepts an absent runId as the null default the cue contract declares", () => {
    const projection = structuredClone(DEMO_PROJECTION) as unknown as {
      cues: Array<Record<string, unknown>>;
    };
    const firstCue = projection.cues[0];
    if (!firstCue) throw new Error("demo projection has no cues");
    delete firstCue.runId;

    // twin-cue.schema.json omits runId from `required` and defaults it to null, so a producer
    // dumping with exclude_none emits no key at all. That document is valid.
    expect(parseProjection(projection).cues[0]?.runId).toBeNull();
  });

  it("accepts an explicit null runId and rejects a non-string one", () => {
    const nulled = structuredClone(DEMO_PROJECTION) as unknown as {
      cues: Array<{ runId: unknown }>;
    };
    const nulledCue = nulled.cues[0];
    if (!nulledCue) throw new Error("demo projection has no cues");
    nulledCue.runId = null;
    expect(parseProjection(nulled).cues[0]?.runId).toBeNull();

    const wrongType = structuredClone(DEMO_PROJECTION) as unknown as {
      cues: Array<{ runId: unknown }>;
    };
    const wrongTypeCue = wrongType.cues[0];
    if (!wrongTypeCue) throw new Error("demo projection has no cues");
    wrongTypeCue.runId = 7;
    expect(() => parseProjection(wrongType)).toThrow(/runId must be a string or null/);
  });

  it("rejects cue keys the published contract forbids", () => {
    const projection = structuredClone(DEMO_PROJECTION) as unknown as {
      cues: Array<Record<string, unknown>>;
    };
    const firstCue = projection.cues[0];
    if (!firstCue) throw new Error("demo projection has no cues");
    firstCue.occuredAt = "2026-08-03T12:00:00.000Z";

    // twin-cue.schema.json sets additionalProperties: false. A typo like this must fail loudly
    // rather than being dropped, which would leave the real occurredAt silently unread.
    expect(() => parseProjection(projection)).toThrow(/unsupported keys: occuredAt/);
  });

  it("leaves free-form cue parameters unconstrained", () => {
    const projection = structuredClone(DEMO_PROJECTION) as unknown as {
      cues: Array<{ parameters: Record<string, unknown> }>;
    };
    const firstCue = projection.cues[0];
    if (!firstCue) throw new Error("demo projection has no cues");
    firstCue.parameters.vendorSpecificHint = "anything";

    expect(parseProjection(projection).cues[0]?.parameters.vendorSpecificHint).toBe("anything");
  });

  it("rejects unknown keys on every definition object the contract closes", () => {
    const root = looseDefinition();
    root.projectionRuls = [];
    expect(() => parseTwinDefinition(root)).toThrow(/unsupported keys: projectionRuls/);

    const frame = looseDefinition();
    frame.coordinateFrame.scale = 1;
    expect(() => parseTwinDefinition(frame)).toThrow(/coordinateFrame has unsupported keys: scale/);

    const scene = looseDefinition();
    scene.scene.sha512 = "0".repeat(128);
    expect(() => parseTwinDefinition(scene)).toThrow(/scene has unsupported keys: sha512/);

    const entity = looseDefinition();
    const firstEntity = entity.entities[0];
    if (!firstEntity) throw new Error("demo definition has no entities");
    firstEntity.nodes = ["CellRoot"];
    expect(() => parseTwinDefinition(entity)).toThrow(/entities\[0\] has unsupported keys: nodes/);

    const anchor = looseDefinition();
    const firstAnchor = anchor.anchors?.[0];
    if (!firstAnchor) throw new Error("demo definition has no anchors");
    firstAnchor.rotation = [0, 0, 0];
    expect(() => parseTwinDefinition(anchor)).toThrow(
      /anchors\[0\] has unsupported keys: rotation/,
    );

    const timeline = looseDefinition();
    timeline.animationTimeline.fps = 24;
    expect(() => parseTwinDefinition(timeline)).toThrow(
      /animationTimeline has unsupported keys: fps/,
    );

    const binding = looseDefinition();
    const firstBinding = binding.animationTimeline.bindings[0];
    if (!firstBinding) throw new Error("demo definition has no animation bindings");
    firstBinding.clip = "dispense_cycle";
    expect(() => parseTwinDefinition(binding)).toThrow(
      /animationTimeline\.bindings\[0\] has unsupported keys: clip/,
    );
  });

  it("accepts contract fields the viewer does not model", () => {
    const definition = looseDefinition();
    // The API always serves projectionRules, and the viewer ignores them. Rejecting the key
    // because TwinDefinition omits it would break the viewer against every live response.
    definition.projectionRules = [
      {
        id: "dispense-started",
        match: { eventType: "TaskStarted", capability: "cell.dispense", phase: "started" },
        action: "highlight",
        target: "dispenser-head",
      },
    ];

    expect(parseTwinDefinition(definition).entities).toHaveLength(7);
  });

  it("accepts an omitted anchors list as the empty default the contract declares", () => {
    const definition = looseDefinition();
    delete definition.anchors;

    // twin-definition.schema.json omits anchors from `required` and defaults it to an empty tuple.
    expect(parseTwinDefinition(definition).anchors).toEqual([]);
  });

  it("leaves free-form animation parameterMatch unconstrained", () => {
    const definition = looseDefinition();
    const firstBinding = definition.animationTimeline.bindings[0];
    if (!firstBinding) throw new Error("demo definition has no animation bindings");
    const parameterMatch = firstBinding.parameterMatch as Record<string, unknown>;
    parameterMatch.vendorSpecificHint = "anything";

    expect(
      parseTwinDefinition(definition).animationTimeline?.bindings[0]?.parameterMatch
        .vendorSpecificHint,
    ).toBe("anything");
  });

  it("rejects malformed coordinates before scene binding", () => {
    const definition = structuredClone(DEMO_DEFINITION) as unknown as {
      anchors: Array<{ position: unknown }>;
    };
    const firstAnchor = definition.anchors[0];
    if (!firstAnchor) throw new Error("demo definition has no anchors");
    firstAnchor.position = [0, Number.NaN, 0];

    expect(() => parseTwinDefinition(definition)).toThrow(/finite numbers/);
  });

  it("rejects coordinate semantics not supported by v0alpha1", () => {
    const definition = structuredClone(DEMO_DEFINITION) as unknown as {
      coordinateFrame: { unit: string; handedness: string; origin: number[] };
    };
    definition.coordinateFrame.unit = "mm";
    expect(() => parseTwinDefinition(definition)).toThrow(/unit must be m/);

    definition.coordinateFrame.unit = "m";
    definition.coordinateFrame.handedness = "left";
    expect(() => parseTwinDefinition(definition)).toThrow(/must be right/);

    definition.coordinateFrame.handedness = "right";
    definition.coordinateFrame.origin = [1, 0, 0];
    expect(() => parseTwinDefinition(definition)).toThrow(/origin must be/);
  });

  it("accepts an omitted or null optional anchor node", () => {
    const definition = structuredClone(DEMO_DEFINITION) as unknown as {
      anchors: Array<{ node?: string | null }>;
    };
    const first = definition.anchors[0];
    if (!first) throw new Error("demo definition has no anchors");
    first.node = null;
    expect(parseTwinDefinition(definition).anchors[0]?.node).toBeUndefined();
  });

  it("rejects ambiguous or out-of-range authored animation bindings", () => {
    const duplicate = structuredClone(DEMO_DEFINITION) as TwinDefinition;
    const timeline = duplicate.animationTimeline;
    if (!timeline) throw new Error("demo definition has no animation timeline");
    const first = timeline.bindings[0];
    if (!first) throw new Error("demo definition has no animation bindings");
    timeline.bindings.push(structuredClone(first));
    expect(() => parseTwinDefinition(duplicate)).toThrow(/ids must be unique/);

    const outOfRange = structuredClone(DEMO_DEFINITION) as TwinDefinition;
    const outOfRangeTimeline = outOfRange.animationTimeline;
    if (!outOfRangeTimeline) throw new Error("demo definition has no animation timeline");
    const last = outOfRangeTimeline.bindings.at(-1);
    if (!last) throw new Error("demo definition has no animation bindings");
    last.frameEnd = outOfRangeTimeline.frameEnd + 1;
    expect(() => parseTwinDefinition(outOfRange)).toThrow(/frame range is invalid/);
  });

  it("rejects empty animation parameter matches", () => {
    const definition = structuredClone(DEMO_DEFINITION) as TwinDefinition;
    const timeline = definition.animationTimeline;
    if (!timeline) throw new Error("demo definition has no animation timeline");
    const first = timeline.bindings[0];
    if (!first) throw new Error("demo definition has no animation bindings");
    first.parameterMatch = {};
    expect(() => parseTwinDefinition(definition)).toThrow(/cannot be empty/);
  });

  it("rejects animation bindings that can match the same cue", () => {
    const definition = structuredClone(DEMO_DEFINITION) as TwinDefinition;
    const timeline = definition.animationTimeline;
    if (!timeline) throw new Error("demo definition has no animation timeline");
    timeline.bindings.push({
      id: "input-transfer-more-specific",
      action: "transfer",
      parameterMatch: { source: "input" },
      frameStart: 2,
      frameEnd: 100,
    });
    expect(() => parseTwinDefinition(definition)).toThrow(/are ambiguous/);
  });
});

describe("published contract alignment", () => {
  const cueSchema = loadSchema("twin-cue");
  const definitionSchema = loadSchema("twin-definition");

  function definitionDef(name: string): SchemaObject {
    const value = definitionSchema.$defs?.[name];
    if (!value) throw new Error(`twin-definition schema has no $defs.${name}`);
    return value;
  }

  const closedObjects: Array<[string, ReadonlySet<string>, SchemaObject]> = [
    ["cue", CONTRACT_KEYS.cue, cueSchema],
    ["definition root", CONTRACT_KEYS.definitionRoot, definitionSchema],
    ["coordinateFrame", CONTRACT_KEYS.coordinateFrame, definitionDef("CoordinateFrame")],
    ["scene", CONTRACT_KEYS.scene, definitionDef("TwinScene")],
    ["entity", CONTRACT_KEYS.entity, definitionDef("TwinEntity")],
    ["anchor", CONTRACT_KEYS.anchor, definitionDef("TwinAnchor")],
    ["animationTimeline", CONTRACT_KEYS.animationTimeline, definitionDef("AnimationTimeline")],
    ["animationBinding", CONTRACT_KEYS.animationBinding, definitionDef("AnimationBinding")],
  ];

  it.each(closedObjects)("mirrors every key the %s contract declares", (_label, keys, schema) => {
    expect([...keys].sort()).toEqual(Object.keys(schema.properties ?? {}).sort());
  });

  it.each(closedObjects)(
    "closes %s only because the contract closes it",
    (_label, _keys, schema) => {
      expect(schema.additionalProperties).toBe(false);
    },
  );

  it("leaves the objects the contracts deliberately open unconstrained", () => {
    expect(cueSchema.properties?.parameters?.additionalProperties).toBe(true);
    expect(definitionDef("AnimationBinding").properties?.parameterMatch?.additionalProperties).toBe(
      true,
    );
  });

  it("covers every closed object the viewer parses", () => {
    expect(Object.keys(CONTRACT_KEYS).sort()).toEqual(
      [
        "anchor",
        "animationBinding",
        "animationTimeline",
        "coordinateFrame",
        "cue",
        "definitionRoot",
        "entity",
        "scene",
      ].sort(),
    );
  });
});
