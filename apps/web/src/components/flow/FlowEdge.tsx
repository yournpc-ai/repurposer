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

/** The one edge renderer — a single quiet stroke for both semantics plus
 * the dashed-flow birth animation (`flow-edge-birth`: dashes march in, then
 * settle solid). Live work rides as a second path: one short packet
 * traveling the same bezier (`flow-edge-packet`), so the base stroke never
 * flashes. */
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
    <>
      <BaseEdge
        id={id}
        path={path}
        className={cn(
          "flow-edge",
          data?.semantic === "lineage" ? "flow-edge-lineage" : "flow-edge-dependency",
          draw && "flow-edge-born",
        )}
        style={draw ? { animationDelay: `${data?.drawDelay ?? 0}ms` } : undefined}
      />
      {data?.active && (
        <path
          d={path}
          pathLength={100}
          className={cn("flow-edge-packet", draw && "flow-edge-packet-born")}
          style={draw ? { animationDelay: `${data?.drawDelay ?? 0}ms` } : undefined}
        />
      )}
    </>
  )
}
