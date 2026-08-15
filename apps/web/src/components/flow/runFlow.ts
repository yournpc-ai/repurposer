import type { TFunction } from "i18next"

import { toAbsoluteUrl } from "@/lib/api"
import type { Output, WorkflowStep } from "@/lib/types"

import { productNodeSize, VIDEO_ASSET_NODE_SIZE } from "./layout"
import type { FlowEdge, FlowNode, FlowNodeStatus } from "./types"

/** RunFlowGraph adapter (ADR-036/041, 全栈同名 with the server graph): a
 * run's real topology → the FlowView contract, consumed by the results
 * canvas. Composition: assets left, ARTIFACT nodes middle, product outputs
 * right.
 *
 * 渲染单元 (D6 修订 2026-08-12): the canvas renders artifact nodes, not
 * steps — the unit is "something produced the user may point at in chat and
 * say 'change this'" (plan / selection / dub / music). Steps sharing the
 * class-declared `canvas_key` merge into ONE node; keyless steps fold into
 * the 过程脊; `canvas_hidden` steps (render) never appear — their state
 * projects onto the product card in place. All of it is VIEW behavior over
 * the full step rows.
 *
 * Edge discipline (prohibitions #9 / #11): dependency edges come from the
 * server's edge table (step `inputs`) plus the structural fact every recipe
 * adapter already relies on — source assets feed the root steps; lineage
 * edges come from server-resolved fields only (output.workflow_step_id).
 * Endpoint rewiring (step → its artifact card / the spine; hidden step →
 * its first rendered ancestor via `inputs`) is mechanical projection over
 * that same real data — the frontend never invents derivation. */
export interface RunFlowAsset {
  id: string
  type: string
  title: string | null
  file_url: string | null
  /** Browser-playable URL resolved through the storage seam (AssetResponse's
   * computed field) — the media src for image thumbs and inline video. */
  stream_url?: string | null
  /** Lightbox meta (AssetResponse passthrough): media duration + upload
   * time ride the info column and the chip grid. */
  duration_seconds?: number | null
  created_at?: string
}

/** User-facing product types (the /results payload is already filtered
 * server-side; internal artifact types like material_understanding never
 * become canvas nodes). */
const PRODUCT_TYPE_LABEL_KEY: Record<string, string> = {
  clip: "results.tabs.clips",
  post: "results.tabs.post",
  quotes: "results.tabs.quotes",
  carousel: "results.tabs.carousel",
  article: "results.tabs.article",
}

/** Step status → FlowView status. A parked checkpoint (`waiting`) reads as
 * not-yet-done on the canvas — the ask lives in the chat dock, not the
 * graph (D2: progress never enters the graph). */
function stepNodeStatus(status: string): FlowNodeStatus {
  switch (status) {
    case "running":
      return "running"
    case "done":
      return "done"
    case "failed":
      return "failed"
    case "skipped":
      return "skipped"
    default:
      return "pending"
  }
}

/** Aggregate status over a canvas node's member steps: failure is always
 * visible (in place — the card itself turns red), then liveness. */
function aggregateStatus(members: WorkflowStep[]): FlowNodeStatus {
  const statuses = members.map((s) => stepNodeStatus(s.status))
  if (statuses.some((s) => s === "failed")) return "failed"
  if (statuses.some((s) => s === "running")) return "running"
  if (statuses.every((s) => s === "done" || s === "skipped")) return "done"
  return "pending"
}

/** The 过程脊 group node's reserved id (D6) — every folded step's edges
 * rewire to it; the surface toggles expansion off this id. */
export const SPINE_NODE_ID = "spine"

export function runFlowGraph(
  input: {
    assets: RunFlowAsset[]
    steps: WorkflowStep[]
    outputs: Output[]
    /** The run's prompt — displayed in every product card's interaction
     * area (spec on the body; changes happen in chat). */
    prompt?: string | null
    /** The node carrying the results tour's data-tour anchors (first ready
     * product, chosen by the surface). */
    tourOutputId?: string | null
    /** 过程脊 state (D6): collapsed (default) folds the keyless plumbing
     * steps into one group node; expanded renders them as step pills.
     * Artifact cards stay cards either way — they are render units, not
     * steps. */
    spineExpanded?: boolean
  },
  t: TFunction
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const nodes: FlowNode[] = []
  const rawEdges: FlowEdge[] = []
  const { assets, steps, outputs, prompt, tourOutputId, spineExpanded = false } = input

  const stepIds = new Set(steps.map((s) => s.id))
  const byId = new Map(steps.map((s) => [s.id, s]))

  assets.forEach((asset, i) => {
    const typeLabel = t(`generationOverlay.assetTypes.${asset.type}`, {
      defaultValue: asset.type,
    })
    // file_url is a bare storage key on new rows — the browser-playable URL
    // is the computed stream_url (legacy rows carry a path/URL in file_url,
    // which toAbsoluteUrl passes through).
    const mediaUrl = toAbsoluteUrl(asset.stream_url ?? asset.file_url)
    nodes.push({
      id: `asset:${asset.id}`,
      kind: "asset",
      label: asset.title || typeLabel,
      detail: asset.title ? typeLabel : undefined,
      thumbUrl: asset.type === "image" ? mediaUrl : null,
      // The source video IS a video node — it plays inline (muted loop),
      // sized landscape so the frame is watchable.
      videoUrl: asset.type === "video" ? mediaUrl : null,
      size: asset.type === "video" ? VIDEO_ASSET_NODE_SIZE : undefined,
      order: i,
    })
  })

  // ── 渲染单元分组 (D6 修订) ────────────────────────────────────────────
  // canvas_hidden → never a node; canvas_key → merge into one artifact card
  // per key; the rest → the 过程脊.
  const artifactGroups = new Map<string, WorkflowStep[]>()
  const spineSteps: WorkflowStep[] = []
  for (const step of steps) {
    if (step.canvas_hidden) continue
    if (step.canvas_key) {
      const group = artifactGroups.get(step.canvas_key) ?? []
      artifactGroups.set(step.canvas_key, [...group, step])
    } else {
      spineSteps.push(step)
    }
  }

  // step id → rendered node id. A hidden step (render) resolves through its
  // own inputs to the first rendered ancestor — projection over the real
  // edge table, never invented lineage.
  const resolvedNode = new Map<string, string | null>()
  const resolveStepNode = (
    stepId: string,
    trail: Set<string> = new Set()
  ): string | null => {
    if (resolvedNode.has(stepId)) return resolvedNode.get(stepId)!
    if (trail.has(stepId)) return null // cycle guard — input is a DAG, never trust it
    trail.add(stepId)
    const step = byId.get(stepId)
    let id: string | null = null
    if (step) {
      if (step.canvas_key) {
        id = `artifact:${step.canvas_key}`
      } else if (!step.canvas_hidden) {
        id = spineExpanded ? `step:${step.id}` : SPINE_NODE_ID
      } else {
        for (const upstream of step.inputs ?? []) {
          id = resolveStepNode(upstream, trail)
          if (id) break
        }
      }
    }
    resolvedNode.set(stepId, id)
    return id
  }

  // Artifact cards (D6 修订): body = the group's own copy (the plan card
  // shows the picked direction in full via canvas_text; the others their
  // summary line); the mention anchors to the group's last step.
  for (const [key, members] of artifactGroups) {
    const sorted = [...members].sort((a, b) => a.seq - b.seq)
    const anchor = sorted[sorted.length - 1]
    const bodyMember = sorted.find((s) => s.canvas_text) ?? anchor
    const type = key.split(":", 1)[0]
    nodes.push({
      id: `artifact:${key}`,
      kind: "artifact",
      artifact: key,
      label: t(`results.canvas.artifact.${type}`, { defaultValue: type }),
      body: bodyMember.canvas_text ?? bodyMember.summary ?? undefined,
      // The plan card's second line = what the understanding found in the
      // material ("11 arguments · 10 quotes").
      detail:
        key === "plan"
          ? (sorted.find((s) => s.kind === "director_understand")?.summary ??
            undefined)
          : undefined,
      status: aggregateStatus(sorted),
      anchorStepId: anchor.id,
      order: sorted[0].seq,
    })
  }

  // The 过程脊: keyless plumbing folds into one expandable group node;
  // expanding reveals the step pills (artifact cards are unaffected). A
  // failed plumbing step no longer breaks out — the group node itself
  // carries the failed aggregate (the run's failure is narrated in chat).
  if (spineExpanded) {
    for (const step of spineSteps) {
      nodes.push({
        id: `step:${step.id}`,
        kind: "step",
        // The same friendly-name chain the chat step flow uses (prohibition
        // #10 — never a model name on the canvas).
        label:
          step.summary ||
          (step.stage
            ? t(`results.stepper.${step.stage}`, { defaultValue: "" })
            : "") ||
          t(`chat.stepKinds.${step.kind}`, { defaultValue: step.kind }),
        status: stepNodeStatus(step.status),
        order: step.seq,
      })
    }
  } else if (spineSteps.length > 0) {
    nodes.push({
      id: SPINE_NODE_ID,
      kind: "spine",
      label: t("results.canvas.spine"),
      detail: t("results.canvas.spineSteps", { count: spineSteps.length }),
      status: aggregateStatus(spineSteps),
      expanded: false,
      order: Math.min(...spineSteps.map((s) => s.seq)),
    })
  }

  // Step-level dependency edges (the raw table; endpoints resolve to canvas
  // nodes in the final pass).
  for (const step of steps) {
    for (const upstream of step.inputs ?? []) {
      // Guard: edges only between steps present in this run's payload.
      if (stepIds.has(upstream)) {
        rawEdges.push({
          from: `step:${upstream}`,
          to: `step:${step.id}`,
          semantic: "dependency",
        })
      }
    }
  }

  // Source assets feed the root steps (the run's entry points) — process
  // order, so the dependency semantic (recipe adapter precedent).
  const roots = steps.filter((s) => (s.inputs ?? []).length === 0)
  for (const asset of assets) {
    for (const root of roots) {
      rawEdges.push({
        from: `asset:${asset.id}`,
        to: `step:${root.id}`,
        semantic: "dependency",
      })
    }
  }

  // Products: newest-first payload → stable ascending order within a layer.
  const products = [...outputs]
    .filter((o) => o.type in PRODUCT_TYPE_LABEL_KEY)
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
  // Top pick: the batch's highest-scored clip gets the accent badge — the
  // same triage rule the old results grid used (score → what to post first).
  const topClipScore = Math.max(
    0,
    ...products
      .filter((o) => o.type === "clip")
      .map((o) => (typeof o.score?.value === "number" ? o.score.value : 0)),
  )
  products.forEach((output, i) => {
    const id = `output:${output.id}`
    const thumbUrl = toAbsoluteUrl(
      output.files.image ?? output.publishing.cover_image_url ?? null,
    )
    // Multi-item outputs (quotes = N cards, carousel = N slides): the node
    // carries one display variant per item — the hover switcher flips the
    // main display (the first quote's baked image is the only media; the
    // rest render as text tiles).
    const quotes = output.type === "quotes" ? (output.payload.quotes ?? []) : []
    const slides = output.type === "carousel" ? (output.payload.slides ?? []) : []
    const variants =
      quotes.length > 1
        ? quotes.map((q, qi) => ({
            label: q.quote,
            sub: q.attribution,
            thumbUrl: qi === 0 ? thumbUrl : null,
          }))
        : slides.length > 1
          ? slides.map((s) => ({
              label: s.title,
              sub: s.body ?? undefined,
              thumbUrl: null,
            }))
          : undefined
    nodes.push({
      id,
      kind: "output",
      label: t(PRODUCT_TYPE_LABEL_KEY[output.type], { defaultValue: output.type }),
      detail: output.language
        ? t(`languages.${output.language}`, { defaultValue: output.language })
        : undefined,
      thumbUrl,
      // The product card skin (D5): the node carries the row, sized as the
      // canvas's 大卡; the tour anchors ride the surface's chosen node. The
      // node keeps the clip's own frame (2026-08-14 三档画幅 on the canvas —
      // 9:16/1:1/16:9 node sizes, never a forced crop).
      output,
      prompt: prompt ?? null,
      variants,
      topPick:
        output.type === "clip" &&
        topClipScore > 0 &&
        output.score?.value === topClipScore,
      size: productNodeSize(
        output.type === "clip"
          ? ((output.render_spec as { aspect?: string } | null)?.aspect ?? null)
          : null,
      ),
      tourTargets: output.id === tourOutputId,
      order: i,
    })
    // Lineage = the server-resolved producing step (prohibition #11). Rows
    // carried over from an earlier run point at steps outside this payload —
    // the node still renders, edgeless, rather than inventing a parent.
    if (output.workflow_step_id && stepIds.has(output.workflow_step_id)) {
      rawEdges.push({
        from: `step:${output.workflow_step_id}`,
        to: id,
        semantic: "lineage",
      })
    }
  })

  // Final pass: step endpoints resolve to their canvas node (artifact card /
  // spine / step pill when the spine is expanded; hidden steps walk to their
  // first rendered ancestor). Self-loops and duplicates collapse — the
  // visible graph stays 真边, never invented.
  const seen = new Set<string>()
  const edges: FlowEdge[] = []
  for (const e of rawEdges) {
    const from = e.from.startsWith("step:")
      ? resolveStepNode(e.from.slice(5))
      : e.from
    const to = e.to.startsWith("step:")
      ? resolveStepNode(e.to.slice(5))
      : e.to
    if (!from || !to || from === to) continue
    const key = `${from}|${to}|${e.semantic}`
    if (seen.has(key)) continue
    seen.add(key)
    edges.push({ from, to, semantic: e.semantic })
  }

  return { nodes, edges }
}
