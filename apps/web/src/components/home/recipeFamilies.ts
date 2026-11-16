import type { BUILTIN_SKILL_VERSIONS } from "@/lib/skills"

export interface ShelfDemo {
  id: string
  url: string
}

interface RecipeApplication {
  id: string
  demos: readonly ShelfDemo[]
}

export interface RecipeFamily {
  id: string
  skillId: keyof typeof BUILTIN_SKILL_VERSIONS
  subs: readonly [RecipeApplication, RecipeApplication]
}

const DEMO_OUTPUTS = "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs"

export const RECIPE_FAMILIES: readonly [RecipeFamily, ...RecipeFamily[]] = [
  {
    id: "product-promo",
    skillId: "promo-video",
    subs: [
      {
        id: "website-product",
        demos: [
          {
            id: "product-promo-oxvalue-product-evidence",
            url: `${DEMO_OUTPUTS}/product-promo-oxvalue-product-evidence-e1e78348.mp4`,
          },
          {
            id: "product-promo-oxvalue-energy-arc",
            url: `${DEMO_OUTPUTS}/product-promo-oxvalue-energy-arc-6f210db6.mp4`,
          },
        ],
      },
      { id: "course-service", demos: [] },
    ],
  },
  {
    id: "talking-head",
    skillId: "talking-head-video",
    subs: [
      { id: "opinion-talking-head", demos: [] },
      { id: "course-lecture-teaser", demos: [] },
    ],
  },
  {
    id: "text-animation",
    skillId: "text-animation",
    subs: [
      {
        id: "opinion-text",
        demos: [
          {
            id: "text-short-clear-rhythm",
            url: `${DEMO_OUTPUTS}/text-short-clear-rhythm-2d594025.mp4`,
          },
        ],
      },
      { id: "quote-announcement", demos: [] },
    ],
  },
  {
    id: "knowledge-explainer",
    skillId: "knowledge-explainer",
    subs: [
      {
        id: "concept-explainer",
        demos: [
          {
            id: "knowledge-explainer-clear-expression",
            url: `${DEMO_OUTPUTS}/knowledge-explainer-clear-expression-73f4a743.mp4`,
          },
        ],
      },
      { id: "research-report", demos: [] },
    ],
  },
]
