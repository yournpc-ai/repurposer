import { Handle, Position, type Node, type NodeProps } from "@xyflow/react"
import {
  Check,
  Clapperboard,
  Download,
  FileText,
  Loader2,
  Minus,
  Play,
  Send,
  X,
} from "lucide-react"
import { useTranslation } from "react-i18next"

import { cn } from "@/lib/utils"

import type { FlowNode, FlowNodeStatus, FlowOutputAction } from "./types"

export interface FlowCardData extends Record<string, unknown> {
  node: FlowNode
  /** Reveal index for birth choreography (undefined = render instantly). */
  bornIndex?: number
  selected: boolean
  /** Product-toolbar dispatch (ADR-041 D5) — the surface owns the actions. */
  onOutputAction?: (outputId: string, action: FlowOutputAction) => void
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

/** The output node's product-card skin (ADR-041 D5 — the node IS the card):
 * thumbnail with the score / top-pick badge, title, and the deterministic
 * next-step line. On hover a floating toolbar rides above the card (with a
 * gap) carrying the old card-face actions — preview / download / publish;
 * graph operations are permanently banned from it (prohibition #3). */
function ProductCard({
  node,
  onOutputAction,
}: {
  node: FlowNode
  onOutputAction?: FlowCardData["onOutputAction"]
}) {
  const { t } = useTranslation()
  const output = node.output
  if (!output) return <ThumbCard node={node} />

  const title =
    output.publishing.title ||
    output.payload.hook ||
    output.payload.title ||
    output.payload.content?.split("\n", 1)[0] ||
    node.label
  const score = typeof output.score?.value === "number" ? output.score.value : null
  const duration = output.type === "clip" ? (output.payload.duration ?? null) : null
  const hasVideo = !!output.files.video
  // The toolbar only carries actions that exist for this product type —
  // moved over from the old card faces, nothing new invented (D5 平移): a
  // clip without its MP4 yet offers neither preview nor download (the old
  // menu gated the same way).
  const canDownload =
    output.type === "clip"
      ? hasVideo
      : output.type === "quotes"
        ? !!output.files.image
        : true
  const actions: { action: FlowOutputAction; Icon: typeof Play; label: string }[] = []
  if (output.type === "clip" && hasVideo) {
    actions.push({ action: "preview", Icon: Play, label: t("results.canvas.preview") })
  }
  if (canDownload) {
    actions.push({
      action: "download",
      Icon: Download,
      label: t("results.canvas.download"),
    })
  }
  if (output.type === "clip" && hasVideo) {
    actions.push({ action: "publish", Icon: Send, label: t("results.canvas.publish") })
  }

  return (
    <div
      data-tour={node.tourTargets ? "results-menu" : undefined}
      className="group/product relative flex h-full w-full flex-col gap-2 rounded-lg bg-card p-2 ring-foreground/10 ring-1"
    >
      {/* Hover toolbar — a floating pill with a gap above the card. It is
          part of the node (absolute, not fixed): no portal, no transformed-
          ancestor teleport. Graph actions never live here. */}
      <div className="pointer-events-none absolute -top-11 left-1/2 z-10 -translate-x-1/2 opacity-0 transition-opacity group-hover/product:pointer-events-auto group-hover/product:opacity-100">
        <div className="overlay-surface flex items-center gap-0.5 rounded-lg p-1">
          {actions.map(({ action, Icon, label }) => (
            <button
              key={action}
              type="button"
              title={label}
              aria-label={label}
              className="flex h-7 w-7 items-center justify-center rounded-md text-foreground transition-colors hover:bg-accent"
              onClick={(e) => {
                e.stopPropagation()
                onOutputAction?.(output.id, action)
              }}
            >
              <Icon className="h-4 w-4" />
            </button>
          ))}
        </div>
      </div>

      <div
        data-tour={node.tourTargets ? "results-video" : undefined}
        className="relative h-28 shrink-0 overflow-hidden rounded-md bg-muted"
      >
        {node.thumbUrl ? (
          <img src={node.thumbUrl} alt={title} className="h-full w-full object-cover" />
        ) : (
          <span className="flex h-full w-full items-center justify-center text-muted-foreground">
            {output.type === "clip" ? (
              <Clapperboard className="h-5 w-5" />
            ) : (
              <FileText className="h-5 w-5" />
            )}
          </span>
        )}
        {score !== null && (
          <span
            data-tour={node.tourTargets ? "results-score" : undefined}
            title={output.score?.reason ?? undefined}
            className={cn(
              "absolute left-1.5 top-1.5 rounded px-1.5 py-0.5 text-[10px] font-medium",
              node.topPick
                ? "bg-primary text-primary-foreground"
                : "bg-black/70 text-white",
            )}
          >
            {node.topPick ? `${t("results.topPick")} · ${score}` : score}
          </span>
        )}
        {duration !== null && duration > 0 && (
          <span className="absolute right-1.5 top-1.5 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-white">
            {duration}s
          </span>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-1 px-0.5">
        <p className="line-clamp-2 text-xs font-medium leading-snug">{title}</p>
        <p className="truncate text-[11px] leading-tight text-muted-foreground">
          {node.label}
          {node.detail ? ` · ${node.detail}` : ""}
        </p>
        {/* The deterministic next-step line (D5 下一步建议 — zero-LLM,
            derived from the product type; the consultant posture's "always
            one next step", presented, never a control). */}
        <p className="mt-auto line-clamp-2 text-[11px] leading-snug text-muted-foreground">
          {t(`results.nextStep.${output.type}`, {
            defaultValue: t("results.nextStep.default"),
          })}
        </p>
      </div>
    </div>
  )
}

/** The one node card renderer — three skins (asset/output thumbs, step pill;
 * the output skin grows into the product card when the node carries a
 * product row). Birth choreography: `flow-node-born` keyframe staggered by
 * `bornIndex` (the real compile order, replayed slowly — ADR-036 补记 3). */
export function FlowNodeCard({ data }: NodeProps<FlowCardNode>) {
  const { node, bornIndex, selected, onOutputAction } = data
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
      {node.kind === "step" ? (
        <StepCard node={node} />
      ) : node.kind === "output" ? (
        <ProductCard node={node} onOutputAction={onOutputAction} />
      ) : (
        <ThumbCard node={node} />
      )}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-0 !w-0 !opacity-0"
      />
    </div>
  )
}
