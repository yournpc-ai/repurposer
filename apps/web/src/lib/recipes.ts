/**
 * 配方卡 (RecipeCard, RECIPES §7) — the home capability cards: a promise and
 * a pinned task book (explicit slots + dub_languages prior) so the promise is
 * delivered deterministically (never re-inferred by the LLM).
 *
 * Phase 1: hardcoded frontend data, NO table (prohibition). Copy lives in
 * i18n under `recipes.<id>.*` (title / promise / promptTemplate); this file
 * holds structural data only. `status: "reserved"` cards are data seats —
 * never rendered (点亮纪律: a card ships only when its capability is real).
 * Fields are added when a live card actually consumes them — no speculative
 * contract.
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
    preview: { posterUrl: "/recipes/image-video-poster.jpg" },
    status: "reserved",
  },
  {
    // R3 seat: landscape two-person interview -> vertical speaker reframe.
    id: "reframe",
    slotsPrior: [CLIPS_SLOT],
    preview: { posterUrl: "/recipes/reframe-poster.jpg" },
    status: "reserved",
  },
  {
    // R4 seat: style showcase (content TBD, RECIPES §4.4).
    id: "style",
    slotsPrior: [CLIPS_SLOT],
    preview: { posterUrl: "/recipes/style-poster.jpg" },
    status: "reserved",
  },
]

/** Cards eligible for rendering (点亮纪律 — reserved seats stay hidden). */
export const liveRecipeCards = RECIPE_CARDS.filter((c) => c.status === "live")
