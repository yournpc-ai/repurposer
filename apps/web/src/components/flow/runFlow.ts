import type { TFunction } from "i18next"

import { toAbsoluteUrl } from "@/lib/api"
import type { Output, WorkflowStep } from "@/lib/types"

import { PRODUCT_NODE_SIZE } from "./layout"
import type { FlowEdge, FlowNode, FlowNodeStatus } from "./types"

/** RunFlowGraph adapter (ADR-036/041, 全栈同名 with the server graph): a
 * run's real topology → the FlowView contract, consumed by the results
 * canvas. Composition (brief §2): assets left, process steps middle,
 * product outputs right.
 *
 * Edge discipline (prohibitions #9 / #11): dependency edges come from the
 * server's edge table (step `inputs`) plus the structural fact every recipe
 * adapter already relies on — source assets feed the root steps; lineage
 * edges come from server-resolved fields only (output.workflow_step_id).
 * The frontend never invents derivation. */
export interface RunFlowAsset {
  id: string
  type: string
  title: string | null
  file_url: string | null
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

/** The 过程脊 group node's reserved id (D6) — every folded step's edges
 * rewire to it; the surface toggles expansion off this id. */
export const SPINE_NODE_ID = "spine"

export function runFlowGraph(
  input: {
    assets: RunFlowAsset[]
    steps: WorkflowStep[]
    outputs: Output[]
    /** The node carrying the results tour's data-tour anchors (first ready
     * product, chosen by the surface). */
    tourOutputId?: string | null
    /** 过程脊 state (D6): collapsed (default) folds every spine-tier step
     * into one group node; expanded renders the full step topology. */
    spineExpanded?: boolean
  },
  t: TFunction
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const nodes: FlowNode[] = []
  const rawEdges: FlowEdge[] = []
  const { assets, steps, outputs, tourOutputId, spineExpanded = false } = input

  const stepIds = new Set(steps.map((s) => s.id))

  assets.forEach((asset, i) => {
    const typeLabel = t(`generationOverlay.assetTypes.${asset.type}`, {
      defaultValue: asset.type,
    })
    nodes.push({
      id: `asset:${asset.id}`,
      kind: "asset",
      label: asset.title || typeLabel,
      detail: asset.title ? typeLabel : undefined,
      thumbUrl: asset.type === "image" ? asset.file_url : null,
      order: i,
    })
  })

  // 过程脊 (ADR-041 D6): spine-tier steps fold into one expandable group
  // node. Folding is a VIEW behavior — the step rows stay full (cost /
  // rerun / lineage read them). A FAILED step always breaks out (the D6
  // test: "hide it — does the user lose trust?"), as does a node class
  // self-describing "primary" (NodeBase.display_tier).
  const foldable = (s: WorkflowStep) =>
    s.display_tier !== "primary" && s.status !== "failed"
  const hiddenSteps = spineExpanded ? [] : steps.filter(foldable)
  const hiddenNodeIds = new Set(hiddenSteps.map((s) => `step:${s.id}`))
  const visibleSteps = spineExpanded ? steps : steps.filter((s) => !foldable(s))

  for (const step of visibleSteps) {
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

  // The spine group node: one stand-in for the folded steps, carrying their
  // count and aggregate state. Click expands in place (the surface owns the
  // toggle; the adapter just renders the state it is handed).
  if (hiddenSteps.length > 0) {
    const statuses = hiddenSteps.map((s) => stepNodeStatus(s.status))
    nodes.push({
      id: SPINE_NODE_ID,
      kind: "spine",
      label: t("results.canvas.spine"),
      detail: t("results.canvas.spineSteps", { count: hiddenSteps.length }),
      status: statuses.every((s) => s === "done" || s === "skipped")
        ? "done"
        : statuses.some((s) => s === "running")
          ? "running"
          : "pending",
      expanded: false,
      order: 0,
    })
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
    nodes.push({
      id,
      kind: "output",
      label: t(PRODUCT_TYPE_LABEL_KEY[output.type], { defaultValue: output.type }),
      detail: output.language
        ? t(`languages.${output.language}`, { defaultValue: output.language })
        : undefined,
      thumbUrl: toAbsoluteUrl(
        output.files.image ?? output.publishing.cover_image_url ?? null,
      ),
      // The product card skin (D5): the node carries the row, sized as the
      // canvas's 大卡; the tour anchors ride the surface's chosen node.
      output,
      topPick:
        output.type === "clip" &&
        topClipScore > 0 &&
        output.score?.value === topClipScore,
      size: PRODUCT_NODE_SIZE,
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

  // Fold: hidden steps' edge endpoints rewire to the spine node (self-loops
  // and duplicates collapse) — the visible graph stays真边, never invented.
  const seen = new Set<string>()
  const edges: FlowEdge[] = []
  for (const e of rawEdges) {
    const from = hiddenNodeIds.has(e.from) ? SPINE_NODE_ID : e.from
    const to = hiddenNodeIds.has(e.to) ? SPINE_NODE_ID : e.to
    if (from === to) continue
    const key = `${from}|${to}|${e.semantic}`
    if (seen.has(key)) continue
    seen.add(key)
    edges.push({ from, to, semantic: e.semantic })
  }

  return { nodes, edges }
}
