# Digital-twin viewer

This directory contains the read-only Three.js viewer for the surrogate-cell example. It consumes
the same engine-neutral twin definition and projected cue timeline exposed by the OpenSDL API. It
does not expose equipment commands or write runtime state.

## Run the included demo

```bash
cd examples/digital-twin-surrogate/viewer
npm ci
npm run dev
```

Open `http://127.0.0.1:4173/viewer/`. The Vite development server serves the generated GLB. If the
OpenSDL API is unavailable, the viewer uses its included reference definition and deterministic cue
sequence.

## View a persisted run

Build the static viewer and start the OpenSDL API with the example manifest:

```bash
cd examples/digital-twin-surrogate/viewer
npm run build
cd ../../../
uv run --locked opensdl-api --manifest examples/digital-twin-surrogate/opensdl.yaml
```

Open `/viewer?run=<run-id>` on the API origin. The viewer reads:

- `GET /twin` for the definition and logical scene bindings;
- `GET /twin/scene.glb` for the verified scene artifact; and
- `GET /twin/runs/{run_id}` for the immutable projected cue sequence.

Each read happens once, when the viewer opens. The viewer does not poll and holds no subscription,
so a selected run is labelled `STORED RUN` and shows that run exactly as it was persisted. Reload
to pick up a different run. Read-only live event projection remains deferred; see
`docs/development/backlog.md`.

Without `?run=`, the included cue sequence applies only when the configured revision and scene
digest match the included showcase. Another configured twin opens with an empty timeline and asks
for a run identifier. `?run_id=` is also accepted for compatibility.

The API recalculates the scene digest for every GLB response. The browser calculates it again before
parsing the downloaded bytes. It stops loading when a declared entity or anchor node is absent.

The showcase definition maps projected cues to authored GLB frames through `animationTimeline`.
Playback scrubs those frame ranges on one global animation clock. Playback remains local and
read-only in every mode.

## Playback timing

Playback runs on fixed per-action durations so authored motion stays legible. This is stylized
sequence pacing, not a time-accurate replay. The transport clock measures position in the cue
sequence, and the viewer never derives it from event timestamps. The transport labels it as such.

Recorded timing stays visible instead of being implied. The cue panel reports the recorded instant
of the current cue and the run's wall-clock duration, taken from the first projected cue to the
last. The surrogate cell runs with `latency_seconds: 0`, so a run records that duration in
milliseconds; a reading such as `0 ms` is the honest answer, not a missing value.

The included demo carries the same profile, reporting `14 ms` of recorded time against 25.6 s of
stylized playback. That gap is the point: the two clocks measure different things, and only one of
them is a duration the run actually took.

## Controls

- drag to orbit and scroll to zoom;
- use **Play**, the scrubber, or <kbd>Space</kbd> for playback;
- use the arrow keys to move the sequence clock in 500 ms increments; and
- use **Reset** or <kbd>R</kbd> to reset the timeline and camera.

## Check the viewer

```bash
npm test
npm run lint
npm run typecheck
npm run build
```

`static/` is the Vite build consumed by `spec.twin.viewer_root` in the example manifest.
