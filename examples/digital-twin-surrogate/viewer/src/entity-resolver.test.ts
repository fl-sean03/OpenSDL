import { Group, Object3D } from "three";
import { describe, expect, it } from "vitest";

import { resolveAnchor, resolveEntity } from "./entity-resolver";

describe("scene binding", () => {
  it("prefers the exact GLB node name", () => {
    const root = new Group();
    const node = new Object3D();
    node.name = "SampleCarrier";
    root.add(node);

    expect(resolveEntity(root, { id: "sample", node: "SampleCarrier", resources: [] })).toBe(node);
  });

  it("resolves entities from exported GLB extras when names change", () => {
    const root = new Group();
    const node = new Object3D();
    node.name = "PlateAssembly.001";
    node.userData.opensdlEntityId = "sample";
    root.add(node);

    expect(resolveEntity(root, { id: "sample", node: "SampleCarrier", resources: [] })).toBe(node);
  });

  it("tolerates Blender suffixes on named anchor nodes", () => {
    const root = new Group();
    const node = new Object3D();
    node.name = "Anchor_Output.001";
    root.add(node);

    expect(resolveAnchor(root, { id: "output", node: "Anchor_Output", position: [0, 0, 0] })).toBe(
      node,
    );
  });
});
