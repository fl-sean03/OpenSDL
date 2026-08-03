import { describe, expect, it } from "vitest";

import { DEMO_PROJECTION } from "./demo";
import { buildTimeline, evaluateTimeline, timelineDuration } from "./timeline";

describe("cue timeline", () => {
  it("orders cues deterministically and assigns contiguous durations", () => {
    const reversed = [...DEMO_PROJECTION.cues].reverse();
    const segments = buildTimeline(reversed);

    expect(segments.map((item) => item.cue.sequence)).toEqual(
      DEMO_PROJECTION.cues.map((item) => item.sequence),
    );
    expect(segments[0]?.startMs).toBe(0);
    expect(
      segments.every((item, index) => index === 0 || item.startMs === segments[index - 1]?.endMs),
    ).toBe(true);
    expect(timelineDuration(segments)).toBeGreaterThan(0);
  });

  it("returns completed cues and fractional progress at any scrub position", () => {
    const segments = buildTimeline(DEMO_PROJECTION.cues.slice(0, 2));
    const firstEnd = segments[0]?.endMs ?? 0;
    const second = segments[1];
    expect(second).toBeDefined();

    const state = evaluateTimeline(segments, firstEnd + (second?.durationMs ?? 0) / 2);
    expect(state.completed).toHaveLength(1);
    expect(state.current?.cue.sequence).toBe(1);
    expect(state.progress).toBeCloseTo(0.5);
  });

  it("clamps time before zero and after the final cue", () => {
    const segments = buildTimeline(DEMO_PROJECTION.cues.slice(0, 2));
    expect(evaluateTimeline(segments, -100).current?.cue.sequence).toBe(0);
    expect(evaluateTimeline(segments, Number.POSITIVE_INFINITY).completed).toHaveLength(2);
  });
});
