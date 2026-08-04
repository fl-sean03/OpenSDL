import { describe, expect, it } from "vitest";

import { animationTimeSeconds, bindingForCue } from "./authored-motion";
import type { AnimationTimeline, TwinCue } from "./types";

const timeline: AnimationTimeline = {
  frameRate: 24,
  frameStart: 1,
  frameEnd: 960,
  bindings: [
    {
      id: "input-to-dispense",
      action: "transfer",
      parameterMatch: { source: "input", destination: "dispense" },
      frameStart: 1,
      frameEnd: 160,
    },
    {
      id: "mix",
      action: "play_clip",
      parameterMatch: { clip: "mix_cycle" },
      frameStart: 580,
      frameEnd: 630,
    },
  ],
};

function cue(action: TwinCue["action"], parameters: Record<string, unknown>): TwinCue {
  return {
    id: "cue-1",
    sequence: 0,
    sourceEventId: "event-1",
    runId: "run-1",
    taskId: "task-1",
    capabilityId: "cell.transfer_labware",
    occurredAt: "2026-08-03T00:00:00Z",
    phase: "succeeded",
    action,
    target: "sample",
    parameters,
  };
}

describe("authored animation bindings", () => {
  it("matches action and every declared parameter", () => {
    expect(
      bindingForCue(
        timeline,
        cue("transfer", {
          source: "input",
          destination: "dispense",
          labware: "plate-1",
        }),
      )?.id,
    ).toBe("input-to-dispense");
    expect(
      bindingForCue(timeline, cue("transfer", { source: "input", destination: "characterize" })),
    ).toBeUndefined();
  });

  it("maps cue progress into the shared authored frame clock", () => {
    const binding = timeline.bindings[1];
    if (!binding) throw new Error("missing test binding");
    expect(animationTimeSeconds(timeline, binding, 0)).toBeCloseTo(580 / 24);
    expect(animationTimeSeconds(timeline, binding, 0.5)).toBeCloseTo(605 / 24);
    expect(animationTimeSeconds(timeline, binding, 1)).toBeCloseTo(630 / 24);
  });

  it("clamps progress before calculating animation time", () => {
    const binding = timeline.bindings[0];
    if (!binding) throw new Error("missing test binding");
    expect(animationTimeSeconds(timeline, binding, -1)).toBeCloseTo(1 / 24);
    expect(animationTimeSeconds(timeline, binding, 2)).toBeCloseTo(160 / 24);
  });
});
