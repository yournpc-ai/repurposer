import { Handle, Position, type Node, type NodeProps } from "@xyflow/react"
import { Check, Clapperboard, FileText, Loader2, Minus, X } from "lucide-react"

import { cn } from "@/lib/utils"

import type { FlowNode, FlowNodeStatus } from "./types"

export interface FlowCardData extends Record<string, unknown> {
  node: FlowNode
  /** Reveal index for birth choreography (undefined = render instantly). */
  bornIndex?: number
  selected: boolean
}

export type FlowCardNode = Node<FlowCardData, "flowCard">

function StatusBadge({ status }: { status: FlowNodeStatus }) {
  switch (status) {
    case "running":
      return (
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-foreground text-background">
          <Loader2 className="h-3 w-3 animate-spin" />
        </span>
      )
    case "done":
      return (
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-foreground text-background">
          <Check className="h-3 w-3" />
        </span>
      )
    case "failed":
      return (
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-destructive text-destructive-foreground">
          <X className="h-3 w-3" />
        </span>
      )
    case "skipped":
      return (
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <Minus className="h-3 w-3" />
        </span>
      )
    default:
      return null
  }
}

function ThumbCard({ node }: { node: FlowNode }) {
  const FallbackIcon = node.kind === "asset" ? FileText : Clapperboard
  return (
    <div className="flex h-full w-full flex-col gap-1.5">
      <div className="relative min-h-0 flex-1 overflow-hidden rounded-md bg-muted">
        {node.thumbUrl ? (
          <img src={node.thumbUrl} alt={node.label} className="h-full w-full object-cover" />
        ) : (
          <span className="flex h-full w-full items-center justify-center text-muted-foreground">
            <FallbackIcon className="h-5 w-5" />
          </span>
        )}
        {node.status && node.status !== "pending" && (
          <span className="absolute right-1.5 top-1.5">
            <StatusBadge status={node.status} />
          </span>
        )}
      </div>
      <div className="min-w-0">
        <p className="truncate text-xs leading-tight">{node.label}</p>
        {node.detail && (
          <p className="truncate text-[11px] leading-tight text-muted-foreground">{node.detail}</p>
        )}
      </div>
    </div>
  )
}

function StepCard({ node }: { node: FlowNode }) {
  return (
    <div className="flex h-full w-full items-center gap-2.5 rounded-md bg-card px-3 py-2 ring-foreground/10 ring-1">
      {node.status ? (
        <StatusBadge status={node.status} />
      ) : (
        <span className="h-5 w-5 shrink-0 rounded-full bg-muted" />
      )}
      {/* Labels wrap to two lines (the pill is sized for it) — a truncated
          "…" node is never acceptable. Detail stays a one-line tag. */}
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-sm leading-snug">{node.label}</p>
        {node.detail && (
          <p className="truncate text-xs leading-tight text-muted-foreground">{node.detail}</p>
        )}
      </div>
    </div>
  )
}

/** The one node card renderer — three skins (asset/output thumbs, step pill).
 * Birth choreography: `flow-node-born` keyframe staggered by `bornIndex`
 * (the real compile order, replayed slowly — ADR-036 补记 3). */
export function FlowNodeCard({ data }: NodeProps<FlowCardNode>) {
  const { node, bornIndex, selected } = data
  return (
    <div
      className={cn(
        "h-full w-full cursor-pointer rounded-md text-foreground transition-colors",
        node.status === "pending" && "opacity-50",
        node.status === "skipped" && "opacity-40",
        node.status === "running" && "flow-node-running",
        bornIndex !== undefined && "flow-node-born",
        selected && "rounded-md ring-2 ring-foreground/40",
      )}
      style={bornIndex !== undefined ? { animationDelay: `${bornIndex * 120}ms` } : undefined}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-0 !w-0 !opacity-0"
      />
      {node.kind === "step" ? <StepCard node={node} /> : <ThumbCard node={node} />}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-0 !w-0 !opacity-0"
      />
    </div>
  )
}
