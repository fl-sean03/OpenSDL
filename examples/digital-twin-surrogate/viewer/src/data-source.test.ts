import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadExperience } from "./data-source";
import { DEMO_DEFINITION, DEMO_PROJECTION } from "./demo";

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("viewer data-source selection", () => {
  beforeEach(() => {
    vi.stubGlobal("window", {
      clearTimeout: globalThis.clearTimeout,
      setTimeout: globalThis.setTimeout,
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it("uses the included deterministic cues only for their exact scene", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(DEMO_DEFINITION)));

    const experience = await loadExperience();

    expect(experience.source).toBe("local-demo");
    expect(experience.projection).toEqual(DEMO_PROJECTION);
  });

  it("does not apply Flex-specific demo cues to another configured twin", async () => {
    const definition = structuredClone(DEMO_DEFINITION);
    definition.revision = "lab-specific-revision";
    definition.scene.sha256 = "a".repeat(64);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(definition)));

    const experience = await loadExperience();

    expect(experience.source).toBe("configured-scene");
    expect(experience.sourceDetail).toBe("NO RUN SELECTED");
    expect(experience.projection).toEqual({
      definition_revision: "lab-specific-revision",
      run_id: "",
      cues: [],
    });
  });
});
