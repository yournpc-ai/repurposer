"use client"

/** ResultsCanvas (ADR-041 D1) — the project page's terminal-state default
 * center: the current run's real topology + latest products, rendered by
 * the shared FlowView substrate (prohibition #9 — no hand-drawn edges or
 * layout here). Navigation is open (pan/zoom, D7); editing gestures are
 * structurally absent in the substrate. Product nodes are cards (D5): the
 * surface owns their actions — click focuses (焦点注入, D8; a clip also
 * opens its detail modal), the hover toolbar reports preview / download /
 * publish. */

import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import type { Output, WorkflowStep } from "@/lib/types"

import { FlowView } from "./FlowView"
import { runFlowGraph, SPINE_NODE_ID, type RunFlowAsset } from "./runFlow"
import type { FlowOutputAction } from "./types"

export interface ResultsCanvasProps {
  assets: RunFlowAsset[]
  steps: WorkflowStep[]
  outputs: Output[]
  /** Birth replay in compile order — only for a completion witnessed live
   * in this session; every other entry renders the final frame instantly
   * (prohibition #5). */
  choreograph?: boolean
  /** The node carrying the results tour's data-tour anchors. */
  tourOutputId?: string | null
  /** A product node was clicked — the surface sets the dock focus and opens
   * the detail modal (clips). */
  onOutputClick?: (output: Output) => void
  /** A product node's hover-toolbar action (preview / download / publish). */
  onOutputAction?: (output: Output, action: FlowOutputAction) => void
  /** A process step node was clicked (the spine expanded) — the surface
   * inserts the step's @workflow_step mention into the dock (D8). */
  onStepClick?: (stepId: string, label: string) => void
  /** Canvas interaction collapses the dock's history drawer (D4 点画布收回). */
  onCanvasPointerDown?: () => void
  className?: string
}

export function ResultsCanvas({
  assets,
  steps,
  outputs,
  choreograph = false,
  tourOutputId,
  onOutputClick,
  onOutputAction,
  onStepClick,
  onCanvasPointerDown,
  className,
}: ResultsCanvasProps) {
  const { t } = useTranslation()
  // 过程脊 expand/collapse is view state (D6 — the graph data is always
  // full; only the surface's density flips).
  const [spineExpanded, setSpineExpanded] = useState(false)
  const { nodes, edges } = useMemo(
    () => runFlowGraph({ assets, steps, outputs, tourOutputId, spineExpanded }, t),
    [assets, steps, outputs, tourOutputId, spineExpanded, t]
  )
  const outputById = useMemo(
    () => new Map(outputs.map((o) => [`output:${o.id}`, o])),
    [outputs]
  )
  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  return (
    <div className={className} onPointerDown={onCanvasPointerDown}>
      <FlowView
        nodes={nodes}
        edges={edges}
        navigation="explore"
        choreograph={choreograph}
        dots
        className="h-full"
        onSelect={(id) => {
          // The spine group node toggles in place; a step node points the
          // dock at it (@workflow_step); a product node focuses / details.
          if (id === SPINE_NODE_ID) {
            setSpineExpanded((v) => !v)
            return
          }
          const output = outputById.get(id)
          if (output) {
            onOutputClick?.(output)
            return
          }
          if (id.startsWith("step:")) {
            const node = nodeById.get(id)
            if (node) onStepClick?.(id.slice(5), node.label)
          }
        }}
        onOutputAction={(id, action) => {
          const output = outputById.get(`output:${id}`)
          if (output) onOutputAction?.(output, action)
        }}
      />
    </div>
  )
}
