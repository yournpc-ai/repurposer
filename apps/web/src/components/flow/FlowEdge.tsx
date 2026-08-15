import { BaseEdge, getBezierPath, type Edge, type EdgeProps } from "@xyflow/react"

import { cn } from "@/lib/utils"

import type { FlowEdgeSemantic } from "./types"

export interface FlowEdgeData extends Record<string, unknown> {
  semantic: FlowEdgeSemantic
  /** Birth stagger delay (ms); null = render instantly (no choreography). */
  drawDelay: number | null
  /** Live "work flowing through this edge" dashes (SSE status-driven). */
  active: boolean
}

export type FlowEdgeType = Edge<FlowEdgeData>

/** The one edge renderer — two visual semantics (lineage = the brand stroke,
 * dependency = the quiet foreground stroke) plus the dashed-flow birth
 * animation (`flow-edge-birth`: dashes march in, then settle solid). */
export function FlowEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<FlowEdgeType>) {
  const [path] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })
  const draw = data?.drawDelay != null
  return (
    <BaseEdge
      id={id}
      path={path}
      className={cn(
        "flow-edge",
        data?.semantic === "lineage" ? "flow-edge-lineage" : "flow-edge-dependency",
        draw && "flow-edge-born",
        data?.active && "flow-edge-active",
      )}
      style={draw ? { animationDelay: `${data?.drawDelay ?? 0}ms` } : undefined}
    />
  )
}
