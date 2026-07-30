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

export interface RecipeCard {
  /** i18n key root: recipes.<id>.title / .promise / .promptTemplate */
  id: string
  /** explicit-pinned task slots — they survive re-inference (pin-merge). */
  slotsPrior: IntentSlot[]
  /** Cross-output task-book params pinned alongside the slots. */
  params?: { dubLanguages?: string[] }
  /** Public-readable static assets (apps/web/public/recipes/) — the landing
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

export const RECIPE_CARDS: RecipeCard[] = [
  {
    // R1: one talk -> clips + your cloned voice speaking DE/FR/ES (fork
    // semantics — the originals and all language versions coexist).
    id: "dub",
    slotsPrior: [CLIPS_SLOT],
    params: { dubLanguages: ["de", "fr", "es"] },
    preview: {
      posterUrl: "/recipes/dub-poster.jpg",
      videoUrl: "/recipes/dub-preview.mp4",
    },
    status: "live",
  },
  {
    // R2 seat: transcript + photos -> stills + stacking captions + voice.
    id: "image-video",
    slotsPrior: [CLIPS_SLOT],
    preview: {
      posterUrl: "/recipes/image-video-poster.jpg",
      videoUrl: "/recipes/image-video-preview.mp4",
    },
    status: "reserved",
  },
  {
    // R3 seat: landscape two-person interview -> vertical speaker reframe.
    id: "reframe",
    slotsPrior: [CLIPS_SLOT],
    preview: {
      posterUrl: "/recipes/reframe-poster.jpg",
      videoUrl: "/recipes/reframe-preview.mp4",
    },
    status: "reserved",
  },
  {
    // R4 seat: style showcase (content TBD, RECIPES §4.4).
    id: "style",
    slotsPrior: [CLIPS_SLOT],
    preview: {
      posterUrl: "/recipes/style-poster.jpg",
      videoUrl: "/recipes/style-preview.mp4",
    },
    status: "reserved",
  },
]
