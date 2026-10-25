/**
 * Home 两级 tab 货架 (D5, flora-parity-ui 批) — the data-driven registry
 * behind `RecipeTabs` + `RecipeShelf`: 一级 pill 轨 (families) × 下划线子
 * tab (subs) × 横滑货架 (shelves).
 *
 * 组织轴 = 用户任务 (2026-10 investor-demo ruling), never 产物介质: the
 * tabs answer "what can I get done", not "what file type comes out".
 * Three task families + a catch-all:
 *
 *   ads (Ads & UGC — first seat = the home default)   文字短片 / 产品演示
 *   talks (Talks & interviews)   一段讲话 → 字幕 / 配音 / 竖屏剪辑 / 重构
 *   posts (Social media)         LinkedIn 核心: 贴文 / 轮播幻灯 (金句卡演示期隐藏)
 *   templates (More)             catch-all 座 — 未归类服务端新卡的兜底行,
 *                                正常为空不渲染
 *
 * 上架纪律: `resolveFamilies` drops empty shelves → empty subs → empty
 * families, so a family without demos never renders, not even a placeholder
 * seat (连摆位都不摆). A demo video SHOULD be a real render of the shelf's
 * capability; three reused product-demo entries temporarily ride REUSED
 * existing renders as pure layout placeholders (each entry's comment names
 * its source) — a placeholder proves the shelf's layout, never the
 * capability, and swapping in a real sample is a data-only edit.
 * Placeholders are recorded in data comments and the batch brief, never
 * bannered in the UI.
 *
 * 卡片点击唯一归宿 = composer 预填 (D5 禁则 8 — 永不是模板编辑器): every
 * resolved shelf item carries its `prefillKey` — a recipe card resolves to
 * `recipes.<id>.promptTemplate` (配方 = 提示词, ADR-040), a demo card to
 * `recipes.shelf.demos.<id>.prompt`.
 */

import type { LucideIcon } from "lucide-react"
import { LayoutGrid } from "lucide-react"

import type { RecipePublic } from "@/lib/recipes"

/** One demo video card on a MG family shelf (autoplay muted loop + hover
 * sound veil; the render itself is the evidence). */
export interface ShelfDemo {
  /** Demo id — prefill copy lives at `recipes.shelf.demos.<id>.prompt`. The
   * id is the card's stable business key (React key + sound-owner id): it
   * never derives from the url, so a video swap touches nothing else. */
  id: string
  /** Demo video URL. The standard is a real render of the shelf's
   * capability; placeholder entries (a reused existing render, its source
   * named in the entry's comment) exist only to ship a shelf's layout
   * before its own samples land — replacing one is a data-only edit. */
  url: string
  /** Card frame: "wide" = 16:9, "vertical" = 3/4 (prototype .vcard / .v).
   * Always the file's real aspect — never stretch a placeholder. */
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
  /** Keep the tab visible as a registry seat while disabling selection. */
  disabled?: boolean
  subs: RecipeSubTabDef[]
}

/** The recipe card's shelf family — D5's "recipe 注册表加 family 字段",
 * web-side projection: the server registry (apps/api) stays family-
 * agnostic, so the assignment lives here. A card registered server-side
 * WITHOUT an entry here files under "templates" (the catch-all row — MG
 * 批 D3「进现有配方行」). Hidden cards keep their honest mapping — the
 * seat reappears the moment the hide lifts. */
export const RECIPE_CARD_FAMILY: Record<string, string> = {
  // Talks & interviews — one talk recording in, named cuts out.
  "multilingual-subs": "talks",
  "voice-dub": "talks",
  "highlight-clips": "talks",
  reframe: "talks",
  // Social media — the LinkedIn-core written/visual outputs.
  "social-post": "posts",
  carousel: "posts",
  "quote-cards": "posts", // demo-hidden (DEMO_HIDDEN_CARDS)
  "image-video": "templates", // demo-hidden (DEMO_HIDDEN_CARDS)
}

/** 演示期下架清单 (2026-10 investor-demo ruling) — HIDE, never delete: the
 * cards stay in the server registry, the capabilities stay live (the agent
 * still answers a spoken request), the i18n copy stays. The shelf simply
 * doesn't list them. Remove an id here and the card reappears in its
 * mapped family.
 *
 *   quote-cards — 内容偏薄 (single composite image), overlaps the posts
 *                 story the carousel already tells better
 *   image-video — 照片成片, consumer-flavored, off the knowledge-expert
 *                 positioning, collides with the MG flagship story */
export const DEMO_HIDDEN_CARDS: ReadonlySet<string> = new Set([
  "quote-cards",
  "image-video",
])

export function recipeCardFamily(card: RecipePublic): string {
  return RECIPE_CARD_FAMILY[card.id] ?? "templates"
}

/** The shelf registry — task families in display order (the first family
 * is the home's default tab). Ads' RESERVED seats (brand / ugc / product)
 * declare EMPTY demo lists until their renders land — invisible until then,
 * zero component changes to turn them on. The product-demo / text-short subs
 * are LIVE shelves. Any remaining placeholder entries are marked
 * individually below; the text-short entries and the product-demo shelf's
 * first entry are real film-chain renders. */
export const RECIPE_FAMILIES: RecipeFamilyDef[] = [
  {
    // Ads — Film-led text shorts and product demos. First seat = the home
    // default tab.
    id: "ads",
    subs: [
      {
        // 产品演示 — the first entry is a real film-chain render. The
        // remaining reused entries stay explicitly marked as placeholders.
        id: "product-demo",
        shelves: [
          {
            id: "product-demo",
            kind: "demos",
            demos: [
              {
                // ZYMIX 产品演示 + 独立屏上说明字幕 — real render from the
                // current film chain (project 8577f1ff, output 8beb17c9).
                id: "product-demo-zymix",
                url: "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/product-demo-zymix-one-way-in-41a917c7.mp4",
                orientation: "wide",
              },
              {
                // 功能亮点介绍 — placeholder: reuses the snappify "Code"
                // vertical launch film.
                id: "product-demo-highlights",
                url: "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/mg-launch-film-snappify-code-adc0737d.mp4",
                orientation: "vertical",
              },
              {
                // 视频配文字说明 — placeholder: reuses the snappify "Frame"
                // vertical launch film.
                id: "product-demo-captioned",
                url: "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/mg-launch-film-snappify-frame-0ef913dd.mp4",
                orientation: "vertical",
              },
              {
                // 操作流程演示 — placeholder: reuses the zymix.ai wide
                // launch film.
                id: "product-demo-walkthrough",
                url: "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/mg-launch-film-zymix-9890ad58.mp4",
                orientation: "wide",
              },
            ],
          },
        ],
      },
      {
        // 文字短片 — real text-source Film render (project 9345ddc2,
        // output a9701fe0), content-addressed into the demo/ tree.
        id: "text-short",
        shelves: [
          {
            id: "text-short",
            kind: "demos",
            demos: [
              {
                id: "text-short-gentle-close",
                url: "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/text-short-gentle-close-6c42705a.mp4",
                orientation: "wide",
              },
              {
                // Genesis 逐字英文文字短片 — real text-source Film render
                // (project f52c489c, output 50a6b40d), 68.1s / 16:9.
                id: "text-short-genesis",
                url: "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/text-short-genesis-25aa61fa.mp4",
                orientation: "wide",
              },
            ],
          },
        ],
      },
      { id: "brand", shelves: [{ id: "brand", kind: "demos", demos: [] }] },
      { id: "ugc", shelves: [{ id: "ugc", kind: "demos", demos: [] }] },
      { id: "product", shelves: [{ id: "product", kind: "demos", demos: [] }] },
    ],
  },
  {
    id: "talks",
    disabled: true,
    subs: [{ id: "all", shelves: [{ id: "talks", kind: "recipes" }] }],
  },
  {
    id: "posts",
    disabled: true,
    subs: [{ id: "all", shelves: [{ id: "posts", kind: "recipes" }] }],
  },
  {
    // Catch-all seat: a server-side card without a family mapping files
    // here. Empty in the current assignment → never renders.
    id: "templates",
    icon: LayoutGrid,
    subs: [{ id: "all", shelves: [{ id: "featured", kind: "recipes" }] }],
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
  disabled?: boolean
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
    // 演示期下架 (DEMO_HIDDEN_CARDS): hide ≠ delete — the card's capability
    // and copy stay live, the shelf just doesn't list it.
    if (DEMO_HIDDEN_CARDS.has(card.id)) continue
    const familyId = recipeCardFamily(card)
    const list = cardsByFamily.get(familyId)
    if (list) list.push(card)
    else cardsByFamily.set(familyId, [card])
  }
  return families
    .map((family) => ({
      id: family.id,
      icon: family.icon,
      disabled: family.disabled,
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
