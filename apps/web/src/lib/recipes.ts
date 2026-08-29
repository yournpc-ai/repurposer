/**
 * 配方卡 (RecipeCard, RECIPES §7.1) — the home capability gallery, fed by
 * the server-side recipe registry. **配方 = 数据** (2026-08-06): the server
 * holds one data package per recipe — base structure / flow / example_assets
 * / example_outputs ride the public endpoint (the preset substance never
 * leaves the server); translatable text stays in i18n (`recipes.<id>.*`
 * plus the shared `recipes.flow.*` / `recipes.tags.*` / `recipes.materials.*`
 * namespaces). Adding a recipe = one server registry entry + i18n keys —
 * zero code paths in the consumer.
 *
 * Recipe-gallery v2 (ADR-048, 2026-08-23): the card face NO LONGER carries
 * real media. The teaser / preview pointer, the masonry span, and every
 * featured-card concept are retired — the gallery is a uniform 4-column
 * grid of process-schematic covers (REST = static SVG; HOVER = the same
 * schematic plays its process animation). Each card's cover is looked up
 * by `card.id` from `components/recipes/covers/`, not from data.
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
  /** RECIPES §10: ``"reserved"`` cards occupy a grid seat with a Soon
   * pill; the click path is gated on ``"live"``. */
  status: "live" | "reserved"
  input_slots: RecipeInputSlot[]
  aspect: string
  /** Shared `recipes.tags.*` i18n keys. */
  tags: string[]
  /** Static recipe flow (ADR-035): shared `recipes.flow.*` i18n keys. */
  flow: { key: string; detail_key?: string | null; fanout?: number | null }[]
  example_assets: { kind: string; url: string; label_key?: string | null }[]
  example_outputs: {
    /** MediaKind of the baked artifact (产物展示统一, 2026-08-27):
     * "video" | "image" | "audio" render as media; "document" is a JSON
     * payload the overlay fetches and renders by `doc_format`. */
    kind: string
    url: string
    poster_url?: string | null
    label_key?: string | null
    /** kind="document" only: which writer payload shape the JSON holds. */
    doc_format?: "post" | "carousel" | null
    /** Declared frame for media kinds (falls back to the card aspect). */
    aspect?: string | null
  }[]
}

/** Does a staged file cover a required input slot? The launch gate reads
 * this (a recipe's required blank must be filled before send — same posture
 * as the composer's prompt-required toast). A wide slot (``any_of``) passes
 * when the file covers ANY ONE accepted kind (任一覆盖即过). Mirrors
 * inferAssetType's MIME families; slides travel as deck files (pdf/ppt). */
export function slotCoversFile(slot: RecipeInputSlot, file: File): boolean {
  const accepted = slot.type ? [slot.type] : (slot.any_of ?? [])
  return accepted.some((type) => fileCoversSlotType(type, file))
}

function fileCoversSlotType(slotType: string, file: File): boolean {
  switch (slotType) {
    case "video":
      return file.type.startsWith("video/")
    case "audio":
      return file.type.startsWith("audio/")
    case "images":
      // Decks convert to page images in asset processing (the image-video
      // card folds the 课件 scenario in), so a deck file covers the visual
      // slot too — the card's inputHint ("photos or a slide deck") is the
      // truth, and the server-side media gate already accepts deck-only.
      return file.type.startsWith("image/") || fileCoversSlotType("slides", file)
    case "slides":
      return (
        file.type === "application/pdf" ||
        /\.(pdf|pptx?|key)$/i.test(file.name)
      )
    default:
      // transcript — the document/text fallback, same as inferAssetType.
      return !/^(video|audio|image)\//.test(file.type)
  }
}

/** The gallery's card list: the public registry alone (recipe-gallery v2 — no
 * preview media; the cover is keyed off `card.id`). Card order = registry
 * insertion order (RECIPES §4: row 1 video sources, row 2 text/image sources). */
export async function fetchRecipeCards(): Promise<RecipePublic[]> {
  const res = await apiFetch("/api/v1/recipes")
  if (!res.ok) return []
  return (await res.json()) as RecipePublic[]
}
