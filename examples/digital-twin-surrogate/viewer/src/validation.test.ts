import { describe, expect, it } from "vitest";

import { DEMO_DEFINITION, DEMO_PROJECTION } from "./demo";
import type { TwinDefinition } from "./types";
import { parseProjection, parseTwinDefinition } from "./validation";

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
