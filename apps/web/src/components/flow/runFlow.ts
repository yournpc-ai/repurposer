import type { TFunction } from "i18next"

import type { FlowEdge, FlowNode, FlowNodeStatus } from "./types"
import type { Output, WorkflowStep } from "@/lib/types"

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

export function runFlowGraph(
  input: {
    assets: RunFlowAsset[]
    steps: WorkflowStep[]
    outputs: Output[]
  },
  t: TFunction
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const nodes: FlowNode[] = []
  const edges: FlowEdge[] = []
  const { assets, steps, outputs } = input

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

  for (const step of steps) {
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
    for (const upstream of step.inputs ?? []) {
      // Guard: edges only between steps present in this run's payload.
      if (stepIds.has(upstream)) {
        edges.push({
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
      edges.push({
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
  products.forEach((output, i) => {
    const id = `output:${output.id}`
    nodes.push({
      id,
      kind: "output",
      label: t(PRODUCT_TYPE_LABEL_KEY[output.type], { defaultValue: output.type }),
      detail: output.language
        ? t(`languages.${output.language}`, { defaultValue: output.language })
        : undefined,
      thumbUrl: output.files.image ?? null,
      order: i,
    })
    // Lineage = the server-resolved producing step (prohibition #11). Rows
    // carried over from an earlier run point at steps outside this payload —
    // the node still renders, edgeless, rather than inventing a parent.
    if (output.workflow_step_id && stepIds.has(output.workflow_step_id)) {
      edges.push({
        from: `step:${output.workflow_step_id}`,
        to: id,
        semantic: "lineage",
      })
    }
  })

  return { nodes, edges }
}
