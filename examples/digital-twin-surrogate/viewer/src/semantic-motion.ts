export interface MotionOffset {
  x: number;
  y: number;
  z: number;
}

function bounded(progress: number): number {
  return Math.max(0, Math.min(progress, 1));
}

export function mixerOffset(progress: number): MotionOffset {
  const value = bounded(progress);
  const envelope = Math.sin(value * Math.PI);
  const phase = value * Math.PI * 18;
  return {
    x: Math.cos(phase) * 0.001 * envelope,
    y: 0,
    z: -Math.sin(phase) * 0.001 * envelope,
  };
}

export function readerLidOffset(progress: number): MotionOffset {
  const travel = Math.sin(bounded(progress) * Math.PI);
  return {
    x: -0.164 * travel,
    y: 0.052 * travel,
    z: 0,
  };
}
