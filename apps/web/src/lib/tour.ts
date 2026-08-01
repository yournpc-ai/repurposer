/**
 * 版本即内容 (tour version = a pure function of content): a tour's seen flag
 * stores a hash of its DEFINITION — step config + source-language copy.
 * Any content change, steps or copy, yields a new hash and replays the tour
 * exactly once per user. No manual version constants, no human "is it worth
 * re-showing" judgment — the contract is enforced by code.
 *
 * The copy is hashed from the EN locale (the source of truth — every copy
 * edit touches it, zh mirrors it), so a language switch never replays the
 * tour: the hash is language-independent by construction.
 */

import en from "@/lib/i18n/locales/en"

/** One tour step as CONFIG — copy referenced by i18n key, never pre-rendered,
 * so the definition (and its hash) is independent of the active language. */
export interface TourStepDef {
  target: string
  titleKey: string
  descKey: string
  side?: "top" | "bottom" | "left" | "right"
  align?: "start" | "center" | "end"
}

/** djb2 — a tiny deterministic string hash (tour versioning, not security). */
export function tourVersionOf(steps: TourStepDef[], copy: unknown): string {
  const serialized = JSON.stringify({ steps, copy })
  let hash = 5381
  for (let i = 0; i < serialized.length; i++) {
    hash = ((hash << 5) + hash + serialized.charCodeAt(i)) >>> 0
  }
  return hash.toString(36)
}

export const tourCopy = en.tour
