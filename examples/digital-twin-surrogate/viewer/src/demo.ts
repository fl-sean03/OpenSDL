import type { TwinCue, TwinDefinition, TwinProjection } from "./types";

export const DEMO_SCENE_URL = "/__opensdl_demo__/scene.glb";

export const DEMO_DEFINITION: TwinDefinition = {
  apiVersion: "opensdl.dev/v0alpha1",
  kind: "DigitalTwin",
  version: "0.1.0",
  revision: "open-frame-self-driving-cell-2026-08-04",
  coordinateFrame: {
    unit: "m",
    handedness: "right",
    upAxis: "Z",
    origin: [0, 0, 0],
  },
  scene: {
    path: "scene/assets/surrogate-cell.glb",
    sha256: "d9a1fae5d345b92a6c1bb79e7d7043e3ad899580fa3c5df092a3dd450d2a64f0",
  },
  entities: [
    { id: "cell", node: "CellRoot", resources: [] },
    { id: "sample", node: "SampleCarrier", resources: [] },
    { id: "mover", node: "Mover", resources: ["cell-transport"] },
    { id: "gripper-head", node: "GripperHead", resources: ["cell-transport"] },
    { id: "pipette-head", node: "PipetteHead", resources: ["cell-dispenser"] },
    { id: "mixer-rotor", node: "MixerRotor", resources: ["cell-mixer"] },
    {
      id: "characterizer",
      node: "CharacterizerHousing",
      resources: ["cell-characterizer"],
    },
    {
      id: "characterizer-door",
      node: "CharacterizerDoor",
      resources: ["cell-characterizer"],
    },
  ],
  anchors: [
    { id: "input", node: "Anchor_Input", position: [-1.56, -0.0535, 1.16865] },
    { id: "dispense", node: "Anchor_Dispense", position: [-0.78, -0.0535, 1.14965] },
    { id: "mix", node: "Anchor_Mix", position: [0.0, -0.0535, 1.22615] },
    {
      id: "characterize",
      node: "Anchor_Characterize",
      position: [0.78, -0.0535, 1.17065],
    },
    { id: "output", node: "Anchor_Output", position: [1.56, -0.0535, 1.16865] },
  ],
  animationTimeline: {
    frameRate: 24,
    frameStart: 1,
    frameEnd: 960,
    bindings: [
      {
        id: "input-to-dispense",
        action: "transfer",
        parameterMatch: { source: "input", destination: "dispense" },
        frameStart: 1,
        frameEnd: 150,
      },
      {
        id: "dispense-cycle",
        action: "play_clip",
        parameterMatch: { clip: "dispense_cycle" },
        frameStart: 208,
        frameEnd: 552,
      },
      {
        id: "dispense-to-mix",
        action: "transfer",
        parameterMatch: { source: "dispense", destination: "mix" },
        frameStart: 612,
        frameEnd: 672,
      },
      {
        id: "mix-cycle",
        action: "play_clip",
        parameterMatch: { clip: "mix_cycle" },
        frameStart: 672,
        frameEnd: 724,
      },
      {
        id: "mix-to-characterize",
        action: "transfer",
        parameterMatch: { source: "mix", destination: "characterize" },
        frameStart: 724,
        frameEnd: 770,
      },
      {
        id: "characterize-cycle",
        action: "play_clip",
        parameterMatch: { clip: "characterize_cycle" },
        frameStart: 776,
        frameEnd: 892,
      },
      {
        id: "characterize-to-output",
        action: "transfer",
        parameterMatch: { source: "characterize", destination: "output" },
        frameStart: 898,
        frameEnd: 960,
      },
    ],
  },
};

const DEMO_RUN_STARTED_MS = Date.UTC(2026, 7, 3, 12, 0, 0);

/**
 * Millisecond offsets from the first event of the included run, indexed by cue sequence.
 *
 * The surrogate cell is configured with `latency_seconds: 0`, and its adapter only awaits when that
 * value is truthy, so a simulated run records every event within a few milliseconds. These offsets
 * reproduce that timing profile: uneven, often repeating inside a single millisecond, and far under
 * a second end to end. They keep the run's reported wall clock faithful to what this run is.
 *
 * They are deliberately not one-per-second. An earlier fixture placed the cue sequence number in
 * the seconds field, which reported a nineteen-second duration the run never took.
 */
const CUE_OFFSETS_MS: readonly number[] = [
  // cell.transfer_labware: input -> dispense
  0, 1, 1,
  // cell.dispense
  2, 4, 4, 4,
  // cell.transfer_labware: dispense -> mix
  5, 6, 6,
  // cell.mix
  8, 8,
  // cell.transfer_labware: mix -> characterize
  9, 10, 10,
  // cell.characterize
  12, 12,
  // cell.transfer_labware: characterize -> output
  13, 14, 14,
];

function occurredAtFor(sequence: number): string {
  const offsetMs = CUE_OFFSETS_MS[sequence];
  if (offsetMs === undefined) {
    throw new Error(`demo cue ${sequence} has no recorded offset`);
  }
  return new Date(DEMO_RUN_STARTED_MS + offsetMs).toISOString();
}

function cue(
  sequence: number,
  capabilityId: string,
  phase: TwinCue["phase"],
  action: TwinCue["action"],
  target: string,
  parameters: Record<string, unknown>,
): TwinCue {
  return {
    id: `demo-cue-${sequence.toString().padStart(2, "0")}`,
    sequence,
    sourceEventId: `demo-event-${sequence.toString().padStart(2, "0")}`,
    runId: "included-demo",
    taskId: `demo-task-${sequence.toString().padStart(2, "0")}`,
    capabilityId,
    occurredAt: occurredAtFor(sequence),
    phase,
    action,
    target,
    parameters,
  };
}

export const DEMO_PROJECTION: TwinProjection = {
  definition_revision: DEMO_DEFINITION.revision,
  run_id: "included-demo",
  cues: [
    cue(0, "cell.transfer_labware", "started", "highlight", "mover", {
      active: true,
      tone: "cyan",
    }),
    cue(1, "cell.transfer_labware", "succeeded", "transfer", "sample", {
      source: "input",
      destination: "dispense",
      labware: "showcase-plate-001",
    }),
    cue(2, "cell.transfer_labware", "succeeded", "highlight", "mover", {
      active: false,
      tone: "cyan",
    }),
    cue(3, "cell.dispense", "started", "highlight", "pipette-head", {
      active: true,
      tone: "violet",
    }),
    cue(4, "cell.dispense", "succeeded", "play_clip", "pipette-head", {
      clip: "dispense_cycle",
    }),
    cue(5, "cell.dispense", "succeeded", "set_property", "sample", {
      property: "volume_per_well_ul",
      value: 100,
    }),
    cue(6, "cell.dispense", "succeeded", "highlight", "pipette-head", {
      active: false,
      tone: "violet",
    }),
    cue(7, "cell.transfer_labware", "started", "highlight", "mover", {
      active: true,
      tone: "cyan",
    }),
    cue(8, "cell.transfer_labware", "succeeded", "transfer", "sample", {
      source: "dispense",
      destination: "mix",
      labware: "showcase-plate-001",
    }),
    cue(9, "cell.transfer_labware", "succeeded", "highlight", "mover", {
      active: false,
      tone: "cyan",
    }),
    cue(10, "cell.mix", "succeeded", "play_clip", "mixer-rotor", {
      clip: "mix_cycle",
    }),
    cue(11, "cell.mix", "succeeded", "set_property", "sample", {
      property: "mixed",
      value: true,
    }),
    cue(12, "cell.transfer_labware", "started", "highlight", "mover", {
      active: true,
      tone: "cyan",
    }),
    cue(13, "cell.transfer_labware", "succeeded", "transfer", "sample", {
      source: "mix",
      destination: "characterize",
      labware: "showcase-plate-001",
    }),
    cue(14, "cell.transfer_labware", "succeeded", "highlight", "mover", {
      active: false,
      tone: "cyan",
    }),
    cue(15, "cell.characterize", "succeeded", "play_clip", "characterizer-door", {
      clip: "characterize_cycle",
    }),
    cue(16, "cell.characterize", "succeeded", "set_property", "sample", {
      property: "normalized_response",
      value: 0.56,
    }),
    cue(17, "cell.transfer_labware", "started", "highlight", "mover", {
      active: true,
      tone: "cyan",
    }),
    cue(18, "cell.transfer_labware", "succeeded", "transfer", "sample", {
      source: "characterize",
      destination: "output",
      labware: "showcase-plate-001",
    }),
    cue(19, "cell.transfer_labware", "succeeded", "highlight", "mover", {
      active: false,
      tone: "cyan",
    }),
  ],
};
