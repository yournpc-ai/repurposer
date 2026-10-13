/**
 * Home 两级 tab 货架 (D5, flora-parity-ui 批) — the data-driven registry
 * behind `RecipeTabs` + `RecipeShelf`: 一级 pill 轨 (families) × 下划线子
 * tab (subs) × 横滑货架 (shelves). Shape follows the prototype
 * (`scratch/skill-mg-ui-proposal.html` 屏①), trimmed to real skill
 * coverage (原型注⑤: 族名按真实 skill 覆盖裁剪——发言人/真人 UGC 是
 * avatar 栈不是 MG 引擎,不占座).
 *
 * 上架纪律 (无真 demo 不成卡): a demos shelf entry ships ONLY with a real
 * rendered demo video — the MG 批 (D3) owns those assets; this registry
 * declares the seats with EMPTY demo lists, and `resolveFamilies` drops
 * empty shelves → empty subs → empty families, so a family without real
 * demos never renders, not even a placeholder (连摆位都不摆). Until D3
 * lands demo URLs, only the templates family resolves.
 *
 * 卡片点击唯一归宿 = composer 预填 (D5 禁则 8 — 永不是模板编辑器): every
 * resolved shelf item carries its `prefillKey` — a recipe card resolves to
 * `recipes.<id>.promptTemplate` (配方 = 提示词, ADR-040), a demo card to
 * `recipes.shelf.demos.<id>.prompt`.
 */

import type { LucideIcon } from "lucide-react"
import { LayoutGrid } from "lucide-react"

import type { RecipePublic } from "@/lib/recipes"

/** One demo video card on a MG family shelf (loop/muted, loop 播放即证据). */
export interface ShelfDemo {
  /** Demo id — prefill copy lives at `recipes.shelf.demos.<id>.prompt`. */
  id: string
  /** Real rendered demo video URL. An entry ships ONLY with a real render;
   * a family whose demos are all missing never renders. */
  url: string
  /** Card frame: "wide" = 16:9, "vertical" = 3/4 (prototype .vcard / .v). */
  orientation: "wide" | "vertical"
}

export interface RecipeShelfDef {
  /** Shelf id — the title key is `recipes.shelf.titles.<id>`. */
  id: string
  /** "recipes" = the family's recipe cards (RecipeCard); "demos" = MG demo
   * video cards. */
  kind: "recipes" | "demos"
  demos?: ShelfDemo[]
}

export interface RecipeSubTabDef {
  /** Sub-tab id — the label key is `recipes.shelf.subs.<id>`. */
  id: string
  shelves: RecipeShelfDef[]
}

export interface RecipeFamilyDef {
  /** Family id — the label key is `recipes.shelf.families.<id>`. */
  id: string
  /** Optional leading glyph on the level-1 pill (prototype: the templates
   * tab carries the grid icon). */
  icon?: LucideIcon
  subs: RecipeSubTabDef[]
}

/** The recipe card's shelf family — D5's "recipe 注册表加 family 字段",
 * web-side projection: the server registry (apps/api) stays family-
 * agnostic, so the assignment lives here. A card registered server-side
 * WITHOUT an entry here files under "templates" (the catch-all row — MG
 * 批 D3「进现有配方行」). */
export const RECIPE_CARD_FAMILY: Record<string, string> = {
  "multilingual-subs": "templates",
  "voice-dub": "templates",
  "highlight-clips": "templates",
  reframe: "templates",
  "social-post": "templates",
  "quote-cards": "templates",
  carousel: "templates",
  "image-video": "templates",
}

export function recipeCardFamily(card: RecipePublic): string {
  return RECIPE_CARD_FAMILY[card.id] ?? "templates"
}

/** The shelf registry. MG families declare their subs/shelves with EMPTY
 * demo lists — D3 turns them on by filling URLs, zero component changes. */
export const RECIPE_FAMILIES: RecipeFamilyDef[] = [
  {
    id: "templates",
    icon: LayoutGrid,
    subs: [{ id: "all", shelves: [{ id: "featured", kind: "recipes" }] }],
  },
  {
    id: "explainer",
    subs: [
      { id: "animated", shelves: [{ id: "animated", kind: "demos", demos: [] }] },
      { id: "motion", shelves: [{ id: "motion", kind: "demos", demos: [] }] },
    ],
  },
  {
    id: "ads",
    subs: [
      { id: "brand", shelves: [{ id: "brand", kind: "demos", demos: [] }] },
      {
        id: "saas",
        shelves: [
          {
            id: "saas",
            kind: "demos",
            demos: [
              {
                // MG 批 D3 点亮: the launch_film pipeline's own render
                // (linear.app → capture → storyboard → film-spec render,
                // e2e run de3f5e89 — every on-screen word grounds to the
                // captured page). Content-addressed into the demo/ tree.
                id: "launch-film-linear",
                url: "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/mg-launch-film-linear-6bc23a6a.mp4",
                orientation: "wide",
              },
            ],
          },
        ],
      },
      { id: "product", shelves: [{ id: "product", kind: "demos", demos: [] }] },
    ],
  },
  {
    id: "social",
    subs: [
      { id: "linkedin", shelves: [{ id: "linkedin", kind: "demos", demos: [] }] },
    ],
  },
]

/** One card on a resolved shelf — the discriminated union the shelf
 * renders; `prefillKey` is the click's entire payload (composer 预填). */
export type ShelfItem =
  | { kind: "recipe"; card: RecipePublic; prefillKey: string }
  | { kind: "demo"; demo: ShelfDemo; prefillKey: string }

export interface ResolvedShelf {
  id: string
  items: ShelfItem[]
}

export interface ResolvedSub {
  id: string
  shelves: ResolvedShelf[]
}

export interface ResolvedFamily {
  id: string
  icon?: LucideIcon
  subs: ResolvedSub[]
}

/** Project the registry + the fetched recipe cards into renderable
 * families — the 上架纪律 lives here: empty shelf → dropped, empty sub →
 * dropped, empty family → dropped. Card order = the server registry's
 * insertion order (preserved by the encounter-order grouping). Reserved
 * cards keep their seat (RECIPES §10 — RecipeCard renders the Soon pill). */
export function resolveFamilies(
  families: RecipeFamilyDef[],
  cards: RecipePublic[],
): ResolvedFamily[] {
  const cardsByFamily = new Map<string, RecipePublic[]>()
  for (const card of cards) {
    const familyId = recipeCardFamily(card)
    const list = cardsByFamily.get(familyId)
    if (list) list.push(card)
    else cardsByFamily.set(familyId, [card])
  }
  return families
    .map((family) => ({
      id: family.id,
      icon: family.icon,
      subs: family.subs
        .map((sub) => ({
          id: sub.id,
          shelves: sub.shelves
            .map((shelf): ResolvedShelf => ({
              id: shelf.id,
              items:
                shelf.kind === "recipes"
                  ? (cardsByFamily.get(family.id) ?? []).map((card) => ({
                      kind: "recipe" as const,
                      card,
                      prefillKey: `recipes.${card.id}.promptTemplate`,
                    }))
                  : (shelf.demos ?? []).map((demo) => ({
                      kind: "demo" as const,
                      demo,
                      prefillKey: `recipes.shelf.demos.${demo.id}.prompt`,
                    })),
            }))
            .filter((shelf) => shelf.items.length > 0),
        }))
        .filter((sub) => sub.shelves.length > 0),
    }))
    .filter((family) => family.subs.length > 0)
}

export function resolveRecipeFamilies(cards: RecipePublic[]): ResolvedFamily[] {
  return resolveFamilies(RECIPE_FAMILIES, cards)
}
