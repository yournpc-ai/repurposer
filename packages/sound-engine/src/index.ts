import { analyzeAcoustics, encodeWavPcm16, renderGraph } from "./dsp.js";
import { INTERNAL_SOUND_RECIPES } from "./recipes.js";
import {
  CHANNELS,
  SAMPLE_RATE,
  SOUND_ENGINE_NAME,
  SOUND_ENGINE_VERSION,
  type SoundRecipeCatalogEntry,
  type SoundSynthesisSpec,
  type SynthesisResult,
  type WavSynthesisResult,
} from "./types.js";

export * from "./types.js";

export const DEFAULT_SOUND_SEED = 1248;

export const SOUND_RECIPES: readonly SoundRecipeCatalogEntry[] = Object.values(
  INTERNAL_SOUND_RECIPES,
).map((entry) => entry.catalog);

export function getSoundRecipe(recipeId: string): SoundRecipeCatalogEntry | undefined {
  return INTERNAL_SOUND_RECIPES[recipeId]?.catalog;
}

export function normalizeSoundParams(
  recipeId: string,
  overrides: Record<string, number> = {},
): Record<string, number> {
  const recipe = INTERNAL_SOUND_RECIPES[recipeId];
  if (!recipe) {
    throw new Error(`Unknown sound recipe: ${recipeId}`);
  }
  const specs = recipe.catalog.params;
  for (const key of Object.keys(overrides)) {
    if (!(key in specs)) {
      throw new Error(`Unknown parameter "${key}" for recipe "${recipeId}"`);
    }
  }
  const normalized: Record<string, number> = {};
  for (const key of Object.keys(specs).sort()) {
    const def = specs[key];
    const raw = overrides[key] ?? def.default;
    if (typeof raw !== "number" || !Number.isFinite(raw)) {
      throw new Error(`Parameter "${key}" must be a finite number`);
    }
    const clamped = Math.max(def.min, Math.min(def.max, raw));
    normalized[key] = def.step >= 1 ? Math.round(clamped / def.step) * def.step : Math.round(clamped * 1000) / 1000;
  }
  return normalized;
}

export function normalizeSeed(seed?: number): number {
  const value = seed ?? DEFAULT_SOUND_SEED;
  if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) {
    throw new Error("Seed must be an integer between 0 and 4294967295");
  }
  return value;
}

export function buildSoundSpec(input: {
  recipeId: string;
  params?: Record<string, number>;
  seed?: number;
}): SoundSynthesisSpec {
  const recipe = INTERNAL_SOUND_RECIPES[input.recipeId];
  if (!recipe) {
    throw new Error(`Unknown sound recipe: ${input.recipeId}`);
  }
  return {
    engine: SOUND_ENGINE_NAME,
    engine_version: SOUND_ENGINE_VERSION,
    recipe_id: recipe.catalog.id,
    recipe_version: recipe.catalog.version,
    params: normalizeSoundParams(input.recipeId, input.params),
    seed: normalizeSeed(input.seed),
    sample_rate: SAMPLE_RATE,
    channels: CHANNELS,
  };
}

/**
 * Deterministic canonical JSON of synthesis identity only.
 * Discovery metadata (name, desc, domain, category, use_for, avoid) is excluded by design.
 */
export function canonicalSoundSpecJson(spec: SoundSynthesisSpec): string {
  const sortedParams: Record<string, number> = {};
  for (const key of Object.keys(spec.params).sort()) {
    sortedParams[key] = spec.params[key];
  }
  return JSON.stringify({
    channels: spec.channels,
    engine: spec.engine,
    engine_version: spec.engine_version,
    params: sortedParams,
    recipe_id: spec.recipe_id,
    recipe_version: spec.recipe_version,
    sample_rate: spec.sample_rate,
    seed: spec.seed,
  });
}

export function synthesizeSound(input: {
  recipeId: string;
  params?: Record<string, number>;
  seed?: number;
}): SynthesisResult {
  const spec = buildSoundSpec(input);
  const recipe = INTERNAL_SOUND_RECIPES[spec.recipe_id]!;
  const graph = recipe.buildGraph(spec.params);
  const { left, right } = renderGraph(graph, spec.seed);
  const acoustics = analyzeAcoustics(left, right);
  return {
    left,
    right,
    sampleRate: SAMPLE_RATE,
    channels: CHANNELS,
    spec,
    acoustics,
  };
}

export function synthesizeWav(input: {
  recipeId: string;
  params?: Record<string, number>;
  seed?: number;
}): WavSynthesisResult {
  const result = synthesizeSound(input);
  const wav = encodeWavPcm16(result.left, result.right);
  return { ...result, wav };
}

export { encodeWavPcm16 };
