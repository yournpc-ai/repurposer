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
  it("注册表八卡全部归 templates 族", () => {
    for (const id of ALL_REGISTRY_IDS) {
      expect(recipeCardFamily(card(id))).toBe("templates")
    }
  })

  it("未登记的新卡归 templates(进现有配方行 — MG 批 D3 口径)", () => {
    expect(recipeCardFamily(card("launch-film"))).toBe("templates")
  })
})

describe("resolveFamilies — 族分组", () => {
  it("模板族首货架 = recipes 货架,卡按注册表序入驻(live + reserved 都保留座位)", () => {
    const cards = ALL_REGISTRY_IDS.map((id, i) =>
      card(id, i === ALL_REGISTRY_IDS.length - 1 ? "reserved" : "live"),
    )
    const families = resolveRecipeFamilies(cards)
    const templates = families.find((f) => f.id === "templates")
    expect(templates).toBeDefined()
    const firstShelf = templates!.subs[0]?.shelves[0]
    expect(firstShelf?.id).toBe("featured")
    expect(firstShelf?.items.map((it) => it.kind)).toEqual(
      cards.map(() => "recipe"),
    )
    expect(
      firstShelf?.items.map((it) => (it.kind === "recipe" ? it.card.id : "")),
    ).toEqual(ALL_REGISTRY_IDS)
  })

  it("卡只落在自己族的 recipes 货架——别族 recipes 货架不串货", () => {
    const families: RecipeFamilyDef[] = [
      { id: "templates", subs: [{ id: "all", shelves: [{ id: "featured", kind: "recipes" }] }] },
      { id: "explainer", subs: [{ id: "anim", shelves: [{ id: "anim", kind: "recipes" }] }] },
    ]
    const resolved = resolveFamilies(families, [card("voice-dub")])
    expect(resolved.map((f) => f.id)).toEqual(["templates"])
  })
})

describe("resolveFamilies — 空族不渲染(连摆位都不摆)", () => {
  it("未供货 MG 族整族不渲染;供货族上架(D3 首片 = ads/saas)", () => {
    const families = resolveRecipeFamilies(ALL_REGISTRY_IDS.map((id) => card(id)))
    expect(families.map((f) => f.id)).toEqual(["templates", "ads"])
    const ads = families.find((f) => f.id === "ads")
    // The empty siblings (brand/product) cascade away; only the supplied
    // sub keeps its seat.
    expect(ads?.subs.map((s) => s.id)).toEqual(["saas"])
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
    const item = families[0].subs[0].shelves[0].items[0]
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

  it("模板族首货架复用 RecipeCard(kind = recipes)", () => {
    const templates = RECIPE_FAMILIES.find((f) => f.id === "templates")
    expect(templates?.subs[0]?.shelves[0]?.kind).toBe("recipes")
  })

  it("MG 族货架 = demo 视频族(kind = demos);上架的每一片都是 demo/ 树真片(无真 demo 不成卡)", () => {
    for (const family of RECIPE_FAMILIES.filter((f) => f.id !== "templates")) {
      for (const sub of family.subs) {
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
    }
  })
})
