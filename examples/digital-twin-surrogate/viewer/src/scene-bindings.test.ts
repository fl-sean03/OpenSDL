import { Group, Object3D } from "three";
import { describe, expect, it } from "vitest";

import { requireSceneBindings, unresolvedSceneBindings } from "./scene-bindings";
import type { TwinDefinition } from "./types";

function definition(): TwinDefinition {
  return {
    apiVersion: "opensdl.dev/v0alpha1",
    kind: "DigitalTwin",
    version: "0.1.0",
    revision: "binding-test",
    coordinateFrame: {
      unit: "m",
      handedness: "right",
      upAxis: "Z",
      origin: [0, 0, 0],
    },
    scene: { path: "scene.glb", sha256: "a".repeat(64) },
    entities: [{ id: "sample", node: "SampleCarrier", resources: [] }],
    anchors: [{ id: "output", node: "Anchor_Output", position: [0, 0, 0] }],
  };
}

describe("required scene bindings", () => {
  it("fails closed with every missing declared node", () => {
    const model = new Group();

    expect(unresolvedSceneBindings(definition(), model)).toEqual([
      "entity:sample",
      "anchor:output",
    ]);
    expect(() => requireSceneBindings(definition(), model)).toThrow(
      "Twin scene is missing required bindings: entity:sample, anchor:output",
    );
  });

  it("accepts a fully resolved scene", () => {
    const model = new Group();
    const sample = new Object3D();
    sample.name = "SampleCarrier";
    const output = new Object3D();
    output.name = "Anchor_Output";
    model.add(sample, output);

    expect(unresolvedSceneBindings(definition(), model)).toEqual([]);
    expect(() => requireSceneBindings(definition(), model)).not.toThrow();
  });
});
