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

/**
 * Excursion of the reader lid from its parked pose on the caddy to the closed
 * pose on the reader and back.
 *
 * On the open line the caddy sits one row behind the reader at the same station
 * rather than one deck column beside it, so the travel is 107 mm along the
 * GLB's Z axis (the source scene's -Y) with a lift on the way across.
 */
export function readerLidOffset(progress: number): MotionOffset {
  const travel = Math.sin(bounded(progress) * Math.PI);
  return {
    x: 0,
    y: 0.052 * travel,
    z: 0.107 * travel,
  };
}
