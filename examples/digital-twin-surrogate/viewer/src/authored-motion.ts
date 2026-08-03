import type { AnimationBinding, AnimationTimeline, TwinCue } from "./types";

export function jsonEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) && Array.isArray(right)) {
    return (
      left.length === right.length && left.every((item, index) => jsonEqual(item, right[index]))
    );
  }
  if (
    typeof left === "object" &&
    left !== null &&
    !Array.isArray(left) &&
    typeof right === "object" &&
    right !== null &&
    !Array.isArray(right)
  ) {
    const leftRecord = left as Record<string, unknown>;
    const rightRecord = right as Record<string, unknown>;
    const keys = Object.keys(leftRecord);
    return (
      keys.length === Object.keys(rightRecord).length &&
      keys.every((key) => key in rightRecord && jsonEqual(leftRecord[key], rightRecord[key]))
    );
  }
  return false;
}

export function bindingForCue(
  timeline: AnimationTimeline | undefined,
  cue: TwinCue,
): AnimationBinding | undefined {
  return timeline?.bindings.find(
    (binding) =>
      binding.action === cue.action &&
      Object.entries(binding.parameterMatch).every(([name, expected]) =>
        jsonEqual(cue.parameters[name], expected),
      ),
  );
}

export function animationTimeSeconds(
  timeline: AnimationTimeline,
  binding: AnimationBinding,
  progress: number,
): number {
  const bounded = Math.max(0, Math.min(progress, 1));
  const frame = binding.frameStart + (binding.frameEnd - binding.frameStart) * bounded;
  // Blender's glTF exporter preserves the authored frame clock: frame 1 is
  // stored at 1 / fps, not at time zero. Keep that absolute clock so scene
  // transforms, latches, liquid state, and module status stay frame-exact.
  return frame / timeline.frameRate;
}
