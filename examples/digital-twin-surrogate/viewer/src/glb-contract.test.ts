import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { DEMO_DEFINITION } from "./demo";

const gltfValidator = createRequire(import.meta.url)("gltf-validator") as {
  validateBytes: (
    bytes: Uint8Array,
    options: { maxIssues: number; uri: string },
  ) => Promise<{
    issues: {
      numErrors: number;
      numHints: number;
      numInfos: number;
      numWarnings: number;
    };
  }>;
};

interface GlbAccessor {
  min?: number[];
  max?: number[];
}

interface GlbDocument {
  accessors?: GlbAccessor[];
  animations?: Array<{ samplers: Array<{ input: number }> }>;
  nodes?: Array<{ name?: string }>;
}

function readGlb(): { bytes: Buffer; document: GlbDocument } {
  const path = fileURLToPath(new URL("../../scene/assets/surrogate-cell.glb", import.meta.url));
  const bytes = readFileSync(path);
  expect(bytes.toString("ascii", 0, 4)).toBe("glTF");
  const jsonLength = bytes.readUInt32LE(12);
  expect(bytes.toString("ascii", 16, 20)).toBe("JSON");
  const document = JSON.parse(bytes.toString("utf8", 20, 20 + jsonLength)) as GlbDocument;
  return { bytes, document };
}

describe("checked-in GLB contract", () => {
  it("matches the pinned digest and every required scene binding", () => {
    const { bytes, document } = readGlb();
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(DEMO_DEFINITION.scene.sha256);

    const nodeNames = new Set((document.nodes ?? []).map((node) => node.name));
    const required = [
      ...DEMO_DEFINITION.entities.map((entity) => entity.node),
      ...DEMO_DEFINITION.anchors.flatMap((anchor) => (anchor.node ? [anchor.node] : [])),
    ];
    expect(required.filter((name) => !nodeNames.has(name))).toEqual([]);
  });

  it("contains authored animation across the declared shared frame clock", () => {
    const { document } = readGlb();
    const animations = document.animations ?? [];
    const accessors = document.accessors ?? [];
    expect(animations.length).toBeGreaterThan(0);

    const ranges = animations.flatMap((animation) =>
      animation.samplers.flatMap((sampler) => {
        const accessor = accessors[sampler.input];
        const start = accessor?.min?.[0];
        const end = accessor?.max?.[0];
        return start === undefined || end === undefined ? [] : [{ start, end }];
      }),
    );
    const earliest = Math.min(...ranges.map((range) => range.start));
    const latest = Math.max(...ranges.map((range) => range.end));
    const timeline = DEMO_DEFINITION.animationTimeline;
    if (!timeline) throw new Error("demo definition has no animation timeline");
    expect(earliest).toBeLessThanOrEqual(timeline.frameStart / timeline.frameRate);
    expect(latest).toBeGreaterThanOrEqual(timeline.frameEnd / timeline.frameRate);
    for (const binding of timeline.bindings) {
      expect(binding.frameStart / timeline.frameRate).toBeGreaterThanOrEqual(earliest);
      expect(binding.frameEnd / timeline.frameRate).toBeLessThanOrEqual(latest);
    }
  });

  it("passes the Khronos glTF validator without issues", async () => {
    const { bytes } = readGlb();
    const report = await gltfValidator.validateBytes(new Uint8Array(bytes), {
      uri: DEMO_DEFINITION.scene.path,
      maxIssues: 5_000,
    });
    expect(report.issues).toMatchObject({
      numErrors: 0,
      numWarnings: 0,
      numInfos: 0,
      numHints: 0,
    });
  });
});
