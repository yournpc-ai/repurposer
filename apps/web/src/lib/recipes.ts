/**
 * 配方卡 (RecipeCard, RECIPES §7.1) — the home capability shelf, fed by the
 * server-side recipe registry. **配方 = 数据** (2026-08-06): the server
 * holds one data package per recipe — base structure / flow / example_assets
 * / example_outputs ride the public endpoint (the preset substance never
 * leaves the server); translatable text stays in i18n (`recipes.<id>.*`).
 * Adding a recipe = one server registry entry + i18n keys — zero code paths
 * in the consumer.
 *
 * Recipe-gallery v2 (ADR-048, 2026-08-23): the card face carries NO real
 * media — the cover is a process-schematic inline SVG looked up by `card.id`
 * from `components/recipes/covers/`, not from data (REST = static; HOVER =
 * the same schematic plays its process animation).
 *
 * Click contract (D5, flora-parity-ui 批): a card click's ONLY destination
 * is a composer prefill of `recipes.<id>.promptTemplate` (配方 = 提示词,
 * ADR-040) — never a template-editing surface. The `flow` / `tags` /
 * `example_*` fields remain the wire mirror of the server payload (NAMING
 * §1 — same shape as the backend `RecipePublic`).
 */

import { apiFetch } from "@/lib/api"

/** 输入槽位 (InputSlot, 全栈同名): a narrow slot carries ``type``; a wide
 * slot (宽槽, quote-cards P2, 2026-08-28) carries ``any_of`` — the launch
 * gate passes when staged files cover AT LEAST ONE accepted kind. */
export interface RecipeInputSlot {
  type?: string | null
  any_of?: string[] | null
  required: boolean
}

/** Public card shape served by `GET /api/v1/recipes` (same name, same shape
 * as the backend `RecipePublic`, NAMING §1). */
export interface RecipePublic {
  id: string
  /** RECIPES §10: ``"reserved"`` cards occupy a shelf seat with a Soon
   * pill; the click path is gated on ``"live"``. */
  status: "live" | "reserved"
  input_slots: RecipeInputSlot[]
  aspect: string
  /** Wire mirror — no current client consumer (the shelf face reads only
   * title / promise / inputScenario / promptTemplate). */
  tags: string[]
  /** Wire mirror (static recipe flow, ADR-035). */
  flow: { key: string; detail_key?: string | null; fanout?: number | null }[]
  /** Wire mirror (baked example pack). */
  example_assets: { kind: string; url: string; label_key?: string | null }[]
  example_outputs: {
    /** MediaKind of the baked artifact (产物展示统一, 2026-08-27):
     * "video" | "image" | "audio" render as media; "document" is a JSON
     * payload keyed by `doc_format`. */
    kind: string
    url: string
    poster_url?: string | null
    label_key?: string | null
    /** kind="document" only: which writer payload shape the JSON holds. */
    doc_format?: "post" | "carousel" | null
    /** Declared frame for media kinds (falls back to the card aspect). */
    aspect?: string | null
  }[]
  /** 估价贴 (BILLING §7): the card's credits quotation [low, high] on the
   * typical source — serialization-derived against the live ratio (a config
   * edit moves every sticker). null = unquoted chain. */
  estimate_credits?: [number, number] | null
  /** Usage-priced sticker variant (per-second cards, e.g. voice-dub): rate
   * per source-video second + the one-shot fee (voice clone, once per
   * voice) — the fixed total's honest form when cost scales with source
   * duration. Filled INSTEAD of estimate_credits. */
  estimate_rate?: { per_second: number; one_shot: number } | null
}

/** The shelf's card list: the public registry alone (recipe-gallery v2 — no
 * preview media on the card face; the cover is keyed off `card.id`). Card
 * order = registry insertion order (RECIPES §4: row 1 video sources, row 2
 * text/image sources). */
export async function fetchRecipeCards(): Promise<RecipePublic[]> {
  const res = await apiFetch("/api/v1/recipes")
  if (!res.ok) return []
  return (await res.json()) as RecipePublic[]
}
