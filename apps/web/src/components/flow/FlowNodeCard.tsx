import { Handle, Position, type Node, type NodeProps } from "@xyflow/react"
import { useEffect, useRef, useState } from "react"
import {
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  Clapperboard,
  Download,
  FileText,
  Image as ImageIcon,
  Images,
  Maximize2,
  MoreHorizontal,
  Newspaper,
  Quote,
  Trash2,
  TriangleAlert,
  Volume2,
  VolumeX,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { BrandLoader } from "@/components/BrandLoader"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { apiPut, toAbsoluteUrl } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { GraphEdgeType, Output } from "@/lib/types"

import { BIRTH_STAGGER_MS, PRODUCT_THUMB_DEFAULT_PX, PRODUCT_THUMB_PX } from "./layout"
import type {
  FlowAssetAction,
  FlowAssetInfo,
  FlowNode,
  FlowOutputAction,
} from "./types"

export interface FlowCardData extends Record<string, unknown> {
  node: FlowNode
  /** Reveal index for birth choreography (undefined = render instantly). */
  bornIndex?: number
  selected: boolean
  /** The node's visible ports (ADR-057 端口法则 — computed by FlowView from
   * the incident typed edges): in-ports stack from the consumption region's
   * bottom-left corner, out-ports from the production region's top-right.
   * Undefined = an untyped surface (the recipe 说明书 — the legacy
   * invisible handles render instead). */
  ports?: { in: GraphEdgeType[]; out: GraphEdgeType[] }
  /** Product-toolbar dispatch (ADR-041 D5) — the surface owns the actions. */
  onOutputAction?: (outputId: string, action: FlowOutputAction) => void
  /** Asset-toolbar dispatch (2026-08-17) — the surface owns asset actions. */
  onAssetAction?: (asset: FlowAssetInfo, action: FlowAssetAction) => void
  /** Media expand dispatch — the surface opens the lightbox for the node.
   * `outputId` overrides the node's own row when the pager has the card
   * displaying a sibling (the lightbox must show what the card shows). */
  onExpandMedia?: (nodeId: string, outputId?: string) => void
  /** Revision-turn dispatch (ADR-051 F — hover prompt 框): the edited spec
   * text rides the surface's chat channel with this output pinned as focus.
   * The output id is the DISPLAYED member's (the revision targets the
   * product the user is looking at). */
  onRevise?: (outputId: string, text: string) => void
  /** The pager's displayed product (mount + flip) — the surface tracks it
   * so a node click selects what the user is LOOKING at. */
  onDisplayChange?: (nodeId: string, outputId: string) => void
  /** Card-face prompt direct edit (ADR-057 K4): the card reports the new
   * program; the surface opens the pricing confirmation (锚定子图 + 估价)
   * — nothing touches the graph until the confirmed turn rides chat. */
  onPromptEdit?: (nodeId: string, text: string) => void
}

export type FlowCardNode = Node<FlowCardData, "flowCard">

/** The corner-info band above a media node (2026-08-17 走查拍板, Lovart
 * 解剖; ADR-057 §5): ALWAYS the node's type icon + type name at the
 * top-LEFT, and the right slot stays EMPTY — state expresses in place
 * (draft dashed / running wipe / done self-evident / failed in-card red /
 * stale factsbar badge), never a caption badge. The band's height is part
 * of the node size budget (layout.ts), never an overlay. */
function NodeCaption({
  label,
  Icon,
}: {
  label: string
  Icon?: typeof Clapperboard
}) {
  return (
    <div className="flex h-[26px] shrink-0 items-end gap-2 px-1 pb-2">
      <span className="flex min-w-0 items-center gap-1 text-[11px] leading-none text-muted-foreground">
        {Icon ? <Icon className="h-3.5 w-3.5 shrink-0" /> : null}
        <span className="truncate">{label}</span>
      </span>
    </div>
  )
}

/** Hover media affordance button (the reference canvas's media chrome):
 * a small dark circle revealed on the media's hover — expand top-left,
 * sound top-right, both 8px off the corner. */
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
        // Hover-revealed on pointer devices; always on under (hover: none)
        // (2026-08-19 二轮 R4 — iPad 触摸拿得到画布，hover 揭示在触摸上
        // 没有对应手势).
        "absolute z-10 flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-white opacity-0 transition-opacity group-hover/media:opacity-100 hover:bg-black/80 [@media(hover:none)]:opacity-100",
        className,
      )}
    >
      {children}
    </button>
  )
}

/** The node's factsbar (2026-08-17 走查拍板, Lovart 解剖; ADR-057 §5 外置):
 * one frosted bar (dock-surface + hairline, never bare icons) parked UNDER
 * the card — runtime facts on the left (filename / duration / resolution /
 * language / model — OutputInspector 同源), a hairline divider, then the
 * actions; node business (publish / open / focus / reprocess) lives in the
 * ⋯ menu at the right end. The bar hugs its content — width is NOT capped
 * by the node and facts NEVER ellipsize (2026-08-17 二轮走查拍板): it
 * centers under the card and overhangs symmetrically when the facts are
 * long. */
function MediaToolbar({
  info,
  actions,
  menuItems,
  moreLabel,
  badge,
  onAction,
}: {
  info: string[]
  actions: { action: string; Icon: typeof Download; label: string }[]
  menuItems: { action: string; label: string }[]
  /** aria/title for the ⋯ trigger (i18n from the caller). */
  moreLabel: string
  /** A quiet badge riding the bar's left end (the stale 可重跑 marker —
   * state as a fact, in the facts row, never a caption badge). */
  badge?: string | null
  onAction: (action: string) => void
}) {
  return (
    <div className="dock-surface flex items-center gap-1 rounded-lg p-1 ring-1 ring-foreground/10">
      {badge && (
        <span className="mx-1 rounded bg-muted px-1.5 py-0.5 text-[10px] whitespace-nowrap text-muted-foreground">
          {badge}
        </span>
      )}
      {info.length > 0 && (
        <span className="flex items-center gap-2 pl-1.5 pr-1 text-[11px] whitespace-nowrap text-muted-foreground">
          {info.map((s, i) => (
            <span key={i}>{s}</span>
          ))}
        </span>
      )}
      {(badge || info.length > 0) && (actions.length > 0 || menuItems.length > 0) && (
        <span className="h-3.5 w-px shrink-0 bg-foreground/15" />
      )}
      {actions.map(({ action, Icon, label }) => (
        <button
          key={action}
          type="button"
          title={label}
          aria-label={label}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-foreground transition-colors hover:bg-accent"
          onClick={(e) => {
            e.stopPropagation()
            onAction(action)
          }}
        >
          <Icon className="h-3.5 w-3.5" />
        </button>
      ))}
      {menuItems.length > 0 && (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                type="button"
                aria-label={moreLabel}
                title={moreLabel}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-foreground transition-colors hover:bg-accent"
                onClick={(e) => e.stopPropagation()}
              />
            }
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="end">
            {menuItems.map(({ action, label }) => (
              <DropdownMenuItem
                key={action}
                onClick={(e) => {
                  e.stopPropagation()
                  onAction(action)
                }}
              >
                {label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  )
}

/** The version pager (ADR-051 F2 mechanics, generalized 2026-09-07 from the
 * fork family to the node's slot siblings): the card's display AND its
 * action target flip among the node's REAL product rows. Rides the factsbar
 * band as its own pill, NEVER merged with the hover items switcher
 * (条目切换 ≠ 版本切换). */
function VersionPager({
  current,
  total,
  onFlip,
}: {
  current: number
  total: number
  onFlip: (delta: number) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="dock-surface flex items-center gap-0.5 rounded-lg p-1 ring-1 ring-foreground/10">
      <button
        type="button"
        aria-label={t("results.canvas.versionPrev")}
        title={t("results.canvas.versionPrev")}
        disabled={current <= 0}
        onClick={(e) => {
          e.stopPropagation()
          onFlip(-1)
        }}
        className="flex h-7 w-7 items-center justify-center rounded-md text-foreground transition-colors hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent"
      >
        <ChevronLeft className="h-3.5 w-3.5" />
      </button>
      <span className="px-1 text-[11px] whitespace-nowrap tabular-nums text-muted-foreground">
        {t("results.canvas.versionOf", { current: current + 1, total })}
      </span>
      <button
        type="button"
        aria-label={t("results.canvas.versionNext")}
        title={t("results.canvas.versionNext")}
        disabled={current >= total - 1}
        onClick={(e) => {
          e.stopPropagation()
          onFlip(1)
        }}
        className="flex h-7 w-7 items-center justify-center rounded-md text-foreground transition-colors hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent"
      >
        <ChevronRight className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

/** Per-type corner-label icons (the node's type glyph, top-left). Also the
 * lightbox's type chip icon source. */
export const PRODUCT_TYPE_ICON: Record<string, typeof Clapperboard> = {
  clip: Clapperboard,
  post: FileText,
  quotes: Quote,
  quote_frame: ImageIcon,
  carousel: Images,
  article: Newspaper,
}

function ThumbCard({
  node,
  onExpandMedia,
  onAssetAction,
}: {
  node: FlowNode
  onExpandMedia?: (nodeId: string) => void
  onAssetAction?: FlowCardData["onAssetAction"]
}) {
  const { t } = useTranslation()
  const FallbackIcon = node.kind === "asset" ? FileText : Clapperboard
  // The inline video's ambient playback is muted by default (autoplay
  // policy); the hover sound icon flips it.
  const [muted, setMuted] = useState(true)
  // Media facts for the toolbar are read off the loaded media itself — the
  // real pixels, never a hardcoded table.
  const [dims, setDims] = useState<string | null>(null)
  const expandable = !!(node.videoUrl || node.thumbUrl) && !!onExpandMedia
  const asset = node.asset
  const TypeIcon =
    asset?.type === "video"
      ? Clapperboard
      : asset?.type === "image"
        ? ImageIcon
        : FileText

  // The asset toolbar (results canvas only — a node without the action
  // channel, e.g. the recipe manual, renders no bar): media facts on the
  // left (filename / duration / resolution), then download / delete, and
  // the node's own business (open / reprocess) in the ⋯ menu.
  const showBar = !!onAssetAction && !!asset
  const info: string[] = []
  if (node.detail) info.push(node.detail)
  if (asset?.duration_seconds) info.push(`${asset.duration_seconds}s`)
  if (dims) info.push(dims)
  const handleBarAction = (action: string) => {
    if (action === "open") {
      onExpandMedia?.(node.id)
      return
    }
    if (asset) onAssetAction?.(asset, action as FlowAssetAction)
  }

  return (
    <div className="flex h-full w-full flex-col">
      <NodeCaption label={node.label} Icon={asset ? TypeIcon : undefined} />
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
            onLoadedMetadata={(e) =>
              setDims(
                `${e.currentTarget.videoWidth}×${e.currentTarget.videoHeight}`
              )
            }
          />
        ) : node.thumbUrl ? (
          <img
            src={node.thumbUrl}
            alt={node.label}
            className={cn(
              "h-full w-full",
              node.containThumb ? "object-contain" : "object-cover",
            )}
            onLoad={(e) =>
              setDims(
                `${e.currentTarget.naturalWidth}×${e.currentTarget.naturalHeight}`
              )
            }
          />
        ) : (
          <span className="flex h-full w-full items-center justify-center text-muted-foreground">
            <FallbackIcon className="h-5 w-5" />
          </span>
        )}
        {expandable && (
          <MediaHoverButton
            className="left-2 top-2"
            label={t("results.canvas.expand")}
            onClick={() => onExpandMedia(node.id)}
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </MediaHoverButton>
        )}
        {node.videoUrl && (
          <MediaHoverButton
            className="right-2 top-2"
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
      </div>
      {showBar && (
        <div className="flex h-[44px] shrink-0 items-start justify-center pt-2">
          <MediaToolbar
            info={info}
            actions={[
              {
                action: "download",
                Icon: Download,
                label: t("results.canvas.download"),
              },
              { action: "delete", Icon: Trash2, label: t("common.delete") },
            ]}
            menuItems={[
              ...(expandable
                ? [{ action: "open", label: t("results.canvas.open") }]
                : []),
              { action: "reprocess", label: t("results.canvas.reprocess") },
            ]}
            moreLabel={t("results.canvas.more")}
            onAction={handleBarAction}
          />
        </div>
      )}
    </div>
  )
}

function StepCard({ node }: { node: FlowNode }) {
  return (
    <div className="flex h-full w-full items-center gap-2 rounded-md bg-card px-2.5 py-1.5 ring-foreground/10 ring-1">
      <span className="h-5 w-5 shrink-0 rounded-full bg-muted" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs leading-snug">{node.label}</p>
        {node.detail && (
          <p className="truncate text-[10px] leading-tight text-muted-foreground">{node.detail}</p>
        )}
      </div>
    </div>
  )
}

/** The document node's card (ADR-057 — the task book, the FLORA text-node
 * form). Parked on the same dot grid as the dock, so it takes the
 * dock-surface frost (the canvas's dots read through) + the hairline,
 * never a shadow: the produced text IS the body copy. Read-only on this
 * surface — changing it happens in chat. No factsbar, no program region. */
function DocumentCard({ node }: { node: FlowNode }) {
  return (
    <div className="flex h-full w-full flex-col">
      <NodeCaption label={node.label} Icon={FileText} />
      <div className="dock-surface min-h-0 flex-1 rounded-xl p-4 ring-foreground/10 ring-1">
        {node.spec?.text ? (
          <p className="line-clamp-6 text-xs leading-relaxed">{node.spec.text}</p>
        ) : (
          <p className="text-xs leading-relaxed text-muted-foreground">{node.detail}</p>
        )}
      </div>
    </div>
  )
}

/** The hover prompt 框 (ADR-051 F): one frosted bar revealed over the card's
 * bottom on hover, prefilled with the node's OWN program (spec.prompt —
 * server-composed at fill time). Editing it into any revision ask and
 * sending rides the chat revision channel with the displayed product
 * pinned as focus (prohibition #1: zero new execution channel — never an
 * in-place rerun button). Hover-only reveal: touch keeps the ⋯ menu's
 * focus path. K4 replaces this with the card-face direct edit + the
 * pricing confirmation. */
function ReviseHoverBar({
  specPrompt,
  group,
  onRevise,
}: {
  specPrompt?: string | null
  /** The reveal group's name ("product" / "text") — matches the card root's
   * `group/{name}` class. */
  group: string
  onRevise?: (text: string) => void
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState(specPrompt ?? "")
  // Re-seed when the displayed product changes (a pager flip / a refetch).
  useEffect(() => setDraft(specPrompt ?? ""), [specPrompt])
  if (!onRevise) return null
  const send = () => {
    const text = draft.trim()
    if (!text) return
    onRevise(text)
    setDraft(specPrompt ?? "")
  }
  return (
    <div
      className={cn(
        "pointer-events-none absolute inset-x-2 bottom-2 z-10 opacity-0 transition-opacity",
        `group-hover/${group}:opacity-100`,
      )}
    >
      <div className="dock-surface pointer-events-auto flex items-center gap-1 rounded-lg p-1 ring-1 ring-foreground/10">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.nativeEvent.isComposing) {
              e.preventDefault()
              send()
            }
          }}
          onClick={(e) => e.stopPropagation()}
          placeholder={t("results.canvas.revisePlaceholder")}
          aria-label={t("results.canvas.reviseTooltip")}
          className="h-7 min-w-0 flex-1 bg-transparent px-2 text-xs outline-none placeholder:text-muted-foreground"
        />
        <button
          type="button"
          title={t("results.canvas.reviseSend")}
          aria-label={t("results.canvas.reviseSend")}
          onClick={(e) => {
            e.stopPropagation()
            send()
          }}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-foreground text-background transition-opacity hover:opacity-80"
        >
          <ArrowUp className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

/** Multi-item outputs (quotes = N cards, carousel = N slides): the display
 * variants of ONE output row — the hover switcher flips the main display
 * (items without their own media render as text tiles). */
function outputVariants(output: Output): { label: string; sub?: string; thumbUrl?: string | null }[] {
  const thumbUrl = toAbsoluteUrl(
    output.files.image ?? output.publishing.cover_image_url ?? null,
  )
  const quotes = output.type === "quotes" ? ((output.payload.quotes as { quote: string; attribution?: string }[]) ?? []) : []
  const slides = output.type === "carousel" ? ((output.payload.slides as { title: string; body?: string }[]) ?? []) : []
  if (quotes.length > 1) {
    return quotes.map((q, qi) => ({
      label: q.quote,
      sub: q.attribution,
      thumbUrl: qi === 0 ? thumbUrl : null,
    }))
  }
  if (slides.length > 1) {
    return slides.map((s) => ({ label: s.title, sub: s.body ?? undefined, thumbUrl: null }))
  }
  return []
}

/** The media product region (done state, media-carrying product): the
 * clip's MP4 PLAYS INLINE (muted ambient loop, recipe-gallery 同款); hover
 * affordances: expand top-LEFT, sound top-RIGHT; score / quality ride the
 * media's bottom corners as badges; a rendering clip projects its state in
 * place as the BrandLoader (never a spinner, never a status line). */
function MediaProductRegion({
  node,
  output,
  topClipScore,
  onExpandMedia,
}: {
  node: FlowNode
  output: Output
  topClipScore?: number
  onExpandMedia?: (nodeId: string, outputId?: string) => void
}) {
  const { t } = useTranslation()
  const score = typeof output.score?.value === "number" ? output.score.value : null
  const topPick = !!topClipScore && topClipScore > 0 && score === topClipScore
  // 质检裁决 (期 3): needs_human rides the media's bottom-right corner —
  // non-blocking, so the badge is quiet chrome with the failing checks in
  // its tooltip (成功安静, passed renders nothing).
  const qualityFailed =
    output.quality?.status === "needs_human"
      ? (output.quality.checks ?? []).filter((c) => c.ok === false)
      : []
  const hasVideo = !!output.files.video
  const videoUrl = hasVideo ? toAbsoluteUrl(output.files.video) : null
  const [muted, setMuted] = useState(true)
  const clipAspect = output.aspect ?? null
  const thumbPx = (clipAspect && PRODUCT_THUMB_PX[clipAspect]) || PRODUCT_THUMB_DEFAULT_PX
  // Render state projects onto the card in place: a failed render is the
  // CARD turning failed — never a separate node hanging off the graph; the
  // retry channel is the chat dock, so no toolbar action.
  const renderFailed = output.type === "clip" && output.render_status === "failed"
  const renderActive =
    output.type === "clip" &&
    !hasVideo &&
    (output.render_status === "pending" || output.render_status === "rendering")

  const variants = outputVariants(output)
  const [variantIndex, setVariantIndex] = useState(0)
  const activeVariant = variants[variantIndex] ?? variants[0]
  const shownThumbUrl = toAbsoluteUrl(
    output.files.image ?? output.publishing.cover_image_url ?? null,
  )
  const mediaThumb = variants.length > 0 ? (activeVariant?.thumbUrl ?? null) : shownThumbUrl

  return (
    <div
      data-tour={node.tourTargets ? "results-video" : undefined}
      className={cn("group/media relative shrink-0", clipAspect ? "bg-black" : "bg-muted")}
      style={{ height: thumbPx }}
    >
      {/* Variant switcher (the reference canvas's hover group): fades in at
          the region's top center on hover; each tile is one produced item.
          Always on under (hover: none) — touch has no reveal gesture. */}
      {variants.length > 1 && (
        <div className="pointer-events-none absolute -top-1 left-1/2 z-10 -translate-x-1/2 opacity-0 transition-opacity group-hover/media:opacity-100 [@media(hover:none)]:opacity-100">
          <div className="dock-surface pointer-events-auto flex items-center gap-1 rounded-xl p-1.5 ring-1 ring-foreground/10">
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
                  "flex h-8 w-8 items-center justify-center overflow-hidden rounded-md text-[11px] font-medium transition-opacity",
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
      ) : videoUrl ? (
        <video
          src={videoUrl}
          poster={mediaThumb ?? undefined}
          aria-label={node.label}
          className="pointer-events-none h-full w-full object-contain"
          muted={muted}
          loop
          playsInline
          autoPlay
          preload="metadata"
          disablePictureInPicture
        />
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
            <TriangleAlert className="h-5 w-5 text-destructive" />
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
      {/* Media meta badges: the score rides the bottom-left corner; the
          top corners belong to the hover affordances (expand left, sound
          right). The duration is NOT a badge — it lives in the factsbar
          below the card (2026-08-17 二轮走查拍板). */}
      {score !== null && !renderFailed && (
        <span
          data-tour={node.tourTargets ? "results-score" : undefined}
          title={output.score?.reason ?? undefined}
          className={cn(
            "absolute bottom-2 left-2 rounded px-1.5 py-0.5 text-[10px] font-medium",
            topPick ? "bg-primary text-primary-foreground" : "bg-black/70 text-white",
          )}
        >
          {topPick ? `${t("results.topPick")} · ${score}` : score}
        </span>
      )}
      {qualityFailed.length > 0 && !renderFailed && (
        <span
          title={qualityFailed
            .map(
              (c) =>
                `${t(`qualityChecks.${c.id}`, { defaultValue: c.id })}: ${c.detail}`,
            )
            .join("\n")}
          className="absolute bottom-2 right-2 flex items-center gap-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-white"
        >
          <TriangleAlert className="h-3 w-3" />
          {t("results.qualityNeedsReview")}
        </span>
      )}
      {(hasVideo || shownThumbUrl) && !renderActive && onExpandMedia ? (
        <MediaHoverButton
          className="left-2 top-2"
          label={t("results.canvas.expand")}
          onClick={() => onExpandMedia(node.id, output.id)}
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </MediaHoverButton>
      ) : null}
      {videoUrl && (
        <MediaHoverButton
          className="right-2 top-2"
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
    </div>
  )
}

/** The text product region (done state, post / article): the generated text
 * rendered inside the card (these types have no baked image/video) — the
 * card itself is the readable text card (Gamma/Tome-style). The product's
 * own content stays directly editable in place (a product-level text edit —
 * 改字免费即时, persisted via PUT /outputs; never a program change). */
function TextProductRegion({
  output,
  tourTargets,
}: {
  output: Output
  tourTargets?: boolean
}) {
  const { t } = useTranslation()
  const title = output.publishing.title ?? (output.payload.title as string | undefined) ?? null
  const body = (output.payload.content as string | undefined) ?? ""
  const hashtags =
    (output.publishing.hashtags as string[] | undefined) ??
    (output.payload.hashtags as string[] | undefined) ??
    []
  const clipped = hashtags.length > 3 ? [...hashtags.slice(0, 3), "..."] : hashtags

  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(body)
  const [saving, setSaving] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    setDraft(body)
  }, [body])

  useEffect(() => {
    if (editing && textareaRef.current) {
      textareaRef.current.focus()
      const len = textareaRef.current.value.length
      textareaRef.current.setSelectionRange(len, len)
    }
  }, [editing])

  // React Flow's canvas zoom/pan attaches native wheel listeners to the pane,
  // so a React synthetic stopPropagation is not enough — we must stop the
  // native event from bubbling up out of the textarea while editing.
  useEffect(() => {
    const el = textareaRef.current
    if (!el || !editing) return
    const stopWheel = (e: WheelEvent) => {
      e.stopPropagation()
    }
    el.addEventListener("wheel", stopWheel, { passive: true })
    return () => el.removeEventListener("wheel", stopWheel)
  }, [editing])

  const save = async () => {
    if (draft === body) {
      setEditing(false)
      return
    }
    setSaving(true)
    try {
      const nextPayload: Record<string, unknown> = { ...(output.payload ?? {}) }
      if (output.type === "article") {
        nextPayload.title = title ?? ""
        nextPayload.content = draft
      } else {
        nextPayload.content = draft
      }
      const nextPublishing: Record<string, unknown> = { ...(output.publishing ?? {}) }
      if (title !== null) nextPublishing.title = title
      if (hashtags.length > 0) nextPublishing.hashtags = hashtags
      const res = await apiPut(`/api/v1/outputs/${output.id}`, {
        payload: nextPayload,
        publishing: nextPublishing,
      })
      if (res.ok) {
        // Optimistically update the in-memory output so the canvas reflects
        // the edit before the next poll/refetch.
        if (output.type === "article") {
          output.payload.title = title ?? ""
        }
        output.payload.content = draft
      } else {
        setDraft(body)
      }
    } catch {
      setDraft(body)
      toast.error(t("common.requestFailed"))
    } finally {
      setSaving(false)
      setEditing(false)
    }
  }

  const contentClass =
    "h-full w-full overflow-y-auto rounded-lg px-3 py-3 text-left text-xs leading-relaxed thin-scroll"

  return (
    <div
      className="flex min-h-0 flex-1 flex-col"
      data-tour={tourTargets ? "results-video" : undefined}
      onClick={(e) => {
        // Editing the text area should not select the node — the canvas's
        // onNodeClick handler would otherwise steal focus from the textarea.
        if (editing) e.stopPropagation()
      }}
    >
      {editing ? (
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={save}
          onWheel={(e) => {
            e.stopPropagation()
            e.preventDefault()
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault()
              setDraft(body)
              setEditing(false)
            } else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
              e.preventDefault()
              save()
            }
          }}
          disabled={saving}
          className={cn(
            contentClass,
            "resize-none bg-transparent outline-none thin-scroll overscroll-contain",
          )}
        />
      ) : (
        <button
          type="button"
          onClick={(e) => {
            // Entering inline edit is NOT the node-select gesture — a
            // select opens the TextDetailModal reader (2026-09-06); same
            // stopPropagation contract as the toolbar buttons.
            e.stopPropagation()
            setEditing(true)
          }}
          className={cn(contentClass, "cursor-text")}
        >
          {title ? (
            <p className="mb-1 line-clamp-1 text-sm font-medium leading-snug">{title}</p>
          ) : null}
          <p
            className={cn(
              "whitespace-pre-wrap",
              title ? "line-clamp-[11]" : "line-clamp-[12]",
            )}
          >
            {body}
          </p>
          {clipped.length > 0 ? (
            <p className="mt-2 line-clamp-1 text-[10px] text-muted-foreground">
              {clipped.map((h) => `#${h}`).join(" ")}
            </p>
          ) : null}
        </button>
      )}
    </div>
  )
}

/** The draft/quiet body (ADR-057 §5 — 状态原地表达): the un-run node is a
 * dashed empty region reading its own quotation (「运行后生成 · 约 N 积分」);
 * queued reads 排队中 without the price (already committed); a landed-empty
 * node (research — its product is internal) reads its summary line in the
 * same body. */
function QuietBody({ node }: { node: FlowNode }) {
  const { t } = useTranslation()
  const est = node.estimateCredits
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center rounded-lg border border-dashed border-foreground/15 text-center">
      {node.status === "draft" ? (
        <span className="flex flex-col items-center gap-1.5 p-3">
          <span className="text-[11px] text-muted-foreground">
            {t("results.canvas.draftBody")}
          </span>
          {est ? (
            <span className="rounded bg-inset px-2 py-0.5 text-[10px] tabular-nums text-muted-foreground">
              {est[0] === est[1]
                ? t("results.canvas.estimateSingle", { count: est[0] })
                : t("results.canvas.estimateRange", { low: est[0], high: est[1] })}
            </span>
          ) : null}
        </span>
      ) : node.status === "queued" ? (
        <span className="text-[11px] text-muted-foreground">
          {t("results.canvas.queued")}
        </span>
      ) : node.status === "skipped" ? (
        <span className="text-[11px] text-muted-foreground">
          {t("results.canvas.skipped")}
        </span>
      ) : node.status === "failed" ? (
        <span className="px-3 text-[11px] leading-snug text-destructive">
          {t("results.canvas.runFailed")}
        </span>
      ) : (
        // done with no visible product (research): the summary line is the
        // self-evident content.
        <span className="line-clamp-3 px-3 text-[11px] leading-snug text-muted-foreground">
          {node.spec?.summary ?? node.label}
        </span>
      )}
    </div>
  )
}

/** The program region (ADR-057 §5 — the card-face spec): generator/agent
 * nodes read their prompt — and on a node that has products (done / stale),
 * the region is DIRECTLY EDITABLE (K4, the prototype's scene-C anatomy):
 * click drafts in place, Enter sends, Esc cancels. Sending does NOT touch
 * the graph — it lifts the new program to the surface's pricing
 * confirmation (锚定子图 + 估价), and only the confirmed turn rides the
 * chat channel (零旁路). Processor nodes read their params as fact chips
 * (no LLM prompt — deterministic 工序, never editable here). */
function ProgramRegion({
  node,
  editable,
  onPromptEdit,
}: {
  node: FlowNode
  editable?: boolean
  onPromptEdit?: (nodeId: string, text: string) => void
}) {
  const { t } = useTranslation()
  const prompt = node.spec?.prompt
  const params = node.spec?.params ?? null
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(prompt ?? "")
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!editing) setDraft(prompt ?? "")
  }, [prompt, editing])

  useEffect(() => {
    if (editing && textareaRef.current) {
      textareaRef.current.focus()
      const len = textareaRef.current.value.length
      textareaRef.current.setSelectionRange(len, len)
    }
  }, [editing])

  // Same canvas-wheel isolation as the text product's inline edit: React
  // Flow's zoom listens natively on the pane, so the textarea stops the
  // native event while editing.
  useEffect(() => {
    const el = textareaRef.current
    if (!el || !editing) return
    const stopWheel = (e: WheelEvent) => {
      e.stopPropagation()
    }
    el.addEventListener("wheel", stopWheel, { passive: true })
    return () => el.removeEventListener("wheel", stopWheel)
  }, [editing])

  if (node.kind === "processor") {
    const chips: string[] = []
    if (params) {
      const lang = params.target_language as string | undefined
      if (lang) chips.push(t(`languages.${lang}`, { defaultValue: lang }))
      if (typeof params.aspect === "string" && params.aspect) chips.push(params.aspect)
      if (typeof params.mood === "string" && params.mood) chips.push(params.mood)
    }
    if (chips.length === 0) return null
    return (
      <div className="flex shrink-0 flex-wrap items-center gap-1 px-3 py-2">
        {chips.map((chip, i) => (
          <span
            key={i}
            className="rounded bg-inset px-1.5 py-0.5 text-[10px] whitespace-nowrap text-muted-foreground"
          >
            {chip}
          </span>
        ))}
      </div>
    )
  }
  if (!prompt && !editing) return null

  const send = () => {
    const text = draft.trim()
    setEditing(false)
    if (!text || text === (prompt ?? "").trim()) return
    onPromptEdit?.(node.id, text)
  }

  return (
    <div
      className={cn(
        "shrink-0 px-3 py-2 transition-colors",
        editable && !editing && "cursor-text hover:bg-accent/50",
      )}
      onClick={(e) => {
        if (!editable || editing) return
        // Entering the draft is NOT the node-select gesture.
        e.stopPropagation()
        setEditing(true)
      }}
    >
      <p className="text-meta text-[9px]">
        {editing ? t("results.canvas.promptEditing") : t("results.canvas.promptLabel")}
      </p>
      {editing ? (
        <div className="mt-0.5">
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                send()
              } else if (e.key === "Escape") {
                e.preventDefault()
                setDraft(prompt ?? "")
                setEditing(false)
              }
            }}
            onBlur={send}
            rows={3}
            className="w-full resize-none bg-transparent text-xs leading-snug outline-none"
          />
          <div className="mt-1 flex items-center justify-end">
            <button
              type="button"
              title={t("results.canvas.reviseSend")}
              aria-label={t("results.canvas.reviseSend")}
              onClick={(e) => {
                e.stopPropagation()
                send()
              }}
              className="flex h-6 w-6 items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-80"
            >
              <ArrowUp className="h-3 w-3" />
            </button>
          </div>
        </div>
      ) : (
        <p title={prompt ?? undefined} className="mt-0.5 line-clamp-3 text-xs leading-snug">
          {prompt}
        </p>
      )}
    </div>
  )
}

/** The generator / processor / agent card (ADR-057 §4/§5/§6 — one anatomy,
 * state expressed in place): caption (right slot ALWAYS empty) / product
 * region (draft dashed estimate · running wipe · done self-evident ·
 * failed in-card red) / program region / factsbar 外置 (runtime facts +
 * actions + the version pager). */
function GraphCard({
  node,
  selected,
  onOutputAction,
  onExpandMedia,
  onRevise,
  onDisplayChange,
  onPromptEdit,
}: {
  node: FlowNode
  selected: boolean
  onOutputAction?: FlowCardData["onOutputAction"]
  onExpandMedia?: FlowCardData["onExpandMedia"]
  onRevise?: FlowCardData["onRevise"]
  onDisplayChange?: FlowCardData["onDisplayChange"]
  onPromptEdit?: FlowCardData["onPromptEdit"]
}) {
  const { t } = useTranslation()
  const outputs = node.outputs ?? []
  // The pager flips the display AND the action target among the node's
  // products; displayId survives refetches (ids are stable).
  const [displayId, setDisplayId] = useState<string | null>(null)
  const output = (displayId ? outputs.find((o) => o.id === displayId) : null) ?? outputs[0]
  // The surface tracks the shown member — a node click selects what the
  // user is LOOKING at (mount + flip both report).
  useEffect(() => {
    if (output) onDisplayChange?.(node.id, output.id)
  }, [node.id, output, onDisplayChange])
  const shownIdx = Math.max(0, outputs.findIndex((o) => o.id === output?.id))
  const isText = !!output && (output.type === "post" || output.type === "article")
  // The caption's type glyph: the displayed product's type; an un-run node
  // reads its own slot's type (the promise's shape — clips/post/quotes/…).
  const slotType = (node.spec?.params?.slot as { type?: string } | undefined)?.type
  const slotIconKey = slotType === "clips" ? "clip" : slotType
  const TypeIcon = output
    ? (PRODUCT_TYPE_ICON[output.type] ?? Clapperboard)
    : (PRODUCT_TYPE_ICON[slotIconKey ?? ""] ?? FileText)

  // ── factsbar ──────────────────────────────────────────────────────────
  const info: string[] = []
  if (output) {
    if (output.language) {
      info.push(t(`languages.${output.language}`, { defaultValue: output.language }))
    }
    const clipAspect = output.aspect ?? null
    if (clipAspect && clipAspect !== "original") info.push(clipAspect)
    const duration = output.type === "clip" ? ((output.payload.duration as number | undefined) ?? null) : null
    if (duration !== null && duration > 0) info.push(`${duration}s`)
    const models = (output.model_facts ?? []).map((f) => f.model)
    info.push(...models)
  } else {
    // Un-run / quiet node: the params are the facts it already knows.
    const params = node.spec?.params
    const lang = params?.target_language as string | undefined
    if (lang) info.push(t(`languages.${lang}`, { defaultValue: lang }))
    if (typeof params?.aspect === "string" && params.aspect) info.push(params.aspect)
  }

  const hasVideo = !!output?.files.video
  const shownThumbUrl = output
    ? toAbsoluteUrl(output.files.image ?? output.publishing.cover_image_url ?? null)
    : null
  const renderActive =
    !!output &&
    output.type === "clip" &&
    !hasVideo &&
    (output.render_status === "pending" || output.render_status === "rendering")
  const canDownload = !output
    ? false
    : output.type === "clip"
      ? hasVideo
      : output.type === "quotes" || output.type === "quote_frame"
        ? !!output.files.image
        : true
  const actions: { action: FlowOutputAction; Icon: typeof Download; label: string }[] = []
  if (output && !renderActive) {
    if (canDownload) {
      actions.push({
        action: "download",
        Icon: Download,
        label: t("results.canvas.download"),
      })
    }
    actions.push({ action: "delete", Icon: Trash2, label: t("common.delete") })
  }
  const menuItems: { action: string; label: string }[] = output
    ? [
        ...(output.type === "clip" && hasVideo
          ? [{ action: "publish", label: t("results.canvas.publish") }]
          : []),
        ...(hasVideo || shownThumbUrl
          ? [{ action: "open", label: t("results.canvas.open") }]
          : []),
        { action: "focus", label: t("results.canvas.focusNode") },
      ]
    : []
  const handleBarAction = (action: string) => {
    if (!output) return
    if (action === "open" && !(output.type === "clip" && hasVideo)) {
      onExpandMedia?.(node.id, output.id)
      return
    }
    onOutputAction?.(output.id, action as FlowOutputAction)
  }

  const running = node.status === "running"
  const failed = node.status === "failed"
  const renderFailed =
    !!output && output.type === "clip" && output.render_status === "failed"

  return (
    <div className="group/product relative flex h-full w-full flex-col">
      <NodeCaption label={node.label} Icon={TypeIcon} />
      <div
        className={cn(
          "relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg bg-card ring-1",
          selected ? "ring-2 ring-foreground/40" : "ring-foreground/10",
        )}
      >
        {/* The FLORA wipe (CSS 封顶 96% 律继承 — never a fraction claim):
            the one living signal of a filling node. */}
        {running && <span aria-hidden className="node-fill-wipe" />}
        {output ? (
          isText ? (
            <TextProductRegion output={output} tourTargets={node.tourTargets} />
          ) : (
            <MediaProductRegion
              node={node}
              output={output}
              topClipScore={node.topClipScore}
              onExpandMedia={onExpandMedia}
            />
          )
        ) : (
          <div className="flex min-h-0 flex-1 flex-col p-3">
            <QuietBody node={node} />
          </div>
        )}
        {failed && output ? (
          <p className="shrink-0 px-3 py-1.5 text-[11px] leading-snug text-destructive">
            {t("results.canvas.runFailed")}
          </p>
        ) : null}
        {!failed && renderFailed ? (
          <p className="shrink-0 px-3 py-1.5 text-[11px] leading-snug text-destructive">
            {t("results.canvas.renderFailed")}
          </p>
        ) : null}
        <ProgramRegion
          node={node}
          // 直改闸门 (K4): only a settled node with products edits in place
          // (the confirmation pins its product as the revision focus);
          // a queued/running node is executing its program (the wiring op
          // rejects it too), a draft has no product to pin (K5 owns it).
          editable={
            (node.kind === "generator" || node.kind === "agent") &&
            outputs.length > 0 &&
            node.status !== "queued" &&
            node.status !== "running"
          }
          onPromptEdit={onPromptEdit}
        />
        {output ? (
          <ReviseHoverBar
            specPrompt={node.spec?.prompt ?? output.spec_prompt}
            group="product"
            onRevise={onRevise ? (text) => onRevise(output.id, text) : undefined}
          />
        ) : null}
      </div>

      {/* The factsbar band under the card (外置律): runtime facts + actions
          + the version pager — reserved even while quiet, geometry never
          shifts. The stale badge rides the bar's left end (可重跑 — the
          program moved after the product landed). */}
      <div
        data-tour={node.tourTargets ? "results-menu" : undefined}
        className="flex h-[44px] shrink-0 items-start justify-center gap-2 pt-2"
      >
        {outputs.length > 1 && (
          <VersionPager
            current={shownIdx}
            total={outputs.length}
            onFlip={(delta) => {
              const next = outputs[shownIdx + delta]
              if (next) setDisplayId(next.id === outputs[0]?.id ? null : next.id)
            }}
          />
        )}
        {(info.length > 0 || actions.length > 0 || node.status === "stale") && (
          <MediaToolbar
            info={info}
            actions={actions}
            menuItems={menuItems}
            moreLabel={t("results.canvas.more")}
            badge={node.status === "stale" ? t("results.canvas.stale") : null}
            onAction={handleBarAction}
          />
        )}
      </div>
    </div>
  )
}

/** The port-law handles (ADR-057): visible typed ports — in = the
 * consumption region's bottom-left corner, stacked up; out = the
 * production region's top-right corner, stacked down. Port colors match
 * their flow (ctx = the dashed context port). Untyped surfaces (the recipe
 * 说明书) keep the legacy invisible pair. */
function NodePorts({ node, ports }: { node: FlowNode; ports?: { in: GraphEdgeType[]; out: GraphEdgeType[] } }) {
  if (!ports) {
    return (
      <>
        <Handle type="target" position={Position.Left} className="!h-0 !w-0 !opacity-0" />
        <Handle type="source" position={Position.Right} className="!h-0 !w-0 !opacity-0" />
      </>
    )
  }
  // The consumption region sits above the factsbar band (document has no
  // band — its region is the card bottom); production starts under the
  // caption band.
  const inBase = node.kind === "document" ? 14 : 58
  const outBase = 38
  return (
    <>
      {ports.in.map((type, i) => (
        <Handle
          key={`in:${type}`}
          id={`in:${type}`}
          type="target"
          position={Position.Left}
          className={cn("flow-port", `flow-port-${type}`)}
          style={{ top: "auto", bottom: inBase + i * 22 }}
        />
      ))}
      {ports.out.map((type, i) => (
        <Handle
          key={`out:${type}`}
          id={`out:${type}`}
          type="source"
          position={Position.Right}
          className={cn("flow-port", `flow-port-${type}`)}
          style={{ top: outBase + i * 22 }}
        />
      ))}
    </>
  )
}

/** The one node card renderer — recipe skins (asset/output thumbs, step
 * pill) and the ADR-057 graph skins (asset / document / graph card).
 * Birth choreography: `flow-node-born` keyframe staggered by `bornIndex`
 * (the real compile order, replayed slowly — ADR-036 补记 3). */
export function FlowNodeCard({ data }: NodeProps<FlowCardNode>) {
  const { node, bornIndex, selected, ports, onOutputAction, onExpandMedia, onAssetAction, onRevise, onDisplayChange, onPromptEdit } = data
  // Latch the birth frame: the surface drops bornIndex on the next commit
  // (its seen-set absorbs the id), and a follow-up SSE tick can land inside
  // the 420ms keyframe — the class must outlive the animation. A class that
  // stays continuously applied never replays; a remount (the node left the
  // graph and returned) starts a fresh latch.
  const bornLatchRef = useRef<number | undefined>(undefined)
  if (bornIndex !== undefined) bornLatchRef.current = bornIndex
  const born = bornLatchRef.current
  const isGraphCard =
    node.kind === "generator" || node.kind === "processor" || node.kind === "agent"
  return (
    <div
      className={cn(
        "h-full w-full cursor-pointer rounded-md text-foreground transition-colors",
        // 状态原地表达 (ADR-057 §5): skipped is the one whole-card dim; a
        // filling node keeps its quiet pulse; draft/queued/failed/stale all
        // speak inside the card, never on it.
        node.status === "skipped" && "opacity-40",
        node.status === "running" && "flow-node-running",
        born !== undefined && "flow-node-born",
        selected && !isGraphCard && "rounded-md ring-2 ring-foreground/40",
      )}
      style={born !== undefined ? { animationDelay: `${born * BIRTH_STAGGER_MS}ms` } : undefined}
    >
      <NodePorts node={node} ports={ports} />
      {node.kind === "step" ? (
        <StepCard node={node} />
      ) : node.kind === "document" ? (
        <DocumentCard node={node} />
      ) : isGraphCard ? (
        <GraphCard
          node={node}
          selected={selected}
          onOutputAction={onOutputAction}
          onExpandMedia={onExpandMedia}
          onRevise={onRevise}
          onDisplayChange={onDisplayChange}
          onPromptEdit={onPromptEdit}
        />
      ) : (
        <ThumbCard
          node={node}
          onExpandMedia={onExpandMedia}
          onAssetAction={onAssetAction}
        />
      )}
    </div>
  )
}
