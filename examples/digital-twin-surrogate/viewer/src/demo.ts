import type { TwinCue, TwinDefinition, TwinProjection } from "./types";

export const DEMO_SCENE_URL = "/__opensdl_demo__/scene.glb";

export const DEMO_DEFINITION: TwinDefinition = {
  apiVersion: "opensdl.dev/v0alpha1",
  kind: "DigitalTwin",
  version: "0.1.0",
  revision: "flex-class-surrogate-cell-2026-08-03",
  coordinateFrame: {
    unit: "m",
    handedness: "right",
    upAxis: "Z",
    origin: [0, 0, 0],
  },
  scene: {
    path: "scene/assets/surrogate-cell.glb",
    sha256: "4e633af41f9801002f530496541f2922ee38e9ed3bc35da974f0e335478143dc",
  },
  entities: [
    { id: "cell", node: "CellRoot", resources: [] },
    { id: "sample", node: "SampleCarrier", resources: [] },
    { id: "robot", node: "RobotCarriage", resources: ["cell-transport"] },
    { id: "dispenser-head", node: "DispenserHead", resources: ["cell-dispenser"] },
    { id: "mixer-rotor", node: "MixerRotor", resources: ["cell-mixer"] },
    {
      id: "plate-reader",
      node: "ColorimeterHousing",
      resources: ["cell-characterizer"],
    },
    {
      id: "characterizer-door",
      node: "ColorimeterDoor",
      resources: ["cell-characterizer"],
    },
  ],
  anchors: [
    { id: "input", node: "Anchor_Input", position: [0.164, 0.1605, 1.16865] },
    { id: "dispenser", node: "Anchor_Dispenser", position: [-0.164, 0.0535, 1.14965] },
    { id: "mixer", node: "Anchor_Mixer", position: [-0.164, -0.0535, 1.22615] },
    {
      id: "characterizer",
      node: "Anchor_Colorimeter",
      position: [0.164, -0.1605, 1.17065],
    },
    { id: "output", node: "Anchor_Output", position: [0.164, 0.0535, 1.16865] },
  ],
  animationTimeline: {
    frameRate: 24,
    frameStart: 1,
    frameEnd: 960,
    bindings: [
      {
        id: "input-to-dispenser",
        action: "transfer",
        parameterMatch: { source: "input", destination: "dispenser" },
        frameStart: 1,
        frameEnd: 160,
      },
      {
        id: "dispense-cycle",
        action: "play_clip",
        parameterMatch: { clip: "dispense_cycle" },
        frameStart: 164,
        frameEnd: 508,
      },
      {
        id: "dispenser-to-mixer",
        action: "transfer",
        parameterMatch: { source: "dispenser", destination: "mixer" },
        frameStart: 516,
        frameEnd: 574,
      },
      {
        id: "mix-cycle",
        action: "play_clip",
        parameterMatch: { clip: "mix_cycle" },
        frameStart: 574,
        frameEnd: 634,
      },
      {
        id: "mixer-to-characterizer",
        action: "transfer",
        parameterMatch: { source: "mixer", destination: "characterizer" },
        frameStart: 634,
        frameEnd: 684,
      },
      {
        id: "characterize-cycle",
        action: "play_clip",
        parameterMatch: { clip: "characterize_cycle" },
        frameStart: 692,
        frameEnd: 848,
      },
      {
        id: "characterizer-to-output",
        action: "transfer",
        parameterMatch: { source: "characterizer", destination: "output" },
        frameStart: 854,
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
  // cell.transfer_labware: input -> dispenser
  0, 1, 1,
  // cell.dispense
  2, 4, 4, 4,
  // cell.transfer_labware: dispenser -> mixer
  5, 6, 6,
  // cell.mix
  8, 8,
  // cell.transfer_labware: mixer -> characterizer
  9, 10, 10,
  // cell.characterize
  12, 12,
  // cell.transfer_labware: characterizer -> output
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
    cue(0, "cell.transfer_labware", "started", "highlight", "robot", {
      active: true,
      tone: "cyan",
    }),
    cue(1, "cell.transfer_labware", "succeeded", "transfer", "sample", {
      source: "input",
      destination: "dispenser",
      labware: "showcase-plate-001",
    }),
    cue(2, "cell.transfer_labware", "succeeded", "highlight", "robot", {
      active: false,
      tone: "cyan",
    }),
    cue(3, "cell.dispense", "started", "highlight", "dispenser-head", {
      active: true,
      tone: "violet",
    }),
    cue(4, "cell.dispense", "succeeded", "play_clip", "dispenser-head", {
      clip: "dispense_cycle",
    }),
    cue(5, "cell.dispense", "succeeded", "set_property", "sample", {
      property: "volume_per_well_ul",
      value: 100,
    }),
    cue(6, "cell.dispense", "succeeded", "highlight", "dispenser-head", {
      active: false,
      tone: "violet",
    }),
    cue(7, "cell.transfer_labware", "started", "highlight", "robot", {
      active: true,
      tone: "cyan",
    }),
    cue(8, "cell.transfer_labware", "succeeded", "transfer", "sample", {
      source: "dispenser",
      destination: "mixer",
      labware: "showcase-plate-001",
    }),
    cue(9, "cell.transfer_labware", "succeeded", "highlight", "robot", {
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
    cue(12, "cell.transfer_labware", "started", "highlight", "robot", {
      active: true,
      tone: "cyan",
    }),
    cue(13, "cell.transfer_labware", "succeeded", "transfer", "sample", {
      source: "mixer",
      destination: "characterizer",
      labware: "showcase-plate-001",
    }),
    cue(14, "cell.transfer_labware", "succeeded", "highlight", "robot", {
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
    cue(17, "cell.transfer_labware", "started", "highlight", "robot", {
      active: true,
      tone: "cyan",
    }),
    cue(18, "cell.transfer_labware", "succeeded", "transfer", "sample", {
      source: "characterizer",
      destination: "output",
      labware: "showcase-plate-001",
    }),
    cue(19, "cell.transfer_labware", "succeeded", "highlight", "robot", {
      active: false,
      tone: "cyan",
    }),
  ],
};
