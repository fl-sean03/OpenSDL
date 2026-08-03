import { describe, expect, it } from "vitest";

import { mixerOffset, readerLidOffset } from "./semantic-motion";

describe("equipment-faithful semantic motion", () => {
  it("keeps the shaker on a one-millimeter-radius horizontal orbit", () => {
    for (let step = 0; step <= 100; step += 1) {
      const offset = mixerOffset(step / 100);
      expect(offset.y).toBe(0);
      expect(Math.hypot(offset.x, offset.z)).toBeLessThanOrEqual(0.001000001);
    }
  });

  it("returns the shaker to its authored pose", () => {
    expect(mixerOffset(0)).toEqual({ x: 0, y: 0, z: -0 });
    expect(Math.hypot(mixerOffset(1).x, mixerOffset(1).z)).toBeLessThan(1e-12);
  });

  it("carries the reader lid from D2 to D3 and back", () => {
    expect(readerLidOffset(0)).toEqual({ x: 0, y: 0, z: 0 });
    expect(readerLidOffset(0.5)).toEqual({ x: 0.164, y: 0.052, z: 0 });
    expect(Math.hypot(readerLidOffset(1).x, readerLidOffset(1).y)).toBeLessThan(1e-12);
  });
});
