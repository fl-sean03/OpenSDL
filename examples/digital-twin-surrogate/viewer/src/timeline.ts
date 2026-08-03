import type { TwinAction, TwinCue } from "./types";

export interface CueSegment {
  cue: TwinCue;
  startMs: number;
  endMs: number;
  durationMs: number;
}

export interface TimelineState {
  completed: CueSegment[];
  current?: CueSegment;
  progress: number;
}

/** The interval a projected run covers, taken from its persisted cue timestamps. */
export interface RunWallClock {
  firstOccurredAt: string;
  lastOccurredAt: string;
  elapsedMs: number;
}

/**
 * Presentation duration per action, in milliseconds.
 *
 * These are stylized sequence pacing, not measured elapsed time. Cues carry an `occurredAt`
 * projected from the persisted event log, but the simulated cell runs with zero configured
 * latency, so a whole run can emit every cue inside a few milliseconds. Replaying that literally
 * would collapse the animation to an instant, and the authored GLB clip ranges are keyed to this
 * stylized pace besides. Recorded run timing is reported separately by `runWallClock`.
 */
const STYLIZED_DURATIONS: Record<TwinAction, number> = {
  highlight: 600,
  transfer: 2_200,
  play_clip: 2_800,
  set_property: 800,
};

/**
 * Lays cues end to end at stylized pacing.
 *
 * Segment durations come from `STYLIZED_DURATIONS` and ignore `occurredAt` by design. Anything
 * user facing that reports this clock must not present it as elapsed run time.
 */
export function buildTimeline(cues: TwinCue[]): CueSegment[] {
  let cursor = 0;
  return [...cues]
    .sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id))
    .map((cue) => {
      const durationMs = STYLIZED_DURATIONS[cue.action];
      const segment = {
        cue,
        startMs: cursor,
        endMs: cursor + durationMs,
        durationMs,
      };
      cursor = segment.endMs;
      return segment;
    });
}

export function timelineDuration(segments: CueSegment[]): number {
  return segments.at(-1)?.endMs ?? 0;
}

export function evaluateTimeline(segments: CueSegment[], timeMs: number): TimelineState {
  const bounded = Math.max(0, Math.min(timeMs, timelineDuration(segments)));
  const completed: CueSegment[] = [];
  for (const segment of segments) {
    if (bounded >= segment.endMs) {
      completed.push(segment);
      continue;
    }
    if (bounded >= segment.startMs) {
      return {
        completed,
        current: segment,
        progress: (bounded - segment.startMs) / segment.durationMs,
      };
    }
    break;
  }
  return { completed, progress: 0 };
}

const ZONED_INSTANT = /(?:Z|[+-]\d{2}:?\d{2})$/i;

/**
 * Reports the interval a run covers, from its earliest to its latest persisted cue timestamp.
 *
 * Returns `undefined` when no cue carries a parseable instant. An `elapsedMs` of zero is a truthful
 * result: a simulated run can record every cue within the same millisecond.
 */
export function runWallClock(cues: TwinCue[]): RunWallClock | undefined {
  const timed = cues
    .map((cue) => ({ occurredAt: cue.occurredAt, epochMs: Date.parse(cue.occurredAt) }))
    .filter((item) => Number.isFinite(item.epochMs))
    .sort((left, right) => left.epochMs - right.epochMs);
  const first = timed.at(0);
  const last = timed.at(-1);
  if (!first || !last) return undefined;
  return {
    firstOccurredAt: first.occurredAt,
    lastOccurredAt: last.occurredAt,
    elapsedMs: last.epochMs - first.epochMs,
  };
}

/** Formats a recorded duration at a resolution that stays honest about sub-second runs. */
export function formatWallClockDuration(milliseconds: number): string {
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return "unavailable";
  if (milliseconds < 1_000) return `${Math.round(milliseconds)} ms`;
  const seconds = milliseconds / 1_000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 2 : 1)} s`;
  const totalSeconds = Math.round(seconds);
  const minutes = Math.floor(totalSeconds / 60);
  if (minutes < 60) return `${minutes}m ${(totalSeconds % 60).toString().padStart(2, "0")}s`;
  return `${Math.floor(minutes / 60)}h ${(minutes % 60).toString().padStart(2, "0")}m`;
}

/**
 * Formats a persisted cue instant for display.
 *
 * Only a timestamp that declares an offset is normalized and labelled UTC. Anything else is shown
 * verbatim rather than claiming a zone the event log did not record.
 */
export function formatOccurredAt(occurredAt: string): string {
  const epochMs = Date.parse(occurredAt);
  if (!Number.isFinite(epochMs) || !ZONED_INSTANT.test(occurredAt.trim())) return occurredAt;
  return `${new Date(epochMs).toISOString().slice(11, 23)} UTC`;
}

export function describeAction(action: TwinAction): string {
  const labels: Record<TwinAction, string> = {
    highlight: "ACTIVE",
    transfer: "TRANSFER",
    play_clip: "MOTION",
    set_property: "RESULT",
  };
  return labels[action];
}
