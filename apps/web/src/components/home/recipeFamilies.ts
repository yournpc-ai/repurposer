/**
 * Home's two-level creation shelf: four video products × two typical
 * applications × real sample cards. Product names come from the built-in
 * Skill registry's localized display names; application and prompt copy live
 * in i18n. Every sample resolves to the exact built-in Skill reference +
 * editable prompt payload used for its new creation journey.
 *
 * Video application seats stay visible when their sample list is empty. The
 * shared shelf renders an honest empty state; it never substitutes another
 * sample or hides the product. Non-video Recipe mappings and prompt payloads
 * remain registered below, but the retired task groups are not Home tabs.
 *
 * Clicking a card only prefills the composer. It never sends a message,
 * uploads material, creates a project/Run, or grants production intent.
 */

import type { LucideIcon } from "lucide-react"

import type { RecipePublic } from "@/lib/recipes"
import {
  skillOptionForReference,
  type SkillOption,
} from "@/lib/skills"

/** One real sample video on a product application shelf. */
export interface ShelfDemo {
  /** Stable business key; prompt copy lives at
   * `recipes.shelf.demos.<id>.prompt`. */
  id: string
  /** Public, content-addressed bytes under the reserved demo/ prefix. */
  url: string
  /** The file's real aspect ratio; media is never stretched to fit a card. */
  orientation: "wide" | "vertical"
  /** Exact immutable built-in Skill binding used by the source journey. */
  skillId: string
  skillVersion?: string
}

export interface RecipeShelfDef {
  /** Application id — its label key is `recipes.shelf.subs.<id>`. */
  id: string
  kind: "recipes" | "demos"
  demos?: ShelfDemo[]
}

export interface RecipeSubTabDef {
  id: string
  shelves: RecipeShelfDef[]
}

export interface RecipeFamilyDef {
  id: string
  /** Product label reuses `skills.builtin.<skillId>.name` via
   * `skillDisplayName`; Home does not maintain another product-name table. */
  skillId?: string
  icon?: LucideIcon
  disabled?: boolean
  /** Keep empty demo applications visible with the shared empty state. */
  preserveEmptyDemoShelves?: boolean
  subs: RecipeSubTabDef[]
}

/** Existing non-video Recipe ownership. These mappings do not create video
 * product tabs or alter the cards' existing prompt/capability registration. */
export const RECIPE_CARD_FAMILY: Record<string, string> = {
  "multilingual-subs": "talks",
  "voice-dub": "talks",
  "highlight-clips": "talks",
  reframe: "talks",
  "social-post": "posts",
  carousel: "posts",
  "quote-cards": "posts",
  "image-video": "templates",
}

/** Shelf-only visibility; hidden cards remain registered capabilities. */
export const DEMO_HIDDEN_CARDS: ReadonlySet<string> = new Set([
  "quote-cards",
  "image-video",
])

export function recipeCardFamily(card: RecipePublic): string {
  return RECIPE_CARD_FAMILY[card.id] ?? "templates"
}

/** The current Home video shelf. Exactly eight application seats are visible;
 * five entries backed by real source journeys have media. The other five
 * shelves intentionally remain empty. */
export const RECIPE_FAMILIES: RecipeFamilyDef[] = [
  {
    id: "product-promo",
    skillId: "promo-video",
    preserveEmptyDemoShelves: true,
    subs: [
      {
        id: "website-product",
        shelves: [
          {
            id: "website-product",
            kind: "demos",
            demos: [
              {
                // Project b8b20d17… / Output cf91834d…, revision 2.
                id: "product-promo-agentveil-the-next-move",
                skillId: "launch-film",
                skillVersion: "1.4.0",
                url: "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/product-promo-agentveil-the-next-move-a2a4b391.mp4",
                orientation: "wide",
              },
              {
                // Project 7386da2b… / Output 73258a3a…, V1 product-evidence.
                id: "product-promo-oxvalue-product-evidence",
                skillId: "promo-video",
                url: "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/product-promo-oxvalue-product-evidence-e1e78348.mp4",
                orientation: "wide",
              },
              {
                // Project 9f7440f8… / Output a98d24e9…, V1 energy arc.
                id: "product-promo-oxvalue-energy-arc",
                skillId: "promo-video",
                url: "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/product-promo-oxvalue-energy-arc-6f210db6.mp4",
                orientation: "wide",
              },
            ],
          },
        ],
      },
      {
        id: "course-service",
        shelves: [{ id: "course-service", kind: "demos", demos: [] }],
      },
    ],
  },
  {
    id: "talking-head",
    skillId: "talking-head-video",
    preserveEmptyDemoShelves: true,
    subs: [
      {
        id: "opinion-talking-head",
        shelves: [{ id: "opinion-talking-head", kind: "demos", demos: [] }],
      },
      {
        id: "course-lecture-teaser",
        shelves: [{ id: "course-lecture-teaser", kind: "demos", demos: [] }],
      },
    ],
  },
  {
    id: "text-animation",
    skillId: "text-animation",
    preserveEmptyDemoShelves: true,
    subs: [
      {
        id: "opinion-text",
        shelves: [
          {
            id: "opinion-text",
            kind: "demos",
            demos: [
              {
                // Project e92babc3… / Output c71525b6…, revision 2.
                id: "text-short-clear-rhythm",
                skillId: "text-animation",
                skillVersion: "1.0.0",
                url: "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/text-short-clear-rhythm-2d594025.mp4",
                orientation: "wide",
              },
            ],
          },
        ],
      },
      {
        id: "quote-announcement",
        shelves: [{ id: "quote-announcement", kind: "demos", demos: [] }],
      },
    ],
  },
  {
    id: "knowledge-explainer",
    skillId: "knowledge-explainer",
    preserveEmptyDemoShelves: true,
    subs: [
      {
        id: "concept-explainer",
        shelves: [
          {
            id: "concept-explainer",
            kind: "demos",
            demos: [
              {
                // Project 0d6104fd… / Output 2b791e37…, revision 2.
                id: "knowledge-explainer-clear-expression",
                skillId: "knowledge-explainer",
                skillVersion: "1.0.0",
                url: "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/knowledge-explainer-clear-expression-73f4a743.mp4",
                orientation: "wide",
              },
            ],
          },
        ],
      },
      {
        id: "research-report",
        shelves: [{ id: "research-report", kind: "demos", demos: [] }],
      },
    ],
  },
]

export type ShelfItem =
  | { kind: "recipe"; card: RecipePublic; prefillKey: string; skill?: SkillOption }
  | { kind: "demo"; demo: ShelfDemo; prefillKey: string; skill?: SkillOption }

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
  skillId?: string
  icon?: LucideIcon
  disabled?: boolean
  subs: ResolvedSub[]
}

/** Project registry definitions and fetched cards into renderable shelves.
 * Generic empty Recipe groups still collapse; opted-in video demo shelves
 * preserve their application seat so the empty state is visible. */
export function resolveFamilies(
  families: RecipeFamilyDef[],
  cards: RecipePublic[],
  skills: SkillOption[] = [],
): ResolvedFamily[] {
  const cardsByFamily = new Map<string, RecipePublic[]>()
  for (const card of cards) {
    if (DEMO_HIDDEN_CARDS.has(card.id)) continue
    const familyId = recipeCardFamily(card)
    const list = cardsByFamily.get(familyId)
    if (list) list.push(card)
    else cardsByFamily.set(familyId, [card])
  }
  return families
    .map((family) => ({
      id: family.id,
      skillId: family.skillId,
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
                      skill: demo.skillVersion
                        ? skillOptionForReference(
                            { kind: "builtin", skill_id: demo.skillId, version: demo.skillVersion },
                            skills,
                          )
                        : skills.find((option) => option.reference.kind === "builtin"
                          && option.skill_id === demo.skillId),
                    })),
            }))
            .filter(
              (shelf) =>
                shelf.items.length > 0 ||
                (family.preserveEmptyDemoShelves === true &&
                  sub.shelves.find((candidate) => candidate.id === shelf.id)?.kind ===
                    "demos"),
            ),
        }))
        .filter((sub) => sub.shelves.length > 0),
    }))
    .filter((family) => family.subs.length > 0)
}

export function resolveRecipeFamilies(
  cards: RecipePublic[],
  skills: SkillOption[] = [],
): ResolvedFamily[] {
  return resolveFamilies(RECIPE_FAMILIES, cards, skills)
}
