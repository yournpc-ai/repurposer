/**
 * 配方卡 (RecipeCard, RECIPES §7) — the home capability gallery: vertical
 * auto-playing teasers + a pinned task book (explicit slots + dub_languages
 * prior) so a remix is delivered deterministically (never re-inferred).
 *
 * Phase 1: hardcoded frontend data, NO table (prohibition). Copy lives in
 * i18n under `recipes.<id>.*` (title / promise / promptTemplate); this file
 * holds structural data only. All four cards RENDER (2026-07-31 product
 * decision — presence over gating); `status: "reserved"` cards show a Soon
 * pill instead of Remix — a promise is never clickable before its capability
 * is real (点亮纪律's remaining line). Fields are added when a live card
 * actually consumes them — no speculative contract.
 */

import type { IntentSlot } from "@/lib/types"

/** Remix interaction is parked (2026-07-31): a recipe delivering its promise
 * needs more than a prefilled prompt — the invisible pin-merge prior bit us
 * in practice (a picked card silently steered a later plain composer run).
 * All cards render with the Soon pill until the flow is redesigned. The
 * machinery (slotsPrior / params / promptTemplate, the composer's prior
 * payload) stays in place, unreachable, for the next iteration. */
export const RECIPE_REMIX_ENABLED = false

export interface RecipeCard {
  /** i18n key root: recipes.<id>.title / .promise / .promptTemplate */
  id: string
  /** explicit-pinned task slots — they survive re-inference (pin-merge). */
  slotsPrior: IntentSlot[]
  /** Cross-output task-book params pinned alongside the slots. */
  params?: { dubLanguages?: string[] }
  /** Public-readable assets on the TOS demo tree (demo/outputs/) — the landing
   * audience is anonymous, so signed/login-gated asset endpoints are banned. */
  preview: { posterUrl: string; videoUrl?: string }
  status: "live" | "reserved"
}

const CLIPS_SLOT: IntentSlot = {
  type: "clips",
  count: null,
  focus: null,
  language: null,
  tone_override: null,
  explicit: true,
}

const RECIPE_MEDIA_BASE = "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs"

export const RECIPE_CARDS: RecipeCard[] = [
  {
    // R1: one talk -> clips + your cloned voice speaking DE/FR/ES (fork
    // semantics — the originals and all language versions coexist).
    id: "dub",
    slotsPrior: [CLIPS_SLOT],
    params: { dubLanguages: ["de", "fr", "es"] },
    preview: {
      posterUrl: `${RECIPE_MEDIA_BASE}/dub-poster.jpg`,
      videoUrl: `${RECIPE_MEDIA_BASE}/dub-preview.mp4`,
    },
    status: "live",
  },
  {
    // R2 seat: transcript + photos -> stills + stacking captions + voice.
    id: "image-video",
    slotsPrior: [CLIPS_SLOT],
    preview: {
      posterUrl: `${RECIPE_MEDIA_BASE}/image-video-poster.jpg`,
      videoUrl: `${RECIPE_MEDIA_BASE}/image-video-preview.mp4`,
    },
    status: "reserved",
  },
  {
    // R3 seat: landscape two-person interview -> vertical speaker reframe.
    id: "reframe",
    slotsPrior: [CLIPS_SLOT],
    preview: {
      posterUrl: `${RECIPE_MEDIA_BASE}/reframe-poster.jpg`,
      videoUrl: `${RECIPE_MEDIA_BASE}/reframe-preview.mp4`,
    },
    status: "reserved",
  },
  {
    // R4 seat: style showcase (content TBD, RECIPES §4.4).
    id: "style",
    slotsPrior: [CLIPS_SLOT],
    preview: {
      posterUrl: `${RECIPE_MEDIA_BASE}/style-poster.jpg`,
      videoUrl: `${RECIPE_MEDIA_BASE}/style-preview.mp4`,
    },
    status: "reserved",
  },
  {
    // R5 seat: nothing but a talk — every scene AI-generated (MiniMax video),
    // the zero-asset end of the source-material spectrum.
    id: "ai-visuals",
    slotsPrior: [CLIPS_SLOT],
    preview: {
      posterUrl: `${RECIPE_MEDIA_BASE}/ai-visuals-poster.jpg`,
      // No preview video until the capability itself exists — poster only.
    },
    status: "reserved",
  },
]
