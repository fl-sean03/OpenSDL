import {
  ACESFilmicToneMapping,
  type AnimationAction,
  type AnimationClip,
  AnimationMixer,
  Box3,
  BoxHelper,
  Color,
  DirectionalLight,
  type Group,
  HemisphereLight,
  LoopOnce,
  MathUtils,
  type Object3D,
  PerspectiveCamera,
  type Quaternion,
  Scene,
  SRGBColorSpace,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import { animationTimeSeconds, bindingForCue } from "./authored-motion";
import { resolveAnchor, resolveEntity } from "./entity-resolver";
import { mixerOffset, readerLidOffset } from "./semantic-motion";
import { type CueSegment, evaluateTimeline } from "./timeline";
import type { TwinAnchor, TwinCue, TwinDefinition } from "./types";

interface Baseline {
  position: Vector3;
  quaternion: Quaternion;
  scale: Vector3;
}

export interface SceneState {
  currentCue?: TwinCue;
  currentSequence: number;
  properties: ReadonlyMap<string, unknown>;
}

const ACCENT = 0xff5a36;
const HIGHLIGHT_COLORS: Record<string, number> = {
  amber: 0xffb020,
  cyan: 0x27d9e8,
  red: 0xff3b30,
  violet: 0xa978ff,
};

export class SceneController {
  private readonly container: HTMLElement;
  private readonly scene = new Scene();
  private readonly camera = new PerspectiveCamera(43, 1, 0.01, 100);
  private readonly renderer: WebGLRenderer;
  private readonly controls: OrbitControls;
  private readonly resizeObserver: ResizeObserver;
  private model?: Group;
  private definition?: TwinDefinition;
  private entities = new Map<string, Object3D>();
  private anchors = new Map<string, Object3D>();
  private anchorDefinitions = new Map<string, TwinAnchor>();
  private baselines = new Map<Object3D, Baseline>();
  private highlights = new Map<string, BoxHelper>();
  private sampleProperties = new Map<string, unknown>();
  private animationMixer?: AnimationMixer;
  private animationActions: AnimationAction[] = [];

  constructor(container: HTMLElement) {
    this.container = container;
    this.scene.background = new Color(0x101313);
    this.renderer = new WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
    });
    this.renderer.outputColorSpace = SRGBColorSpace;
    this.renderer.toneMapping = ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 0.96;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.domElement.setAttribute("aria-hidden", "true");
    container.append(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 0.35;
    this.controls.maxDistance = 8;
    this.controls.maxPolarAngle = MathUtils.degToRad(86);

    const sky = new HemisphereLight(0xe9f2f2, 0x242019, 2.2);
    this.scene.add(sky);
    const key = new DirectionalLight(0xfff7e9, 4.2);
    key.position.set(-3.5, 5.5, 4.5);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    this.scene.add(key);
    const fill = new DirectionalLight(0xb7d5e2, 1.4);
    fill.position.set(3, 2.5, -2.5);
    this.scene.add(fill);

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
  }

  mount(definition: TwinDefinition, model: Group, animations: AnimationClip[] = []): string[] {
    if (this.animationMixer && this.model) {
      this.animationMixer.stopAllAction();
      this.animationMixer.uncacheRoot(this.model);
    }
    if (this.model) this.scene.remove(this.model);
    this.model = model;
    this.definition = definition;
    this.scene.add(model);
    this.entities.clear();
    this.anchors.clear();
    this.anchorDefinitions = new Map(definition.anchors.map((anchor) => [anchor.id, anchor]));
    this.baselines.clear();
    this.highlights.forEach((helper) => {
      this.scene.remove(helper);
    });
    this.highlights.clear();
    this.animationMixer = undefined;
    this.animationActions = [];

    const missing: string[] = [];
    for (const entity of definition.entities) {
      const object = resolveEntity(model, entity);
      if (!object) {
        missing.push(`entity:${entity.id}`);
        continue;
      }
      this.entities.set(entity.id, object);
      this.captureBaseline(object);
      const helper = new BoxHelper(object, ACCENT);
      helper.visible = false;
      const material = helper.material;
      material.transparent = true;
      material.opacity = 0.82;
      material.depthTest = false;
      this.scene.add(helper);
      this.highlights.set(entity.id, helper);
    }
    for (const anchor of definition.anchors) {
      const object = resolveAnchor(model, anchor);
      if (!object) {
        if (anchor.node) missing.push(`anchor:${anchor.id}`);
        continue;
      }
      this.anchors.set(anchor.id, object);
    }

    model.traverse((object) => {
      if ("isMesh" in object && object.isMesh === true) {
        const mesh = object as Object3D & { castShadow: boolean; receiveShadow: boolean };
        mesh.castShadow = true;
        mesh.receiveShadow = true;
      }
    });
    model.updateMatrixWorld(true);
    if (definition.animationTimeline && animations.length > 0) {
      this.animationMixer = new AnimationMixer(model);
      for (const clip of animations) {
        const action = this.animationMixer.clipAction(clip);
        action.setLoop(LoopOnce, 1);
        action.clampWhenFinished = true;
        action.play();
        this.animationActions.push(action);
      }
      this.animationMixer.setTime(
        definition.animationTimeline.frameStart / definition.animationTimeline.frameRate,
      );
      model.updateMatrixWorld(true);
    }
    this.frameModel();
    return missing;
  }

  apply(segments: CueSegment[], timeMs: number): SceneState {
    this.resetVisualState();
    const timeline = evaluateTimeline(segments, timeMs);
    for (const segment of timeline.completed) this.applyCue(segment.cue, 1);
    if (timeline.current) this.applyCue(timeline.current.cue, timeline.progress);
    this.model?.updateMatrixWorld(true);
    this.highlights.forEach((helper) => {
      helper.update();
    });
    return {
      currentCue: timeline.current?.cue ?? timeline.completed.at(-1)?.cue,
      currentSequence:
        timeline.current?.cue.sequence ?? timeline.completed.at(-1)?.cue.sequence ?? -1,
      properties: this.sampleProperties,
    };
  }

  render(): void {
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  resetCamera(): void {
    this.frameModel();
  }

  dispose(): void {
    this.resizeObserver.disconnect();
    this.controls.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }

  private captureBaseline(object: Object3D): void {
    this.baselines.set(object, {
      position: object.position.clone(),
      quaternion: object.quaternion.clone(),
      scale: object.scale.clone(),
    });
  }

  private resetVisualState(): void {
    for (const [object, baseline] of this.baselines) {
      object.position.copy(baseline.position);
      object.quaternion.copy(baseline.quaternion);
      object.scale.copy(baseline.scale);
    }
    this.highlights.forEach((helper) => {
      helper.visible = false;
    });
    this.sampleProperties.clear();
    if (this.animationMixer && this.definition?.animationTimeline) {
      const timeline = this.definition.animationTimeline;
      this.scrubAuthoredAnimation(timeline.frameStart / timeline.frameRate);
    }
    this.model?.updateMatrixWorld(true);
  }

  private applyCue(cue: TwinCue, progress: number): void {
    const authored = this.applyAuthoredMotion(cue, progress);
    switch (cue.action) {
      case "highlight":
        this.applyHighlight(cue, progress);
        break;
      case "transfer":
        if (!authored) this.applyTransfer(cue, progress);
        break;
      case "play_clip":
        if (!authored) this.applySemanticMotion(cue, progress);
        break;
      case "set_property":
        if (progress >= 0.5) {
          const property = cue.parameters.property;
          if (typeof property === "string")
            this.sampleProperties.set(property, cue.parameters.value);
        }
        break;
    }
  }

  private applyHighlight(cue: TwinCue, progress: number): void {
    const helper = this.highlights.get(cue.target);
    if (!helper) return;
    const active = cue.parameters.active !== false;
    helper.visible = active && progress > 0.08;
    helper.material.opacity = 0.38 + Math.sin(progress * Math.PI) * 0.5;
    const tone = typeof cue.parameters.tone === "string" ? cue.parameters.tone : "";
    helper.material.color.setHex(HIGHLIGHT_COLORS[tone] ?? ACCENT);
  }

  private applyAuthoredMotion(cue: TwinCue, progress: number): boolean {
    const timeline = this.definition?.animationTimeline;
    const binding = bindingForCue(timeline, cue);
    if (!timeline || !binding || !this.animationMixer) return false;
    this.scrubAuthoredAnimation(animationTimeSeconds(timeline, binding, progress));
    return true;
  }

  private scrubAuthoredAnimation(timeSeconds: number): void {
    if (!this.animationMixer) return;
    for (const action of this.animationActions) {
      action.enabled = true;
      action.paused = false;
      action.play();
    }
    this.animationMixer.setTime(timeSeconds);
  }

  private applyTransfer(cue: TwinCue, progress: number): void {
    const object = this.entities.get(cue.target);
    const source = typeof cue.parameters.source === "string" ? cue.parameters.source : undefined;
    const destination =
      typeof cue.parameters.destination === "string" ? cue.parameters.destination : undefined;
    if (!object || !source || !destination) return;
    const sourcePosition = this.anchorWorldPosition(source);
    const destinationPosition = this.anchorWorldPosition(destination);
    if (!sourcePosition || !destinationPosition) return;

    const eased = progress * progress * (3 - 2 * progress);
    const worldPosition = sourcePosition.lerp(destinationPosition, eased);
    worldPosition.y += Math.sin(eased * Math.PI) * 0.11;
    if (object.parent) {
      object.parent.worldToLocal(worldPosition);
    }
    object.position.copy(worldPosition);
  }

  private applySemanticMotion(cue: TwinCue, progress: number): void {
    const object = this.entities.get(cue.target);
    const baseline = object ? this.baselines.get(object) : undefined;
    if (!object || !baseline) return;
    const clip = cue.parameters.clip;
    if (clip === "mix_cycle") {
      const offset = mixerOffset(progress);
      object.position.copy(baseline.position);
      // A 2 mm-diameter clockwise orbital translation with no plate yaw.
      object.position.x += offset.x;
      object.position.y += offset.y;
      object.position.z += offset.z;
      object.quaternion.copy(baseline.quaternion);
      return;
    }
    if (clip === "characterize_cycle") {
      // Carry the illumination lid from its caddy to the reader and back.
      // These values are in the GLB's Y-up frame (the source scene is Z-up).
      const offset = readerLidOffset(progress);
      object.position.copy(baseline.position);
      object.position.x += offset.x;
      object.position.y += offset.y;
      object.position.z += offset.z;
      object.quaternion.copy(baseline.quaternion);
    }
  }

  private anchorWorldPosition(id: string): Vector3 | undefined {
    const object = this.anchors.get(id);
    if (object) return object.getWorldPosition(new Vector3());
    const anchor = this.anchorDefinitions.get(id);
    if (!anchor || !this.definition) return undefined;
    return this.definitionPosition(anchor.position);
  }

  private definitionPosition(position: [number, number, number]): Vector3 {
    const axis = this.definition?.coordinateFrame.upAxis ?? "Z";
    if (axis === "Z") return new Vector3(position[0], position[2], -position[1]);
    if (axis === "X") return new Vector3(position[1], position[0], position[2]);
    return new Vector3(position[0], position[1], position[2]);
  }

  private frameModel(): void {
    if (!this.model) return;
    const focus = this.entities.get("cell") ?? this.model;
    const bounds = new Box3().setFromObject(focus);
    if (bounds.isEmpty()) return;
    const size = bounds.getSize(new Vector3());
    const center = bounds.getCenter(new Vector3());
    const radius = Math.max(size.x, size.y, size.z, 0.5);
    this.controls.target.copy(center).add(new Vector3(0, size.y * 0.05, 0));
    this.camera.position
      .copy(center)
      .add(new Vector3(-0.88, 0.52, 1.12).normalize().multiplyScalar(radius * 1.78));
    this.camera.near = Math.max(radius / 500, 0.01);
    this.camera.far = radius * 30;
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  private resize(): void {
    const width = Math.max(this.container.clientWidth, 1);
    const height = Math.max(this.container.clientHeight, 1);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
  }
}
