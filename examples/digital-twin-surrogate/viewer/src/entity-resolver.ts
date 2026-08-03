import type { Object3D } from "three";

import type { TwinAnchor, TwinEntity } from "./types";

const ENTITY_EXTRA_KEYS = [
  "opensdlEntityId",
  "opensdl_entity_id",
  "entityId",
  "entity_id",
  "opensdlId",
];
const ANCHOR_EXTRA_KEYS = ["opensdlAnchorId", "opensdl_anchor_id", "anchorId", "anchor_id"];

function normalize(value: string): string {
  return value.toLocaleLowerCase().replace(/[^a-z0-9]/g, "");
}

function extraEquals(object: Object3D, keys: string[], expected: string): boolean {
  return keys.some((key) => {
    const value = object.userData[key];
    return typeof value === "string" && normalize(value) === normalize(expected);
  });
}

function resolve(
  root: Object3D,
  expectedName: string | undefined,
  logicalId: string,
  extraKeys: string[],
): Object3D | undefined {
  const objects: Object3D[] = [];
  root.traverse((object) => objects.push(object));

  if (expectedName) {
    const exact = objects.find((object) => object.name === expectedName);
    if (exact) return exact;
  }
  const extra = objects.find((object) => extraEquals(object, extraKeys, logicalId));
  if (extra) return extra;
  if (expectedName) {
    const normalizedName = normalize(expectedName);
    const normalized = objects.find((object) => normalize(object.name) === normalizedName);
    if (normalized) return normalized;
    const suffixed = objects.find((object) => normalize(object.name).startsWith(normalizedName));
    if (suffixed) return suffixed;
  }
  return objects.find((object) => normalize(object.name) === normalize(logicalId));
}

export function resolveEntity(root: Object3D, entity: TwinEntity): Object3D | undefined {
  return resolve(root, entity.node, entity.id, ENTITY_EXTRA_KEYS);
}

export function resolveAnchor(root: Object3D, anchor: TwinAnchor): Object3D | undefined {
  return resolve(root, anchor.node, anchor.id, ANCHOR_EXTRA_KEYS);
}
