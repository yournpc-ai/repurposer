/**
 * 货架纯逻辑套件 (D5 验证仪式链): 族分组 / 空族不渲染 / 预填载荷。
 * 纯函数层 (recipeShelf.ts) — 无 DOM、无 i18n、无网络。
 */

import { describe, expect, it } from "vitest"

import type { RecipePublic } from "@/lib/recipes"
import {
  RECIPE_CARD_FAMILY,
  RECIPE_FAMILIES,
  recipeCardFamily,
  resolveFamilies,
  resolveRecipeFamilies,
  type RecipeFamilyDef,
} from "./recipeFamilies"

function card(id: string, status: "live" | "reserved" = "live"): RecipePublic {
  return {
    id,
    status,
    input_slots: [],
    aspect: "9:16",
    tags: [],
    flow: [],
    example_assets: [],
    example_outputs: [],
  }
}

const ALL_REGISTRY_IDS = Object.keys(RECIPE_CARD_FAMILY)

describe("recipeCardFamily — family 字段投影", () => {
  it("八卡按任务族归位(隐藏卡映射保留,下架 ≠ 删除)", () => {
    expect(RECIPE_CARD_FAMILY).toMatchObject({
      "multilingual-subs": "talks",
      "voice-dub": "talks",
      "highlight-clips": "talks",
      reframe: "talks",
      "social-post": "posts",
      carousel: "posts",
      "quote-cards": "posts",
      "image-video": "templates",
    })
  })

  it("未登记的新卡归 templates(进现有配方行 — MG 批 D3 口径)", () => {
    expect(recipeCardFamily(card("launch-film"))).toBe("templates")
  })
})

describe("resolveFamilies — 族分组", () => {
  it("任务族分组: Ads 旗舰居首(默认 tab),talks 四卡 / posts 两卡按注册表序入驻(reserved 保留座位)", () => {
    const cards = ALL_REGISTRY_IDS.map((id) =>
      card(id, id === "reframe" ? "reserved" : "live"),
    )
    const families = resolveRecipeFamilies(cards)
    expect(families.map((f) => f.id)).toEqual(["ads", "talks", "posts"])
    const talksShelf = families[1].subs[0]?.shelves[0]
    expect(talksShelf?.id).toBe("talks")
    expect(
      talksShelf?.items.map((it) => (it.kind === "recipe" ? it.card.id : "")),
    ).toEqual(["multilingual-subs", "voice-dub", "highlight-clips", "reframe"])
    const postsShelf = families[2].subs[0]?.shelves[0]
    expect(
      postsShelf?.items.map((it) => (it.kind === "recipe" ? it.card.id : "")),
    ).toEqual(["social-post", "carousel"])
  })

  it("演示期下架清单: quote-cards / image-video 不上任何货架", () => {
    const families = resolveRecipeFamilies(
      ALL_REGISTRY_IDS.map((id) => card(id)),
    )
    const onShelf = families.flatMap((f) =>
      f.subs.flatMap((s) =>
        s.shelves.flatMap((sh) =>
          sh.items.map((it) =>
            it.kind === "recipe" ? it.card.id : it.demo.id,
          ),
        ),
      ),
    )
    expect(onShelf).not.toContain("quote-cards")
    expect(onShelf).not.toContain("image-video")
  })

  it("卡只落在自己族的 recipes 货架——别族 recipes 货架不串货", () => {
    const families: RecipeFamilyDef[] = [
      { id: "templates", subs: [{ id: "all", shelves: [{ id: "featured", kind: "recipes" }] }] },
      { id: "explainer", subs: [{ id: "anim", shelves: [{ id: "anim", kind: "recipes" }] }] },
    ]
    // An unregistered card falls back to templates — it must NOT cross-file
    // into another family's recipes shelf.
    const resolved = resolveFamilies(families, [card("some-unregistered-card")])
    expect(resolved.map((f) => f.id)).toEqual(["templates"])
  })
})

describe("resolveFamilies — 空族不渲染(连摆位都不摆)", () => {
  it("Ads 族: saas/brand 供货点亮,product 空位级联丢弃——补渲即亮零改动", () => {
    const families = resolveRecipeFamilies(ALL_REGISTRY_IDS.map((id) => card(id)))
    const ads = families.find((f) => f.id === "ads")
    // saas (linear) and brand (zymix) carry real demos; the empty product
    // sibling cascades away until its render lands.
    expect(ads?.subs.map((s) => s.id)).toEqual(["saas", "brand"])
  })

  it("空货架 → 空子 tab → 空族 级联丢弃", () => {
    const families: RecipeFamilyDef[] = [
      {
        id: "explainer",
        subs: [
          // 一空一有: 空货架丢弃,子 tab 存活
          {
            id: "anim",
            shelves: [
              { id: "empty", kind: "demos", demos: [] },
              {
                id: "real",
                kind: "demos",
                demos: [{ id: "d1", url: "https://cdn.example.com/d1.mp4", orientation: "wide" }],
              },
            ],
          },
          // 全空: 子 tab 整丢
          { id: "motion", shelves: [{ id: "motion", kind: "demos", demos: [] }] },
        ],
      },
      // 无子 tab 存活: 族整丢
      { id: "ads", subs: [{ id: "brand", shelves: [{ id: "brand", kind: "demos", demos: [] }] }] },
    ]
    const resolved = resolveFamilies(families, [])
    expect(resolved.map((f) => f.id)).toEqual(["explainer"])
    expect(resolved[0].subs.map((s) => s.id)).toEqual(["anim"])
    expect(resolved[0].subs[0].shelves.map((s) => s.id)).toEqual(["real"])
  })

  it("零卡 → 只剩供货 demo 的族(货架与配方卡解耦)", () => {
    expect(resolveRecipeFamilies([]).map((f) => f.id)).toEqual(["ads"])
  })
})

describe("resolveFamilies — 预填载荷(卡片点击唯一归宿 = composer 预填)", () => {
  it("recipe 卡 → recipes.<id>.promptTemplate(配方 = 提示词, ADR-040)", () => {
    const families = resolveRecipeFamilies([card("highlight-clips")])
    const talks = families.find((f) => f.id === "talks")
    const item = talks!.subs[0].shelves[0].items[0]
    expect(item).toMatchObject({
      kind: "recipe",
      prefillKey: "recipes.highlight-clips.promptTemplate",
    })
  })

  it("demo 卡 → recipes.shelf.demos.<id>.prompt", () => {
    const families: RecipeFamilyDef[] = [
      {
        id: "explainer",
        subs: [
          {
            id: "anim",
            shelves: [
              {
                id: "anim",
                kind: "demos",
                demos: [{ id: "launch-film", url: "https://cdn.example.com/lf.mp4", orientation: "wide" }],
              },
            ],
          },
        ],
      },
    ]
    const item = resolveFamilies(families, [])[0].subs[0].shelves[0].items[0]
    expect(item).toMatchObject({
      kind: "demo",
      prefillKey: "recipes.shelf.demos.launch-film.prompt",
    })
  })
})

describe("RECIPE_FAMILIES 注册表形态守卫", () => {
  it("族 / 子 tab / 货架 id 各自唯一", () => {
    const familyIds = RECIPE_FAMILIES.map((f) => f.id)
    expect(new Set(familyIds).size).toBe(familyIds.length)
    for (const family of RECIPE_FAMILIES) {
      const subIds = family.subs.map((s) => s.id)
      expect(new Set(subIds).size).toBe(subIds.length)
      for (const sub of family.subs) {
        const shelfIds = sub.shelves.map((s) => s.id)
        expect(new Set(shelfIds).size).toBe(shelfIds.length)
      }
    }
  })

  it("任务族货架 = RecipeCard(kind = recipes)", () => {
    for (const id of ["templates", "talks", "posts"]) {
      const family = RECIPE_FAMILIES.find((f) => f.id === id)
      for (const sub of family?.subs ?? []) {
        for (const shelf of sub.shelves) {
          expect(shelf.kind).toBe("recipes")
        }
      }
    }
  })

  it("Ads(MG)族货架 = demo 视频族(kind = demos);上架的每一片都是 demo/ 树真片(无真 demo 不成卡)", () => {
    const ads = RECIPE_FAMILIES.find((f) => f.id === "ads")
    expect(ads).toBeDefined()
    for (const sub of ads!.subs) {
      for (const shelf of sub.shelves) {
        expect(shelf.kind).toBe("demos")
        for (const demo of shelf.demos ?? []) {
          // A shipped seat is a REAL render, content-addressed into the
          // public demo/ tree — never a placeholder, never a stock URL.
          expect(demo.url).toMatch(
            /^https:\/\/repurposer\.tos-ap-southeast-1\.volces\.com\/demo\//,
          )
          expect(["wide", "vertical"]).toContain(demo.orientation)
        }
      }
    }
  })
})
