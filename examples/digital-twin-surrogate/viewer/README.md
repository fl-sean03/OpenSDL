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

Without `?run=`, the included cue sequence applies only when the configured revision and scene
digest match the included showcase. Another configured twin opens with an empty timeline and asks
for a run identifier. `?run_id=` is also accepted for compatibility.

The API recalculates the scene digest for every GLB response. The browser calculates it again before
parsing the downloaded bytes. It stops loading when a declared entity or anchor node is absent.

The showcase definition maps projected cues to authored GLB frames through `animationTimeline`.
Playback scrubs those frame ranges on one global animation clock. Playback remains local and
read-only in every mode.

## Controls

- drag to orbit and scroll to zoom;
- use **Play**, the scrubber, or <kbd>Space</kbd> for playback;
- use the arrow keys to move in 500 ms increments; and
- use **Reset** or <kbd>R</kbd> to reset the timeline and camera.

## Check the viewer

```bash
npm test
npm run lint
npm run typecheck
npm run build
```

`static/` is the Vite build consumed by `spec.twin.viewer_root` in the example manifest.
