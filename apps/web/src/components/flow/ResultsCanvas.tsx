"use client"

/** ResultsCanvas (ADR-041 D1) — the project page's terminal-state default
 * center: the current run's real topology + latest products, rendered by
 * the shared FlowView substrate (prohibition #9 — no hand-drawn edges or
 * layout here). Navigation is open (pan/zoom, D7); editing gestures are
 * structurally absent in the substrate. */

import { useMemo } from "react"
import { useTranslation } from "react-i18next"

import type { Output, WorkflowStep } from "@/lib/types"

import { FlowView } from "./FlowView"
import { runFlowGraph, type RunFlowAsset } from "./runFlow"

export interface ResultsCanvasProps {
  assets: RunFlowAsset[]
  steps: WorkflowStep[]
  outputs: Output[]
  /** Birth replay in compile order — only for a completion witnessed live
   * in this session; every other entry renders the final frame instantly
   * (prohibition #5). */
  choreograph?: boolean
  /** Canvas interaction collapses the dock's history drawer (D4 点画布收回). */
  onCanvasPointerDown?: () => void
  className?: string
}

export function ResultsCanvas({
  assets,
  steps,
  outputs,
  choreograph = false,
  onCanvasPointerDown,
  className,
}: ResultsCanvasProps) {
  const { t } = useTranslation()
  const { nodes, edges } = useMemo(
    () => runFlowGraph({ assets, steps, outputs }, t),
    [assets, steps, outputs, t]
  )
  return (
    <div className={className} onPointerDown={onCanvasPointerDown}>
      <FlowView
        nodes={nodes}
        edges={edges}
        navigation="explore"
        choreograph={choreograph}
        dots
        className="h-full"
      />
    </div>
  )
}
