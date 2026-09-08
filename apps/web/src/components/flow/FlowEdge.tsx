import { BaseEdge, getBezierPath, type Edge, type EdgeProps } from "@xyflow/react"
import { useRef } from "react"

import { cn } from "@/lib/utils"

import type { FlowEdgeSemantic, GraphEdgeType } from "./types"

export interface FlowEdgeData extends Record<string, unknown> {
  /** Recipe surface: derivation vs process order. */
  semantic?: FlowEdgeSemantic
  /** Graph canvas (ADR-057 port law): the typed flow — colors the stroke
   * (video / audio), text/ctx stay neutral (every edge solid — the
   * reference flow is told by the port glyph, not the stroke). */
  edgeType?: GraphEdgeType
  /** Birth stagger delay (ms); null = render instantly (no choreography). */
  drawDelay: number | null
  /** Live "work flowing through this edge" — one short bright packet
   * riding the path (SSE status-driven, 2026-08-19; the all-edge ant march
   * retired). */
  active: boolean
}

export type FlowEdgeType = Edge<FlowEdgeData>

/** The one edge renderer — a single quiet stroke for the recipe semantics,
 * the port law's typed colors on the graph canvas (all solid), plus the
 * dashed-flow birth animation (`flow-edge-birth`: dashes march in, then
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
  // Same latch as the node card's: the surface clears the birth delay on
  // its next commit — the draw class must outlive the dashed-march keyframe
  // (a follow-up frame must not cut it), and a continuously-applied class
  // never replays.
  const drawLatchRef = useRef<number | null>(null)
  if (data?.drawDelay != null) drawLatchRef.current = data.drawDelay
  const drawDelay = drawLatchRef.current
  const draw = drawDelay != null
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        className={cn(
          "flow-edge",
          data?.edgeType
            ? `flow-edge-${data.edgeType}`
            : data?.semantic === "lineage"
              ? "flow-edge-lineage"
              : "flow-edge-dependency",
          draw && "flow-edge-born",
        )}
        style={draw ? { animationDelay: `${drawDelay}ms` } : undefined}
      />
      {data?.active && (
        <path
          d={path}
          pathLength={100}
          className={cn("flow-edge-packet", draw && "flow-edge-packet-born")}
          style={draw ? { animationDelay: `${drawDelay}ms` } : undefined}
        />
      )}
    </>
  )
}
