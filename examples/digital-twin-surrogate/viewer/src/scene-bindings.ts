import type { Object3D } from "three";

import { resolveAnchor, resolveEntity } from "./entity-resolver";
import type { TwinDefinition } from "./types";

export function unresolvedSceneBindings(definition: TwinDefinition, model: Object3D): string[] {
  const missing = definition.entities
    .filter((entity) => !resolveEntity(model, entity))
    .map((entity) => `entity:${entity.id}`);
  for (const anchor of definition.anchors) {
    if (anchor.node && !resolveAnchor(model, anchor)) missing.push(`anchor:${anchor.id}`);
  }
  return missing;
}

export function requireSceneBindings(definition: TwinDefinition, model: Object3D): void {
  const missing = unresolvedSceneBindings(definition, model);
  if (missing.length > 0) {
    throw new Error(`Twin scene is missing required bindings: ${missing.join(", ")}`);
  }
}
