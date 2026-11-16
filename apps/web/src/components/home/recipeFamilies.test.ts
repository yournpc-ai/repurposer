import { describe, expect, it } from "vitest"

import en from "@/lib/i18n/locales/en"
import zh from "@/lib/i18n/locales/zh"
import type { RecipePublic } from "@/lib/recipes"
import { BUILTIN_SKILL_VERSIONS, type SkillOption } from "@/lib/skills"
import {
  RECIPE_CARD_FAMILY,
  RECIPE_FAMILIES,
  recipeCardFamily,
  resolveFamilies,
  resolveRecipeFamilies,
  type RecipeFamilyDef,
  type ShelfDemo,
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

function demosIn(families: ReturnType<typeof resolveRecipeFamilies>): ShelfDemo[] {
  return families.flatMap((family) =>
    family.subs.flatMap((sub) =>
      sub.shelves.flatMap((shelf) =>
        shelf.items.flatMap((item) => (item.kind === "demo" ? [item.demo] : [])),
      ),
    ),
  )
}

describe("non-video Recipe registration", () => {
  it("keeps the existing family mappings and prompt ownership unchanged", () => {
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
    expect(recipeCardFamily(card("unregistered"))).toBe("templates")
  })

  it("generic Recipe shelves still resolve to their existing prompt payload", () => {
    const families: RecipeFamilyDef[] = [
      {
        id: "talks",
        subs: [{ id: "all", shelves: [{ id: "talks", kind: "recipes" }] }],
      },
    ]
    const item = resolveFamilies(families, [card("highlight-clips")])[0]
      ?.subs[0]?.shelves[0]?.items[0]
    expect(item).toMatchObject({
      kind: "recipe",
      prefillKey: "recipes.highlight-clips.promptTemplate",
    })
  })

  it("does not resurrect retired Home task groups from fetched Recipe cards", () => {
    const families = resolveRecipeFamilies(
      Object.keys(RECIPE_CARD_FAMILY).map((id) => card(id)),
    )
    expect(families.map((family) => family.id)).toEqual([
      "product-promo",
      "talking-head",
      "text-animation",
      "knowledge-explainer",
    ])
    expect(
      families.flatMap((family) =>
        family.subs.flatMap((sub) => sub.shelves.flatMap((shelf) => shelf.items)),
      ),
    ).toHaveLength(5)
  })
})

describe("four-product Home shelf", () => {
  it("shows four products and their eight application seats", () => {
    const families = resolveRecipeFamilies([])
    expect(
      families.map((family) => ({
        id: family.id,
        skillId: family.skillId,
        subs: family.subs.map((sub) => sub.id),
      })),
    ).toEqual([
      {
        id: "product-promo",
        skillId: "promo-video",
        subs: ["website-product", "course-service"],
      },
      {
        id: "talking-head",
        skillId: "talking-head-video",
        subs: ["opinion-talking-head", "course-lecture-teaser"],
      },
      {
        id: "text-animation",
        skillId: "text-animation",
        subs: ["opinion-text", "quote-announcement"],
      },
      {
        id: "knowledge-explainer",
        skillId: "knowledge-explainer",
        subs: ["concept-explainer", "research-report"],
      },
    ])
  })

  it("places exactly five real samples and preserves five honest empty states", () => {
    const families = resolveRecipeFamilies([])
    expect(demosIn(families).map((demo) => demo.id)).toEqual([
      "product-promo-agentveil-the-next-move",
      "product-promo-oxvalue-product-evidence",
      "product-promo-oxvalue-energy-arc",
      "text-short-clear-rhythm",
      "knowledge-explainer-clear-expression",
    ])
    const emptyShelves = families.flatMap((family) =>
      family.subs.flatMap((sub) =>
        sub.shelves.filter((shelf) => shelf.items.length === 0).map((shelf) => shelf.id),
      ),
    )
    expect(emptyShelves).toEqual([
      "course-service",
      "opinion-talking-head",
      "course-lecture-teaser",
      "quote-announcement",
      "research-report",
    ])
    expect(en.recipes.shelf.emptyDemo).toBe("No sample for this application yet.")
    expect(zh.recipes.shelf.emptyDemo).toBe("该应用暂无样片。")
  })

  it("does not mix old Film samples or retired video groups into the shelf", () => {
    const ids = demosIn(resolveRecipeFamilies([])).map((demo) => demo.id)
    expect(ids).not.toEqual(
      expect.arrayContaining([
        "product-demo-zymix",
        "product-demo-highlights",
        "product-demo-captioned",
        "product-demo-walkthrough",
        "text-short-gentle-close",
        "text-short-genesis",
      ]),
    )
    expect(RECIPE_FAMILIES.map((family) => family.id)).not.toEqual(
      expect.arrayContaining(["ads", "talks", "posts", "templates"]),
    )
  })

  it("collapses empty generic groups unless a video demo seat opts into visibility", () => {
    const families: RecipeFamilyDef[] = [
      {
        id: "generic",
        subs: [{ id: "empty", shelves: [{ id: "empty", kind: "demos", demos: [] }] }],
      },
      {
        id: "video",
        preserveEmptyDemoShelves: true,
        subs: [{ id: "empty", shelves: [{ id: "empty", kind: "demos", demos: [] }] }],
      },
    ]
    const resolved = resolveFamilies(families, [])
    expect(resolved.map((family) => family.id)).toEqual(["video"])
    expect(resolved[0]?.subs[0]?.shelves[0]?.items).toEqual([])
  })
})

describe("sample → exact Skill reference + prompt", () => {
  const liveSkills: SkillOption[] = Object.entries(BUILTIN_SKILL_VERSIONS).map(
    ([skill_id, version]) => ({
      reference: { kind: "builtin", skill_id, version },
      skill_id,
      name: skill_id,
      description: "",
      capabilities: ["declared"],
    }),
  )

  const installedPromo: SkillOption = {
    reference: { kind: "builtin", skill_id: "promo-video", version: "shotcraft-release" },
    skill_id: "promo-video",
    name: "video-shotcraft",
    description: "",
    capabilities: [],
  }

  it.each([{ skills: [...liveSkills, installedPromo] }, { skills: [] }])(
    "binds the exact source version with live options=$skills.length",
    ({ skills }) => {
    const families = resolveRecipeFamilies([], skills)
    const items = families.flatMap((family) =>
      family.subs.flatMap((sub) => sub.shelves.flatMap((shelf) => shelf.items)),
    )
    expect(items).toHaveLength(5)
    for (const item of items) {
      expect(item.kind).toBe("demo")
      if (item.kind !== "demo") continue
      if (item.demo.skillId === "promo-video") {
        expect(item.skill).toEqual(skills.length ? installedPromo : undefined)
        continue
      }
      expect(item.skill?.reference).toEqual({
        kind: "builtin",
        skill_id: item.demo.skillId,
        version: item.demo.skillVersion,
      })
      expect(item.demo.skillVersion).toBe(
        BUILTIN_SKILL_VERSIONS[item.demo.skillId as keyof typeof BUILTIN_SKILL_VERSIONS],
      )
      expect(item.prefillKey).toBe(`recipes.shelf.demos.${item.demo.id}.prompt`)
    }
  })

  it("keeps registry, short/full Skill labels, applications and prompts in en/zh sync", () => {
    for (const locale of [en, zh]) {
      for (const family of RECIPE_FAMILIES) {
        expect(family.skillId).toBeTruthy()
        expect(locale.skills.builtin).toHaveProperty(`${family.skillId}.name`)
        expect(locale.skills.builtin).toHaveProperty(`${family.skillId}.shortName`)
        for (const sub of family.subs) {
          expect(locale.recipes.shelf.subs).toHaveProperty(sub.id)
          for (const shelf of sub.shelves) {
            expect(shelf.id).toBe(sub.id)
            for (const demo of shelf.demos ?? []) {
              expect(locale.recipes.shelf.demos).toHaveProperty(`${demo.id}.prompt`)
            }
          }
        }
      }
    }
  })

  it("binds website samples to their actual source Skills and keeps replaceable slots", () => {
    const family = RECIPE_FAMILIES.find((item) => item.id === "product-promo")
    expect(family?.skillId).toBe("promo-video")
    const demos = family?.subs[0]?.shelves[0]?.demos
    expect(demos?.[0]).toMatchObject({
      skillId: "launch-film",
      skillVersion: "1.4.0",
    })
    expect(demos?.slice(1)).toMatchObject([
      { id: "product-promo-oxvalue-product-evidence", skillId: "promo-video" },
      { id: "product-promo-oxvalue-energy-arc", skillId: "promo-video" },
    ])
    for (const locale of [en, zh]) {
      for (const demo of demos ?? []) {
        expect(locale.recipes.shelf.demos).toHaveProperty(
          [demo.id, "prompt"],
          expect.stringContaining("{{placeholder}}"),
        )
      }
    }
  })
})

describe("registry integrity", () => {
  it("has unique product, application and shelf ids", () => {
    expect(new Set(RECIPE_FAMILIES.map((family) => family.id)).size).toBe(4)
    for (const family of RECIPE_FAMILIES) {
      expect(new Set(family.subs.map((sub) => sub.id)).size).toBe(family.subs.length)
      for (const sub of family.subs) {
        expect(new Set(sub.shelves.map((shelf) => shelf.id)).size).toBe(sub.shelves.length)
      }
    }
  })

  it("uses only real, content-addressed demo objects with their actual orientation", () => {
    for (const demo of demosIn(resolveRecipeFamilies([]))) {
      expect(demo.url).toMatch(
        /^https:\/\/repurposer\.tos-ap-southeast-1\.volces\.com\/demo\/outputs\/.+-[a-f0-9]{8}\.mp4$/,
      )
      expect(demo.orientation).toBe("wide")
    }
  })
})
