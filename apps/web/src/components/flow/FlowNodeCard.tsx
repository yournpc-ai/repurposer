import { Handle, Position, type Node, type NodeProps } from "@xyflow/react"
import { useState } from "react"
import {
  Check,
  ChevronDown,
  ChevronRight,
  Clapperboard,
  Download,
  FileText,
  Images,
  Loader2,
  Maximize2,
  Minus,
  Newspaper,
  Play,
  Quote,
  Send,
  Volume2,
  VolumeX,
  Waypoints,
  X,
} from "lucide-react"
import { useTranslation } from "react-i18next"

import { BrandLoader } from "@/components/BrandLoader"
import { cn } from "@/lib/utils"

import { PRODUCT_THUMB_DEFAULT_PX, PRODUCT_THUMB_PX } from "./layout"
import type { FlowNode, FlowNodeStatus, FlowOutputAction } from "./types"

export interface FlowCardData extends Record<string, unknown> {
  node: FlowNode
  /** Reveal index for birth choreography (undefined = render instantly). */
  bornIndex?: number
  selected: boolean
  /** Product-toolbar dispatch (ADR-041 D5) — the surface owns the actions. */
  onOutputAction?: (outputId: string, action: FlowOutputAction) => void
  /** Media expand dispatch — the surface opens the lightbox for the node. */
  onExpandMedia?: (nodeId: string) => void
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

/** The corner-info band above a media node (the figma-style anatomy): the
 * node's label top-LEFT, its secondary info top-RIGHT — both OUTSIDE the
 * card body, so the card carries content, not chrome. The band's height is
 * part of the node size budget (layout.ts), never an overlay. */
function NodeCaption({
  label,
  detail,
  Icon,
}: {
  label: string
  detail?: string
  Icon?: typeof Clapperboard
}) {
  return (
    <div className="flex h-[22px] shrink-0 items-end justify-between gap-2 px-0.5 pb-1">
      <span className="flex min-w-0 items-center gap-1 text-[11px] leading-none text-muted-foreground">
        {Icon ? <Icon className="h-3.5 w-3.5 shrink-0" /> : null}
        <span className="truncate">{label}</span>
      </span>
      {detail ? (
        <span className="shrink-0 text-[11px] leading-none text-muted-foreground">
          {detail}
        </span>
      ) : null}
    </div>
  )
}

/** Hover media affordance button (the reference canvas's media chrome):
 * a small dark circle revealed on the media's hover — expand top-left,
 * sound top-right. */
function MediaHoverButton({
  className,
  onClick,
  label,
  children,
}: {
  className?: string
  onClick: () => void
  label: string
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      className={cn(
        "absolute z-10 flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-white opacity-0 transition-opacity group-hover/media:opacity-100 hover:bg-black/80",
        className,
      )}
    >
      {children}
    </button>
  )
}

function ThumbCard({
  node,
  onExpandMedia,
}: {
  node: FlowNode
  onExpandMedia?: (nodeId: string) => void
}) {
  const { t } = useTranslation()
  const FallbackIcon = node.kind === "asset" ? FileText : Clapperboard
  // The inline video's ambient playback is muted by default (autoplay
  // policy); the hover sound icon flips it.
  const [muted, setMuted] = useState(true)
  const expandable = !!(node.videoUrl || node.thumbUrl) && !!onExpandMedia
  return (
    <div className="flex h-full w-full flex-col">
      <NodeCaption label={node.label} detail={node.detail} />
      <div
        className={cn(
          "group/media relative min-h-0 flex-1 overflow-hidden rounded-md",
          node.videoUrl || node.containThumb ? "bg-black" : "bg-muted",
        )}
      >
        {node.videoUrl ? (
          /* The source video node plays inline — muted ambient loop, first
             frame instantly (preload=metadata), non-interactive: clicks and
             drags belong to the canvas. */
          <video
            src={node.videoUrl}
            aria-label={node.label}
            className="pointer-events-none h-full w-full object-contain"
            muted={muted}
            loop
            playsInline
            autoPlay
            preload="metadata"
            disablePictureInPicture
          />
        ) : node.thumbUrl ? (
          <img
            src={node.thumbUrl}
            alt={node.label}
            className={cn(
              "h-full w-full",
              node.containThumb ? "object-contain" : "object-cover",
            )}
          />
        ) : (
          <span className="flex h-full w-full items-center justify-center text-muted-foreground">
            <FallbackIcon className="h-5 w-5" />
          </span>
        )}
        {expandable && (
          <MediaHoverButton
            className="left-1.5 top-1.5"
            label={t("results.canvas.expand")}
            onClick={() => onExpandMedia(node.id)}
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </MediaHoverButton>
        )}
        {node.videoUrl && (
          <MediaHoverButton
            className="right-1.5 top-1.5"
            label={muted ? t("results.canvas.unmute") : t("results.canvas.mute")}
            onClick={() => setMuted((v) => !v)}
          >
            {muted ? (
              <VolumeX className="h-3.5 w-3.5" />
            ) : (
              <Volume2 className="h-3.5 w-3.5" />
            )}
          </MediaHoverButton>
        )}
        {node.status && node.status !== "pending" && (
          <span className="absolute right-1.5 top-1.5">
            <StatusBadge status={node.status} />
          </span>
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

/** The 过程脊 group node (ADR-041 D6): the folded middle steps as ONE
 * container — muted fill reads as a group, not a step (fill-first, no
 * ring); click expands in place. It never carries a toolbar (D5: process
 * nodes never do). */
function SpineCard({ node }: { node: FlowNode }) {
  return (
    <div className="flex h-full w-full items-center gap-2.5 rounded-md bg-muted px-3 py-2">
      {node.status ? (
        <StatusBadge status={node.status} />
      ) : (
        <span className="h-5 w-5 shrink-0 rounded-full bg-card" />
      )}
      <Waypoints className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm leading-snug">{node.label}</p>
        {node.detail && (
          <p className="truncate text-xs leading-tight text-muted-foreground">{node.detail}</p>
        )}
      </div>
      {node.expanded ? (
        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
      ) : (
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
      )}
    </div>
  )
}

/** The artifact node's card (D6 修订 — the render unit is the intervenable
 * artifact: plan / selection / dub / music). Three-section anatomy (the
 * Lovart anatomy, interaction NOT copied): the type + status up top, the
 * produced thing as the body copy, the spec line at the bottom — read-only;
 * changing it happens in chat via the @workflow_step mention, never on the
 * card. No toolbar (D5: process nodes never carry one). */
function ArtifactCard({ node }: { node: FlowNode }) {
  return (
    <div className="flex h-full w-full flex-col gap-1.5 rounded-lg bg-card p-3 ring-foreground/10 ring-1">
      <div className="flex items-center justify-between gap-2">
        <p className="text-meta text-[11px]">{node.label}</p>
        {node.status && node.status !== "pending" && (
          <StatusBadge status={node.status} />
        )}
      </div>
      {node.body && (
        <p className="line-clamp-4 text-xs leading-snug">{node.body}</p>
      )}
      {node.detail && (
        <p className="mt-auto truncate text-[11px] leading-tight text-muted-foreground">
          {node.detail}
        </p>
      )}
    </div>
  )
}

/** Per-type corner-label icons (the node's type glyph, top-left). Also the
 * lightbox's type chip icon source. */
export const PRODUCT_TYPE_ICON: Record<string, typeof Clapperboard> = {
  clip: Clapperboard,
  post: FileText,
  quotes: Quote,
  carousel: Images,
  article: Newspaper,
}

/** The output node's product-card skin (ADR-041 D5 — the node IS the card),
 * 2026-08-15 anatomy (figma-style, the reference canvas's node language):
 *  1. corner-info band ABOVE the card — type + glyph top-left, language
 *     top-right; the card body carries no text chrome.
 *  2. media flush full-bleed inside the card (score / duration ride the
 *     media as badges); a rendering clip projects its state in place as the
 *     BrandLoader (never a spinner, never a status line).
 *  3. the padded interaction area below the media — the run's prompt (spec
 *     on the body, read-only; changes happen in chat) + the deterministic
 *     next-step line.
 *  4. the action pill in a reserved band UNDER the card — always visible
 *     (not hover-gated); preview / download / publish only, graph
 *     operations permanently banned (prohibition #3). The band stays
 *     reserved while a render leaves it empty — geometry never shifts. */
function ProductCard({
  node,
  selected,
  onOutputAction,
  onExpandMedia,
}: {
  node: FlowNode
  selected: boolean
  onOutputAction?: FlowCardData["onOutputAction"]
  onExpandMedia?: FlowCardData["onExpandMedia"]
}) {
  const { t } = useTranslation()
  const output = node.output
  if (!output) return <ThumbCard node={node} onExpandMedia={onExpandMedia} />

  const score = typeof output.score?.value === "number" ? output.score.value : null
  const duration = output.type === "clip" ? (output.payload.duration ?? null) : null
  const hasVideo = !!output.files.video
  // The thumb keeps the clip's own frame (2026-08-14 三档画幅 on the canvas):
  // the node's height was already sized for this aspect in runFlow — the
  // strip here mirrors it exactly, and the poster letterboxes (black) rather
  // than crops if its own ratio ever disagrees.
  const clipAspect =
    output.type === "clip"
      ? ((output.render_spec as { aspect?: string } | null)?.aspect ?? null)
      : null
  const thumbPx = (clipAspect && PRODUCT_THUMB_PX[clipAspect]) || PRODUCT_THUMB_DEFAULT_PX
  // Render state projects onto the card in place (D6 修订): a failed render
  // is the CARD turning failed — never a separate node hanging off the
  // graph; the retry channel is the chat dock (D8), so no toolbar action.
  const renderFailed =
    output.type === "clip" && output.render_status === "failed"
  const renderActive =
    output.type === "clip" &&
    !hasVideo &&
    (output.render_status === "pending" || output.render_status === "rendering")
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

  // Multi-item outputs (quotes = N cards, carousel = N slides): the hover
  // switcher flips the main display between the node's variants; items
  // without their own baked media render as text tiles.
  const variants = node.variants ?? []
  const [variantIndex, setVariantIndex] = useState(0)
  const activeVariant = variants[variantIndex] ?? variants[0]
  const mediaThumb =
    variants.length > 0 ? (activeVariant?.thumbUrl ?? null) : node.thumbUrl

  return (
    <div className="group/product relative flex h-full w-full flex-col">
      {/* Variant switcher (the reference canvas's hover group): fades in at
          the node's top center on hover; each tile is one produced item. */}
      {variants.length > 1 && (
        <div className="pointer-events-none absolute -top-1 left-1/2 z-10 -translate-x-1/2 opacity-0 transition-opacity group-hover/product:opacity-100">
          <div className="overlay-surface pointer-events-auto flex items-center gap-1 rounded-lg p-1 shadow-md ring-1 ring-foreground/10">
            {variants.map((variant, vi) => (
              <button
                key={vi}
                type="button"
                aria-label={`${vi + 1}`}
                title={variant.label}
                onClick={(e) => {
                  e.stopPropagation()
                  setVariantIndex(vi)
                }}
                className={cn(
                  "flex h-7 w-7 items-center justify-center overflow-hidden rounded-md text-[11px] font-medium transition-opacity",
                  vi === (variantIndex < variants.length ? variantIndex : 0)
                    ? "ring-2 ring-foreground/60"
                    : "opacity-60 hover:opacity-100",
                  !variant.thumbUrl && "bg-muted text-muted-foreground",
                )}
              >
                {variant.thumbUrl ? (
                  <img
                    src={variant.thumbUrl}
                    alt={variant.label}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  vi + 1
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      <NodeCaption
        label={node.label}
        detail={node.detail}
        Icon={PRODUCT_TYPE_ICON[output.type] ?? Clapperboard}
      />

      <div
        className={cn(
          "flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg bg-card ring-1",
          selected ? "ring-2 ring-foreground/40" : "ring-foreground/10",
        )}
      >
        <div
          data-tour={node.tourTargets ? "results-video" : undefined}
          className={cn(
            "group/media relative shrink-0",
            clipAspect ? "bg-black" : "bg-muted",
          )}
          style={{ height: thumbPx }}
        >
          {variants.length > 0 && !mediaThumb ? (
            /* A variant without its own baked media renders as a text tile
               (the quote card / the carousel slide). */
            <span className="flex h-full w-full flex-col justify-between gap-2 p-3">
              <p className="line-clamp-4 text-xs font-medium leading-snug">
                {activeVariant?.label}
              </p>
              {activeVariant?.sub ? (
                <p className="truncate text-[11px] text-muted-foreground">
                  {activeVariant.sub}
                </p>
              ) : null}
            </span>
          ) : mediaThumb ? (
            <img
              src={mediaThumb}
              alt={node.label}
              className={cn(
                "h-full w-full",
                clipAspect ? "object-contain" : "object-cover",
              )}
            />
          ) : (
            <span className="flex h-full w-full items-center justify-center text-muted-foreground">
              {renderFailed ? (
                <X className="h-5 w-5 text-destructive" />
              ) : renderActive ? (
                /* Card-level loading is ALWAYS the brand loader (the delta
                   glyph filling = being generated), never a spinner. */
                <BrandLoader className="h-8 w-8" />
              ) : output.type === "clip" ? (
                <Clapperboard className="h-5 w-5" />
              ) : (
                <FileText className="h-5 w-5" />
              )}
            </span>
          )}
          {score !== null && !renderFailed && (
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
          {/* The hover expand rides the top-right; the duration badge moves
              to the bottom-right (video convention) to free the corner. */}
          {(hasVideo || node.thumbUrl) && !renderActive && onExpandMedia ? (
            <MediaHoverButton
              className="right-1.5 top-1.5"
              label={t("results.canvas.expand")}
              onClick={() => onExpandMedia(node.id)}
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </MediaHoverButton>
          ) : null}
          {duration !== null && duration > 0 && !renderFailed && (
            <span className="absolute bottom-1.5 right-1.5 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-white">
              {duration}s
            </span>
          )}
        </div>

        {/* The padded interaction area: the run's prompt (read-only — the
            edit channel is the chat dock, which the node click focuses) +
            the deterministic next-step line. A failed render replaces the
            next-step with the in-place failure + the chat retry channel. */}
        <div className="flex min-h-0 flex-1 flex-col gap-1 p-3">
          {node.prompt ? (
            <p title={node.prompt} className="line-clamp-2 text-xs leading-snug">
              {node.prompt}
            </p>
          ) : null}
          {renderFailed ? (
            <p className="mt-auto line-clamp-2 text-[11px] leading-snug text-destructive">
              {t("results.canvas.renderFailed")}
            </p>
          ) : renderActive ? null : (
            <p className="mt-auto line-clamp-2 text-[11px] leading-snug text-muted-foreground">
              {t(`results.nextStep.${output.type}`, {
                defaultValue: t("results.nextStep.default"),
              })}
            </p>
          )}
        </div>
      </div>

      {/* The always-on action band under the card. The pill carries only
          actions that exist for this product; the band itself is reserved
          either way, so a finishing render never shifts the graph. */}
      <div
        data-tour={node.tourTargets ? "results-menu" : undefined}
        className="flex h-[44px] shrink-0 items-start justify-center pt-2"
      >
        {actions.length > 0 && (
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
        )}
      </div>
    </div>
  )
}

/** The one node card renderer — three skins (asset/output thumbs, step pill;
 * the output skin grows into the product card when the node carries a
 * product row). Birth choreography: `flow-node-born` keyframe staggered by
 * `bornIndex` (the real compile order, replayed slowly — ADR-036 补记 3). */
export function FlowNodeCard({ data }: NodeProps<FlowCardNode>) {
  const { node, bornIndex, selected, onOutputAction, onExpandMedia } = data
  // The product card is a composite (caption + card + action band) — its
  // selected ring hugs the CARD, not the node box; every other skin is a
  // single box and takes the ring on the root.
  const isProduct = node.kind === "output" && !!node.output
  return (
    <div
      className={cn(
        "h-full w-full cursor-pointer rounded-md text-foreground transition-colors",
        node.status === "pending" && "opacity-50",
        node.status === "skipped" && "opacity-40",
        node.status === "running" && "flow-node-running",
        bornIndex !== undefined && "flow-node-born",
        selected && !isProduct && "rounded-md ring-2 ring-foreground/40",
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
      ) : node.kind === "spine" ? (
        <SpineCard node={node} />
      ) : node.kind === "artifact" ? (
        <ArtifactCard node={node} />
      ) : node.kind === "output" ? (
        <ProductCard
          node={node}
          selected={selected}
          onOutputAction={onOutputAction}
          onExpandMedia={onExpandMedia}
        />
      ) : (
        <ThumbCard node={node} onExpandMedia={onExpandMedia} />
      )}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-0 !w-0 !opacity-0"
      />
    </div>
  )
}
