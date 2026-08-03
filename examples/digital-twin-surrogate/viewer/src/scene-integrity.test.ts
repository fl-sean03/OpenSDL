import { afterEach, describe, expect, it, vi } from "vitest";

import { sha256Hex, verifySceneBytes } from "./scene-integrity";

describe("scene integrity", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("computes the standard SHA-256 digest", async () => {
    const bytes = new TextEncoder().encode("opensdl").buffer;
    expect(await sha256Hex(bytes)).toBe(
      "898491d817d61d100cabb0aea313ef6bad6e813ce8ea959a233406d96bcfd950",
    );
  });

  it("rejects bytes that differ from the twin definition", async () => {
    const bytes = new TextEncoder().encode("scene").buffer;
    await expect(verifySceneBytes(bytes, "0".repeat(64))).rejects.toThrow(/integrity mismatch/);
  });

  it("keeps verification enabled outside a Web Crypto secure context", async () => {
    vi.stubGlobal("crypto", undefined);
    const bytes = new TextEncoder().encode("opensdl").buffer;
    expect(await sha256Hex(bytes)).toBe(
      "898491d817d61d100cabb0aea313ef6bad6e813ce8ea959a233406d96bcfd950",
    );
  });
});
