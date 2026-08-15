import type { TFunction } from "i18next"

import { thumbNodeSize } from "@/components/flow/layout"
import type { FlowEdge, FlowNode } from "@/components/flow/types"
import type { RecipeCard } from "@/lib/recipes"

/** Recipe adapter (D6 二次修订 2026-08-08, ADR-035/036): the Recipe data
 * pack → FlowView contract, rendered exactly ONCE in the overlay's 流程 tab
 * (the 示例 tab is flat input/output cards — a second canvas is redundant).
 * ONE graph: source material feeds the curated process steps (fanout
 * expanded), whose terminus fans out into the baked outputs.
 * assets → steps = dependency edges (process order); final step → outputs =
 * lineage edges (the outputs derive from the process). Labels are
 * pre-localized here (FlowView stays text-agnostic). */

const materialLabel = (t: TFunction, labelKey?: string | null) =>
  labelKey ? t(`recipes.materials.${labelKey}`) : null

export function recipeProcessFlow(
  card: RecipeCard,
  t: TFunction,
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const nodes: FlowNode[] = []
  const edges: FlowEdge[] = []

  // The baked outputs share the source's content — its poster doubles as
  // the source thumb when the asset itself has none (demo talk video).
  const sharedPoster =
    card.example_outputs.find((o) => o.poster_url)?.poster_url ?? null

  // Thumbs keep the card's own frame (2026-08-15 三档画幅 on the flow
  // surface): the bake preserves the source's shape, so assets and outputs
  // share one aspect — sized exactly, letterboxed never cropped.
  const thumbSize = thumbNodeSize(card.aspect)

  card.example_assets.forEach((a, i) => {
    nodes.push({
      id: `asset:${i}`,
      kind: "asset",
      label: materialLabel(t, a.label_key) ?? a.kind,
      thumbUrl: a.kind === "video" ? sharedPoster : null,
      size: thumbSize,
      containThumb: true,
      order: i,
    })
  })

  // Curated process steps, `fanout=N` expanded into N parallel branches that
  // re-join at the next level. Branch labels come from the baked outputs'
  // language keys when they line up (dub: EN original + N dubs → branches
  // are the N dubs). The first level hangs off the source material.
  let prevIds: string[] = card.example_assets.map((_, i) => `asset:${i}`)
  card.flow.forEach((step, i) => {
    const fanout = step.fanout && step.fanout > 1 ? step.fanout : 1
    const branchOutputs =
      card.example_outputs.length === fanout + 1
        ? card.example_outputs.slice(1)
        : card.example_outputs
    const ids: string[] = []
    for (let b = 0; b < fanout; b++) {
      const id = `step:${i}:${b}`
      const branch =
        fanout > 1 ? materialLabel(t, branchOutputs[b]?.label_key) : null
      ids.push(id)
      nodes.push({
        id,
        kind: "step",
        label: t(`recipes.flow.${step.key}`),
        detail: branch ?? undefined,
        order: b,
      })
    }
    for (const from of prevIds) {
      for (const to of ids) {
        edges.push({ from, to, semantic: "dependency" })
      }
    }
    prevIds = ids
  })

  // Terminus: the baked outputs fan out from the last step level (or from
  // the assets directly when a recipe curates no steps) — derivation, so
  // the lineage semantic.
  card.example_outputs.forEach((o, i) => {
    const id = `output:${i}`
    nodes.push({
      id,
      kind: "output",
      label: materialLabel(t, o.label_key) ?? o.kind,
      thumbUrl: o.poster_url ?? null,
      size: thumbSize,
      containThumb: true,
      order: i,
    })
    for (const from of prevIds) {
      edges.push({ from, to: id, semantic: "lineage" })
    }
  })

  return { nodes, edges }
}
