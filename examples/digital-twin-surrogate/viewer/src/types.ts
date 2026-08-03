export type TwinAction = "highlight" | "transfer" | "play_clip" | "set_property";

export interface CoordinateFrame {
  unit: string;
  handedness: "left" | "right";
  upAxis: "X" | "Y" | "Z";
  origin: [number, number, number];
}

export interface TwinEntity {
  id: string;
  node: string;
  resources: string[];
}

export interface TwinAnchor {
  id: string;
  node?: string;
  position: [number, number, number];
}

export interface AnimationBinding {
  id: string;
  action: TwinAction;
  parameterMatch: Record<string, unknown>;
  frameStart: number;
  frameEnd: number;
}

export interface AnimationTimeline {
  frameRate: number;
  frameStart: number;
  frameEnd: number;
  bindings: AnimationBinding[];
}

export interface TwinDefinition {
  apiVersion: "opensdl.dev/v0alpha1";
  kind: "DigitalTwin";
  version: string;
  revision: string;
  coordinateFrame: CoordinateFrame;
  scene: {
    path: string;
    sha256: string;
  };
  entities: TwinEntity[];
  anchors: TwinAnchor[];
  animationTimeline?: AnimationTimeline;
}

export interface TwinCue {
  id: string;
  sequence: number;
  sourceEventId: string;
  runId: string | null;
  taskId: string;
  capabilityId: string;
  occurredAt: string;
  phase: "started" | "retrying" | "succeeded" | "failed" | "cancelled" | "intervention_required";
  action: TwinAction;
  target: string;
  parameters: Record<string, unknown>;
}

export interface TwinProjection {
  definition_revision: string;
  run_id: string;
  cues: TwinCue[];
}

export interface LoadedExperience {
  definition: TwinDefinition;
  projection: TwinProjection;
  sceneUrl: string;
  source: "configured-scene" | "live-run" | "local-demo";
  sourceDetail: string;
  note?: string;
}
