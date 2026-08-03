import type { AnimationClip, Group } from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

import { DataSourceError, loadExperience } from "./data-source";
import { requireSceneBindings } from "./scene-bindings";
import { SceneController, type SceneState } from "./scene-controller";
import { verifySceneBytes } from "./scene-integrity";
import { buildTimeline, type CueSegment, describeAction, timelineDuration } from "./timeline";
import type { LoadedExperience } from "./types";
import "./styles.css";

function required<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`viewer element #${id} is missing`);
  return element as T;
}

const elements = {
  app: required<HTMLElement>("app"),
  viewport: required<HTMLElement>("viewport"),
  revision: required<HTMLElement>("revision"),
  sourceLabel: required<HTMLElement>("source-label"),
  sourceDetail: required<HTMLElement>("source-detail"),
  cuePanel: required<HTMLElement>("cue-panel"),
  cueCapability: required<HTMLElement>("cue-capability"),
  cueAction: required<HTMLElement>("cue-action"),
  cueSequence: required<HTMLElement>("cue-sequence"),
  cueProperties: required<HTMLDListElement>("cue-properties"),
  loader: required<HTMLElement>("loader"),
  loaderLabel: required<HTMLElement>("loader-label"),
  loaderProgress: required<HTMLElement>("loader-progress"),
  failure: required<HTMLElement>("failure"),
  failureTitle: required<HTMLElement>("failure-title"),
  failureDetail: required<HTMLElement>("failure-detail"),
  retry: required<HTMLButtonElement>("retry"),
  play: required<HTMLButtonElement>("play"),
  reset: required<HTMLButtonElement>("reset"),
  timeline: required<HTMLInputElement>("timeline"),
  time: required<HTMLOutputElement>("time"),
};

const scene = new SceneController(elements.viewport);
let segments: CueSegment[] = [];
let durationMs = 0;
let timeMs = 0;
let playing = false;
let previousFrame = performance.now();
let lastCueId = "";

function runIdFromLocation(): string | undefined {
  const params = new URLSearchParams(window.location.search);
  const value = params.get("run") ?? params.get("run_id");
  return value?.trim() || undefined;
}

function formatTime(milliseconds: number): string {
  const totalSeconds = Math.floor(milliseconds / 1_000);
  const minutes = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, "0");
  const seconds = (totalSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function updateTransport(): void {
  elements.timeline.value = Math.round(timeMs).toString();
  elements.time.value = `${formatTime(timeMs)} / ${formatTime(durationMs)}`;
  elements.play.textContent = playing ? "Pause" : timeMs >= durationMs ? "Replay" : "Play";
  elements.play.setAttribute("aria-pressed", playing.toString());
}

function updateCue(state: SceneState): void {
  const cue = state.currentCue;
  if (!cue) {
    elements.cueCapability.textContent = segments.length === 0 ? "No visual events" : "Ready";
    elements.cueAction.textContent = segments.length === 0 ? "EMPTY" : "IDLE";
    elements.cueSequence.textContent = `0 / ${segments.length}`;
  } else if (cue.id !== lastCueId) {
    elements.cueCapability.textContent = cue.capabilityId;
    elements.cueAction.textContent = `${describeAction(cue.action)} · ${cue.phase.toLocaleUpperCase()}`;
    elements.cueSequence.textContent = `${state.currentSequence + 1} / ${segments.length}`;
    lastCueId = cue.id;
  }

  elements.cueProperties.replaceChildren();
  for (const [name, value] of state.properties) {
    const term = document.createElement("dt");
    term.textContent = name.replaceAll("_", " ");
    const description = document.createElement("dd");
    description.textContent = String(value);
    elements.cueProperties.append(term, description);
  }
  elements.cueProperties.hidden = state.properties.size === 0;
}

function frame(now: number): void {
  const delta = Math.min(now - previousFrame, 100);
  previousFrame = now;
  if (playing) {
    timeMs = Math.min(timeMs + delta, durationMs);
    if (timeMs >= durationMs) playing = false;
  }
  const state = scene.apply(segments, timeMs);
  updateCue(state);
  updateTransport();
  scene.render();
  requestAnimationFrame(frame);
}

interface LoadedModel {
  scene: Group;
  animations: AnimationClip[];
}

async function loadModel(url: string, expectedSha256: string): Promise<LoadedModel> {
  const response = await fetch(url, { headers: { Accept: "model/gltf-binary" } });
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
  const bytes = await response.arrayBuffer();
  await verifySceneBytes(bytes, expectedSha256);
  elements.loaderProgress.style.width = "78%";
  const loader = new GLTFLoader();
  return new Promise((resolve, reject) => {
    loader.parse(
      bytes,
      "",
      (gltf) => resolve({ scene: gltf.scene, animations: gltf.animations }),
      reject,
    );
  });
}

function setSource(experience: LoadedExperience): void {
  const live = experience.source === "live-run";
  elements.app.dataset.source = live ? "live" : "demo";
  elements.sourceLabel.textContent = live
    ? "PROJECTED RUN"
    : experience.source === "configured-scene"
      ? "CONFIGURED SCENE"
      : "LOCAL DEMO";
  elements.sourceDetail.textContent = experience.sourceDetail;
  elements.sourceDetail.title = experience.note ?? experience.sourceDetail;
}

async function start(): Promise<void> {
  playing = false;
  timeMs = 0;
  lastCueId = "";
  elements.app.dataset.state = "loading";
  elements.failure.hidden = true;
  elements.loader.hidden = false;
  elements.loaderLabel.textContent = "Loading twin definition";
  elements.loaderProgress.style.width = "8%";
  elements.play.disabled = true;
  elements.reset.disabled = true;
  elements.timeline.disabled = true;

  try {
    const experience = await loadExperience(runIdFromLocation());
    setSource(experience);
    elements.revision.textContent = experience.definition.revision;
    elements.loaderLabel.textContent = "Loading verified scene";
    elements.loaderProgress.style.width = "18%";
    const model = await loadModel(experience.sceneUrl, experience.definition.scene.sha256);
    elements.loaderLabel.textContent = "Binding twin entities";
    elements.loaderProgress.style.width = "94%";
    requireSceneBindings(experience.definition, model.scene);
    scene.mount(experience.definition, model.scene, model.animations);
    segments = buildTimeline(experience.projection.cues);
    durationMs = timelineDuration(segments);
    elements.timeline.max = Math.max(durationMs, 1).toString();
    elements.timeline.value = "0";
    elements.play.disabled = segments.length === 0;
    elements.reset.disabled = false;
    elements.timeline.disabled = segments.length === 0;
    elements.loader.hidden = true;
    elements.app.dataset.state = segments.length === 0 ? "empty" : "ready";
    updateTransport();
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown viewer error";
    elements.app.dataset.state = "error";
    elements.loader.hidden = true;
    elements.failure.hidden = false;
    elements.failureTitle.textContent =
      error instanceof DataSourceError
        ? "The projected run could not be loaded."
        : "The 3D scene could not be loaded.";
    elements.failureDetail.textContent = message;
  }
}

elements.play.addEventListener("click", () => {
  if (timeMs >= durationMs) timeMs = 0;
  playing = !playing;
});
elements.reset.addEventListener("click", () => {
  playing = false;
  timeMs = 0;
  scene.resetCamera();
});
elements.timeline.addEventListener("input", () => {
  playing = false;
  timeMs = Number(elements.timeline.value);
});
elements.retry.addEventListener("click", () => void start());
window.addEventListener("keydown", (event) => {
  if (event.target instanceof HTMLInputElement || event.target instanceof HTMLButtonElement) return;
  if (event.code === "Space") {
    event.preventDefault();
    elements.play.click();
  } else if (event.key.toLocaleLowerCase() === "r") {
    elements.reset.click();
  } else if (event.key === "ArrowRight") {
    playing = false;
    timeMs = Math.min(durationMs, timeMs + 500);
  } else if (event.key === "ArrowLeft") {
    playing = false;
    timeMs = Math.max(0, timeMs - 500);
  }
});

requestAnimationFrame(frame);
void start();

window.addEventListener("pagehide", () => scene.dispose(), { once: true });
