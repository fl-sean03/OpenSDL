import { describe, expect, it } from "vitest";

import { DEMO_PROJECTION } from "./demo";
import {
  buildTimeline,
  evaluateTimeline,
  formatOccurredAt,
  formatWallClockDuration,
  runWallClock,
  timelineDuration,
} from "./timeline";
import type { TwinCue } from "./types";

function cueAt(sequence: number, occurredAt: string, action: TwinCue["action"]): TwinCue {
  return {
    id: `cue-${sequence}`,
    sequence,
    sourceEventId: `event-${sequence}`,
    runId: "run-timing",
    taskId: `task-${sequence}`,
    capabilityId: "cell.dispense",
    occurredAt,
    phase: "succeeded",
    action,
    target: "sample",
    parameters: {},
  };
}

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

  it("paces cues by action alone, never by the recorded instants", () => {
    const instant = buildTimeline([
      cueAt(0, "2026-08-03T12:00:00.000Z", "transfer"),
      cueAt(1, "2026-08-03T12:00:00.002Z", "highlight"),
    ]);
    const drawnOut = buildTimeline([
      cueAt(0, "2026-08-03T12:00:00.000Z", "transfer"),
      cueAt(1, "2026-08-03T12:01:30.000Z", "highlight"),
    ]);

    expect(instant.map((item) => item.durationMs)).toEqual(drawnOut.map((item) => item.durationMs));
    expect(timelineDuration(instant)).toBe(timelineDuration(drawnOut));
  });
});

describe("recorded run wall clock", () => {
  it("spans the earliest and latest recorded instants regardless of cue order", () => {
    const wallClock = runWallClock([
      cueAt(0, "2026-08-03T12:00:19.000Z", "highlight"),
      cueAt(1, "2026-08-03T12:00:00.000Z", "transfer"),
      cueAt(2, "2026-08-03T12:00:07.500Z", "play_clip"),
    ]);

    expect(wallClock).toEqual({
      firstOccurredAt: "2026-08-03T12:00:00.000Z",
      lastOccurredAt: "2026-08-03T12:00:19.000Z",
      elapsedMs: 19_000,
    });
  });

  it("reports the included demo run as the sub-second run it represents", () => {
    const wallClock = runWallClock(DEMO_PROJECTION.cues);

    // The bundled cues stand in for a zero-latency simulated run, so their recorded span has to
    // stay in milliseconds. Second-scale spacing here would report a duration no such run takes.
    expect(wallClock?.elapsedMs).toBe(14);
    expect(formatWallClockDuration(wallClock?.elapsedMs ?? Number.NaN)).toBe("14 ms");
  });

  it("keeps the demo's recorded span far below its stylized playback length", () => {
    const recordedMs = runWallClock(DEMO_PROJECTION.cues)?.elapsedMs ?? Number.NaN;

    expect(recordedMs).toBeLessThan(timelineDuration(buildTimeline(DEMO_PROJECTION.cues)) / 100);
  });

  it("reports a truthful zero when every cue lands in one millisecond", () => {
    const wallClock = runWallClock([
      cueAt(0, "2026-08-03T12:00:00.000Z", "highlight"),
      cueAt(1, "2026-08-03T12:00:00.000Z", "transfer"),
    ]);

    expect(wallClock?.elapsedMs).toBe(0);
    expect(formatWallClockDuration(wallClock?.elapsedMs ?? Number.NaN)).toBe("0 ms");
  });

  it("ignores cues whose instants cannot be parsed", () => {
    expect(runWallClock([cueAt(0, "not-a-timestamp", "highlight")])).toBeUndefined();
    expect(
      runWallClock([
        cueAt(0, "not-a-timestamp", "highlight"),
        cueAt(1, "2026-08-03T12:00:04.000Z", "transfer"),
      ])?.elapsedMs,
    ).toBe(0);
  });

  it("returns undefined for a run with no cues", () => {
    expect(runWallClock([])).toBeUndefined();
  });
});

describe("recorded time formatting", () => {
  it("keeps sub-second and multi-scale durations legible", () => {
    expect(formatWallClockDuration(0)).toBe("0 ms");
    expect(formatWallClockDuration(3)).toBe("3 ms");
    expect(formatWallClockDuration(999)).toBe("999 ms");
    expect(formatWallClockDuration(1_500)).toBe("1.50 s");
    expect(formatWallClockDuration(19_000)).toBe("19.0 s");
    expect(formatWallClockDuration(90_000)).toBe("1m 30s");
    expect(formatWallClockDuration(7_380_000)).toBe("2h 03m");
  });

  it("refuses to invent a duration it does not have", () => {
    expect(formatWallClockDuration(Number.NaN)).toBe("unavailable");
    expect(formatWallClockDuration(-1)).toBe("unavailable");
  });

  it("normalizes zoned instants and leaves unzoned ones verbatim", () => {
    expect(formatOccurredAt("2026-08-03T12:00:19.000Z")).toBe("12:00:19.000 UTC");
    expect(formatOccurredAt("2026-08-03T14:00:19+02:00")).toBe("12:00:19.000 UTC");
    expect(formatOccurredAt("2026-08-03T12:00:19")).toBe("2026-08-03T12:00:19");
    expect(formatOccurredAt("not-a-timestamp")).toBe("not-a-timestamp");
  });
});
