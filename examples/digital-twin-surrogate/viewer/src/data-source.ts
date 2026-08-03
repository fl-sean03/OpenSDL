import { DEMO_DEFINITION, DEMO_PROJECTION, DEMO_SCENE_URL } from "./demo";
import type { LoadedExperience, TwinDefinition, TwinProjection } from "./types";
import { parseProjection, parseTwinDefinition } from "./validation";

const REQUEST_TIMEOUT_MS = 4_000;

export class DataSourceError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "DataSourceError";
  }
}

async function getJson(url: string): Promise<unknown> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new DataSourceError(`${url} returned HTTP ${response.status}`);
    }
    return await response.json();
  } finally {
    window.clearTimeout(timeout);
  }
}

function projectionForConfiguredScene(definition: TwinDefinition): TwinProjection {
  if (
    definition.revision === DEMO_DEFINITION.revision &&
    definition.scene.sha256 === DEMO_DEFINITION.scene.sha256
  ) {
    return DEMO_PROJECTION;
  }
  return {
    definition_revision: definition.revision,
    run_id: "",
    cues: [],
  };
}

export async function loadExperience(runId?: string): Promise<LoadedExperience> {
  let definition: TwinDefinition;
  try {
    definition = parseTwinDefinition(await getJson("/twin"));
  } catch (error) {
    return {
      definition: DEMO_DEFINITION,
      projection: DEMO_PROJECTION,
      sceneUrl: DEMO_SCENE_URL,
      source: "local-demo",
      sourceDetail: "INCLUDED DETERMINISTIC RUN",
      note: error instanceof Error ? error.message : "OpenSDL API is unavailable",
    };
  }

  if (!runId) {
    const projection = projectionForConfiguredScene(definition);
    const includedDemo = projection === DEMO_PROJECTION;
    return {
      definition,
      projection,
      sceneUrl: "/twin/scene.glb",
      source: includedDemo ? "local-demo" : "configured-scene",
      sourceDetail: includedDemo ? "INCLUDED DETERMINISTIC RUN" : "NO RUN SELECTED",
      note: "Add ?run=<run-id> to project a persisted OpenSDL run.",
    };
  }

  try {
    const projection = parseProjection(await getJson(`/twin/runs/${encodeURIComponent(runId)}`));
    if (projection.definition_revision !== definition.revision) {
      throw new DataSourceError(
        `run projection revision ${projection.definition_revision} does not match scene revision ${definition.revision}`,
      );
    }
    return {
      definition,
      projection,
      sceneUrl: "/twin/scene.glb",
      source: "live-run",
      sourceDetail: runId,
    };
  } catch (error) {
    throw new DataSourceError(`Could not load projected run ${runId}`, {
      cause: error,
    });
  }
}
