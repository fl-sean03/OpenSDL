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

const DURATIONS: Record<TwinAction, number> = {
  highlight: 600,
  transfer: 2_200,
  play_clip: 2_800,
  set_property: 800,
};

export function buildTimeline(cues: TwinCue[]): CueSegment[] {
  let cursor = 0;
  return [...cues]
    .sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id))
    .map((cue) => {
      const durationMs = DURATIONS[cue.action];
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

export function describeAction(action: TwinAction): string {
  const labels: Record<TwinAction, string> = {
    highlight: "ACTIVE",
    transfer: "TRANSFER",
    play_clip: "MOTION",
    set_property: "RESULT",
  };
  return labels[action];
}
