import { Handle, Position, type Node, type NodeProps } from "@xyflow/react"
import { useEffect, useRef, useState } from "react"
import {
  ArrowUp,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clapperboard,
  Download,
  FileText,
  Image as ImageIcon,
  Images,
  Loader2,
  Maximize2,
  Minus,
  MoreHorizontal,
  Newspaper,
  Quote,
  Trash2,
  TriangleAlert,
  Volume2,
  VolumeX,
  Waypoints,
  X,
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

import { BIRTH_STAGGER_MS, PRODUCT_THUMB_DEFAULT_PX, PRODUCT_THUMB_PX } from "./layout"
import type {
  FlowAssetAction,
  FlowAssetInfo,
  FlowNode,
  FlowNodeStatus,
  FlowOutputAction,
} from "./types"

export interface FlowCardData extends Record<string, unknown> {
  node: FlowNode
  /** Reveal index for birth choreography (undefined = render instantly). */
  bornIndex?: number
  selected: boolean
  /** Product-toolbar dispatch (ADR-041 D5) — the surface owns the actions. */
  onOutputAction?: (outputId: string, action: FlowOutputAction) => void
  /** Asset-toolbar dispatch (2026-08-17) — the surface owns asset actions. */
  onAssetAction?: (asset: FlowAssetInfo, action: FlowAssetAction) => void
  /** Media expand dispatch — the surface opens the lightbox for the node.
   * `outputId` overrides the node's own row when the version pager has the
   * card displaying a fork-family sibling (the lightbox must show what the
   * card shows). */
  onExpandMedia?: (nodeId: string, outputId?: string) => void
  /** Revision-turn dispatch (ADR-051 F — hover prompt 框): the edited spec
   * text rides the surface's chat channel with this output pinned as focus.
   * The output id is the DISPLAYED family member's (the revision targets
   * the version the user is looking at). */
  onRevise?: (outputId: string, text: string) => void
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

/** The corner-info band above a media node (2026-08-17 走查拍板, Lovart
 * 解剖): ALWAYS the node's type icon + type name at the top-LEFT, and the
 * right slot stays EMPTY — every fact (language / duration / resolution…)
 * lives in the toolbar under the card instead. The band's height is part of
 * the node size budget (layout.ts), never an overlay. */
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

/** The media node's toolbar (2026-08-17 走查拍板, Lovart 解剖; 2026-08-19
 * 做薄): one frosted bar (dock-surface + hairline, never bare icons) —
 * media facts on the left (filename / duration / resolution / language /
 * aspect…), a hairline divider, then the actions; node business (publish /
 * open / focus / reprocess) lives in the ⋯ menu at the right end (a
 * floating layer, frosted by the shared DropdownMenu chrome). The bar hugs
 * its content — width is NOT capped by the node and facts NEVER ellipsize
 * (2026-08-17 二轮走查拍板): it centers under the card and overhangs
 * symmetrically when the facts are long. Slimmed 08-19: 36px bar in a 44px
 * band (was 44/56) — hover-化否决不变（小白可发现性优先），只做薄。 */
function MediaToolbar({
  info,
  actions,
  menuItems,
  moreLabel,
  onAction,
}: {
  info: string[]
  actions: { action: string; Icon: typeof Download; label: string }[]
  menuItems: { action: string; label: string }[]
  /** aria/title for the ⋯ trigger (i18n from the caller). */
  moreLabel: string
  onAction: (action: string) => void
}) {
  return (
    <div className="dock-surface flex items-center gap-1 rounded-lg p-1 ring-1 ring-foreground/10">
      {info.length > 0 && (
        <span className="flex items-center gap-2 pl-1.5 pr-1 text-[11px] whitespace-nowrap text-muted-foreground">
          {info.map((s, i) => (
            <span key={i}>{s}</span>
          ))}
        </span>
      )}
      {info.length > 0 && (actions.length > 0 || menuItems.length > 0) && (
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
        {node.status && node.status !== "pending" && (
          <span className="absolute right-2 top-2">
            <StatusBadge status={node.status} />
          </span>
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
      {node.status ? (
        <StatusBadge status={node.status} />
      ) : (
        <span className="h-5 w-5 shrink-0 rounded-full bg-muted" />
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs leading-snug">{node.label}</p>
        {node.detail && (
          <p className="truncate text-[10px] leading-tight text-muted-foreground">{node.detail}</p>
        )}
      </div>
    </div>
  )
}

/** The 过程脊 group node (ADR-041 D6): a thin tunnel, not a main node.
 * Process verbs fold here; it never carries a toolbar or status badge. */
function SpineCard({ node }: { node: FlowNode }) {
  return (
    <div className="flex h-full w-full items-center justify-center gap-1.5 rounded-full bg-muted px-3 text-xs text-muted-foreground ring-1 ring-foreground/5">
      <Waypoints className="h-3 w-3 shrink-0" />
      <span className="truncate">{node.detail}</span>
      {node.expanded ? (
        <ChevronDown className="h-3 w-3 shrink-0" />
      ) : (
        <ChevronRight className="h-3 w-3 shrink-0" />
      )}
    </div>
  )
}

/** The artifact node's card (D6 修订 — the render unit is the intervenable
 * artifact; 2026-08-19 名词节点收窄后 = the 任务书 glass text node, the
 * FLORA text-node form). Parked on the same dot grid as the dock, so it
 * takes the dock-surface frost (the canvas's dots read through) + the
 * hairline, never a shadow. Three-section anatomy (the Lovart anatomy,
 * interaction NOT copied): the type + status up top, the produced thing as
 * the body copy, the spec line at the bottom — read-only; changing it
 * happens in chat via the @workflow_step mention, never on the card. No
 * toolbar (D5: process nodes never carry one). */
function ArtifactCard({ node }: { node: FlowNode }) {
  return (
    <div className="dock-surface flex h-full w-full flex-col gap-2 rounded-xl p-4 ring-foreground/10 ring-1">
      <div className="flex items-center justify-between gap-2">
        <p className="text-meta text-[11px]">{node.label}</p>
        {/* Plan 是任务承诺，不是执行步骤，不显示完成态 icon (ADR-041 D6)。 */}
        {node.artifact !== "plan" && node.status && node.status !== "pending" && (
          <StatusBadge status={node.status} />
        )}
      </div>
      {node.body && (
        <p className="line-clamp-6 text-xs leading-relaxed">{node.body}</p>
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
  quote_frame: ImageIcon,
  carousel: Images,
  article: Newspaper,
}

function TextProductCard({
  node,
  selected,
  onOutputAction,
  onRevise,
}: {
  node: FlowNode
  selected: boolean
  onOutputAction?: FlowCardData["onOutputAction"]
  onRevise?: FlowCardData["onRevise"]
}) {
  const { t } = useTranslation()
  const output = node.output
  const tc = node.textContent
  const title = tc?.title ?? null
  const body = tc?.body ?? ""
  const hashtags = tc?.hashtags ?? []
  const clipped = hashtags.length > 3 ? [...hashtags.slice(0, 3), "..."] : hashtags
  const typeIcon = output ? PRODUCT_TYPE_ICON[output.type] ?? FileText : FileText
  const actions: { action: FlowOutputAction; Icon: typeof Download; label: string }[] = [
    { action: "download", Icon: Download, label: t("results.canvas.download") },
    { action: "delete", Icon: Trash2, label: t("common.delete") },
  ]
  const menuItems: { action: string; label: string }[] = [
    { action: "open", label: t("results.canvas.open") },
    { action: "focus", label: t("results.canvas.focusNode") },
  ]
  const handleBarAction = (action: string) => {
    if (output) onOutputAction?.(output.id, action as FlowOutputAction)
  }

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
    if (!output || draft === body) {
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

  const cancel = () => {
    setDraft(body)
    setEditing(false)
  }

  const handleRootClick = (e: React.MouseEvent) => {
    // Editing the text area should not select the node — the canvas's
    // onNodeClick handler would otherwise steal focus from the textarea.
    if (editing) e.stopPropagation()
  }

  const handleWheel = (e: React.WheelEvent) => {
    // Let the textarea scroll itself; don't bubble to the canvas zoom/pan.
    e.stopPropagation()
    e.preventDefault()
  }

  const contentClass =
    "h-full w-full overflow-y-auto rounded-lg px-3 py-3 text-left text-xs leading-relaxed"

  return (
    <div className="group/text relative flex h-full w-full flex-col" onClick={handleRootClick}>
      <NodeCaption label={node.label} Icon={typeIcon} />
      <div
        className={cn(
          "relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg bg-card ring-1",
          selected ? "ring-2 ring-foreground/40" : "ring-foreground/10",
        )}
      >
        {editing ? (
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={save}
            onWheel={handleWheel}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault()
                cancel()
              } else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                e.preventDefault()
                save()
              }
            }}
            disabled={saving}
            className={cn(
              contentClass,
              "resize-none bg-transparent outline-none",
            )}
            style={{ scrollbarWidth: "thin", overscrollBehavior: "contain" }}
          />
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className={cn(contentClass, "cursor-text")}
            style={{ scrollbarWidth: "thin" }}
          >
            {title ? (
              <p className="mb-1 line-clamp-1 text-sm font-medium leading-snug">{title}</p>
            ) : null}
            <p
              className={cn(
                "whitespace-pre-wrap",
                title ? "line-clamp-[6]" : "line-clamp-[7]",
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
        {!editing ? (
          <ReviseHoverBar
            specPrompt={node.specPrompt}
            group="text"
            onRevise={
              onRevise && output ? (text) => onRevise(output.id, text) : undefined
            }
          />
        ) : null}
      </div>
      <div className="flex h-[44px] shrink-0 items-start justify-center pt-2">
        <MediaToolbar
          info={node.detail ? [node.detail] : []}
          actions={actions}
          menuItems={menuItems}
          moreLabel={t("results.canvas.more")}
          onAction={handleBarAction}
        />
      </div>
    </div>
  )
}
/** The hover prompt 框 (ADR-051 F): one frosted bar revealed over the card's
 * bottom on hover, prefilled with the product's OWN spec (server-projected
 * slot/params — never a frontend assembly). Editing it into any revision
 * ask and sending rides the chat revision channel with the product pinned
 * as focus (prohibition #1: zero new execution channel — never an in-place
 * rerun button). Hover-only reveal: touch keeps the ⋯ menu's focus path. */
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
  // Re-seed when the displayed product changes (a family flip / a refetch).
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

/** The output node's product-card skin (ADR-041 D5 — the node IS the card),
 * 2026-08-15 anatomy (figma-style, the reference canvas's node language;
 * 08-16 走查修订):
 *  1. corner-info band ABOVE the card — type + glyph top-left, language
 *     top-right; the card body carries no text chrome.
 *  2. media flush full-bleed inside the card — a clip's MP4 PLAYS INLINE
 *     (muted ambient loop, recipe-gallery 同款); hover affordances: expand
 *     top-LEFT, sound top-RIGHT; score / duration ride the media's bottom
 *     corners as badges; a rendering clip projects its state in place as
 *     the BrandLoader (never a spinner, never a status line).
 *  3. the padded interaction area below the media — the run's prompt only
 *     (spec on the body, read-only; changes happen in chat).
 *  4. the action bar in a reserved band UNDER the card — one frosted bar
 *     (dock-surface + hairline, never bare icons); info (language / real
 *     pixels) left, divider, download / delete, and the ⋯ menu carrying the
 *     node business (publish / open / focus). Graph operations permanently
 *     banned (prohibition #3). The band stays reserved while a render
 *     leaves it quiet — geometry never shifts. */
function ProductCard({
  node,
  selected,
  onOutputAction,
  onExpandMedia,
  onAssetAction,
  onRevise,
}: {
  node: FlowNode
  selected: boolean
  onOutputAction?: FlowCardData["onOutputAction"]
  onExpandMedia?: FlowCardData["onExpandMedia"]
  onAssetAction?: FlowCardData["onAssetAction"]
  onRevise?: FlowCardData["onRevise"]
}) {
  const { t } = useTranslation()
  const nodeOutput = node.output
  // Fork-family pager (ADR-051 F2 — 变体分页): the card's display AND its
  // action target flip among the family's REAL rows (each keeps its own
  // media — a morph version shares its row's current media, so it can never
  // be a pager entry). The node's own row is the default member; `displayId`
  // survives refetches (ids are stable) and a member leaving the visible set
  // falls back to the node's own row.
  const family = node.familyOutputs ?? []
  const [displayId, setDisplayId] = useState<string | null>(null)
  if (!nodeOutput)
    return (
      <ThumbCard
        node={node}
        onExpandMedia={onExpandMedia}
        onAssetAction={onAssetAction}
      />
    )
  const output =
    (displayId ? family.find((o) => o.id === displayId) : null) ?? nodeOutput
  const flipped = output.id !== nodeOutput.id
  const shownIdx = Math.max(0, family.findIndex((o) => o.id === output.id))
  const flip = (delta: number) => {
    const next = family[shownIdx + delta]
    if (next) setDisplayId(next.id === nodeOutput.id ? null : next.id)
  }
  // The SHOWN member's thumb (the node's own thumbUrl only describes its own
  // row) — hoisted above the menu/expand gates that read it.
  const shownThumbUrl = toAbsoluteUrl(
    output.files.image ?? output.publishing.cover_image_url ?? null,
  )

  const score = typeof output.score?.value === "number" ? output.score.value : null
  // 质检裁决 (期 3): needs_human rides the media's bottom-right corner —
  // non-blocking, so the badge is quiet chrome with the failing checks in
  // its tooltip (成功安静, passed renders nothing).
  const qualityFailed =
    output.quality?.status === "needs_human"
      ? (output.quality.checks ?? []).filter((c) => c.ok === false)
      : []
  const duration = output.type === "clip" ? (output.payload.duration ?? null) : null
  const hasVideo = !!output.files.video
  // The clip's MP4 plays inline (recipe-gallery 同款 ambient loop, 2026-08-16
  // 走查拍板) — muted by default (autoplay policy); the hover sound icon
  // flips it, the poster gives an instant first frame.
  const videoUrl = hasVideo ? toAbsoluteUrl(output.files.video) : null
  const [muted, setMuted] = useState(true)
  // Media facts for the toolbar, read off the loaded media (real pixels).
  const [dims, setDims] = useState<string | null>(null)
  // The thumb keeps the product's own frame (2026-08-14 三档画幅 on the
  // canvas): the node's height was already sized for this aspect in runFlow
  // — the strip here mirrors it exactly, and the poster letterboxes (black)
  // rather than crops if its own ratio ever disagrees. The aspect is the
  // SERVER-DERIVED display aspect (产物展示统一: render_spec → payload →
  // null) — quote_frame pins "9:16" on its payload, clips derive from the
  // render spec; never probe client-side when it's set.
  const clipAspect = output.aspect ?? null
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
  // clip without its MP4 yet offers no download (the old menu gated the
  // same way). No play/preview action (2026-08-16 走查拍板): the video
  // plays inline on its own, and the big player is the hover expand.
  const canDownload =
    output.type === "clip"
      ? hasVideo
      : output.type === "quotes" || output.type === "quote_frame"
        ? !!output.files.image
        : true
  const actions: { action: FlowOutputAction; Icon: typeof Download; label: string }[] = []
  if (canDownload) {
    actions.push({
      action: "download",
      Icon: Download,
      label: t("results.canvas.download"),
    })
  }
  actions.push({ action: "delete", Icon: Trash2, label: t("common.delete") })
  // The ⋯ menu = node business (2026-08-17 走查拍板): publish / open (a clip
  // with its render opens the detail modal via the surface; anything else
  // opens the lightbox in place) + focus (指认到对话输入框). A rendering
  // card's bar stays info-only — geometry reserved, no half-wired actions.
  const menuItems: { action: string; label: string }[] = [
    ...(output.type === "clip" && hasVideo
      ? [{ action: "publish", label: t("results.canvas.publish") }]
      : []),
    ...(hasVideo || shownThumbUrl
      ? [{ action: "open", label: t("results.canvas.open") }]
      : []),
    { action: "focus", label: t("results.canvas.focusNode") },
  ]
  const handleBarAction = (action: string) => {
    if (action === "open" && !(output.type === "clip" && hasVideo)) {
      onExpandMedia?.(node.id)
      return
    }
    onOutputAction?.(output.id, action as FlowOutputAction)
  }
  // Toolbar facts (2026-08-17 二轮走查): language / shape / duration — the
  // duration lives HERE, never as a media overlay badge; the bar is uncapped
  // and never ellipsizes, so all three always render in full. The shape slot
  // shows the media's real pixels once loaded, the spec's aspect before that.
  const barInfo: string[] = []
  if (output.language) {
    barInfo.push(
      t(`languages.${output.language}`, { defaultValue: output.language })
    )
  }
  const shape =
    dims ?? (clipAspect && clipAspect !== "original" ? clipAspect : null)
  if (shape) barInfo.push(shape)
  if (duration !== null && duration > 0) barInfo.push(`${duration}s`)

  // Multi-item outputs (quotes = N cards, carousel = N slides): the hover
  // switcher flips the main display between the node's variants; items
  // without their own baked media render as text tiles. The switcher
  // describes the node's OWN row — a version-pager flip to a sibling hides
  // it (its variants don't describe the sibling).
  const variants = flipped ? [] : (node.variants ?? [])
  const [variantIndex, setVariantIndex] = useState(0)
  const activeVariant = variants[variantIndex] ?? variants[0]
  const mediaThumb =
    variants.length > 0 ? (activeVariant?.thumbUrl ?? null) : shownThumbUrl

  return (
    <div className="group/product relative flex h-full w-full flex-col">
      {/* Variant switcher (the reference canvas's hover group): fades in at
          the node's top center on hover; each tile is one produced item.
          Always on under (hover: none) — touch has no reveal gesture. */}
      {variants.length > 1 && (
        <div className="pointer-events-none absolute -top-1 left-1/2 z-10 -translate-x-1/2 opacity-0 transition-opacity group-hover/product:opacity-100 [@media(hover:none)]:opacity-100">
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

      <NodeCaption
        label={node.label}
        Icon={PRODUCT_TYPE_ICON[output.type] ?? Clapperboard}
      />

      <div
        className={cn(
          "relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg bg-card ring-1",
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
              onLoadedMetadata={(e) =>
                setDims(
                  `${e.currentTarget.videoWidth}×${e.currentTarget.videoHeight}`
                )
              }
            />
          ) : mediaThumb ? (
            <img
              src={mediaThumb}
              alt={node.label}
              className={cn(
                "h-full w-full",
                clipAspect ? "object-contain" : "object-cover",
              )}
              onLoad={(e) =>
                setDims(
                  `${e.currentTarget.naturalWidth}×${e.currentTarget.naturalHeight}`
                )
              }
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
          {/* Media meta badges: the score rides the bottom-left corner; the
              top corners belong to the hover affordances (expand left, sound
              right). The duration is NOT a badge — it lives in the toolbar
              facts below the card (2026-08-17 二轮走查拍板). */}
          {score !== null && !renderFailed && (
            <span
              data-tour={node.tourTargets ? "results-score" : undefined}
              title={output.score?.reason ?? undefined}
              className={cn(
                "absolute bottom-2 left-2 rounded px-1.5 py-0.5 text-[10px] font-medium",
                node.topPick
                  ? "bg-primary text-primary-foreground"
                  : "bg-black/70 text-white",
              )}
            >
              {node.topPick ? `${t("results.topPick")} · ${score}` : score}
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
              onClick={() => onExpandMedia(node.id, flipped ? output.id : undefined)}
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

        {/* The padded interaction area: the product's OWN spec (ADR-051 F —
            the per-card global-prompt repetition retired into this). Read-
            only at rest; the hover prompt 框 is the edit + send affordance
            (the chat revision channel). A failed render speaks here in
            place (retry = the chat dock, D8). */}
        <div className="flex min-h-0 flex-1 flex-col gap-1 p-3">
          {output.spec_prompt ? (
            <p title={output.spec_prompt} className="line-clamp-2 text-xs leading-snug">
              {output.spec_prompt}
            </p>
          ) : null}
          {renderFailed ? (
            <p className="mt-auto line-clamp-2 text-[11px] leading-snug text-destructive">
              {t("results.canvas.renderFailed")}
            </p>
          ) : null}
        </div>
        <ReviseHoverBar
          specPrompt={output.spec_prompt}
          group="product"
          onRevise={onRevise ? (text) => onRevise(output.id, text) : undefined}
        />
      </div>

      {/* The always-on action band under the card — the shared MediaToolbar
          (2026-08-17 走查拍板, Lovart 解剖): media facts left, divider,
          download / publish / delete, and node business in the ⋯ menu. The
          band is reserved even while a render leaves it quiet — geometry
          never shifts. The version pager (ADR-051 F2) rides the same band
          when the fork family has ≥2 members — a separate pill, NEVER
          merged with the hover items switcher (条目切换 ≠ 版本切换). */}
      <div
        data-tour={node.tourTargets ? "results-menu" : undefined}
        className="flex h-[44px] shrink-0 items-start justify-center gap-2 pt-2"
      >
        {family.length > 1 && (
          <div className="dock-surface flex items-center gap-0.5 rounded-lg p-1 ring-1 ring-foreground/10">
            <button
              type="button"
              aria-label={t("results.canvas.versionPrev")}
              title={t("results.canvas.versionPrev")}
              disabled={shownIdx <= 0}
              onClick={(e) => {
                e.stopPropagation()
                flip(-1)
              }}
              className="flex h-7 w-7 items-center justify-center rounded-md text-foreground transition-colors hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            <span className="px-1 text-[11px] whitespace-nowrap tabular-nums text-muted-foreground">
              {t("results.canvas.versionOf", {
                current: shownIdx + 1,
                total: family.length,
              })}
            </span>
            <button
              type="button"
              aria-label={t("results.canvas.versionNext")}
              title={t("results.canvas.versionNext")}
              disabled={shownIdx >= family.length - 1}
              onClick={(e) => {
                e.stopPropagation()
                flip(1)
              }}
              className="flex h-7 w-7 items-center justify-center rounded-md text-foreground transition-colors hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
        <MediaToolbar
          info={barInfo}
          actions={renderActive ? [] : actions}
          menuItems={renderActive ? [] : menuItems}
          moreLabel={t("results.canvas.more")}
          onAction={handleBarAction}
        />
      </div>
    </div>
  )
}

/** The placeholder slot card (ADR-051 B — 占位物化): a live run's promised
 * product, born at its final size and position — the same band anatomy as
 * the product card (caption / card / reserved toolbar band) so the fill
 * swap is pixel-stable. Quiet by law: no status badge, no pulse, no
 * actions (the step narrative lives in the dock's folded checklist). The
 * ONE living signal is the FLORA wipe (2026-09-01 拍板): while the run is
 * alive the quiet wash fills the card left→right (纯 CSS ease-out, caps at
 * 96% — 假进度禁令不破: it never claims a fraction, the landing output is
 * the only 100%). Liveness = runAlive (2026-09-02 用户拍板, running ⊇
 * waiting): a promised slot keeps filling even before its producing step
 * starts and while the run parks for a human — the canvas's granularity is
 * alive/not-alive; the finer step narrative lives in the dock's folded
 * checklist. The body carries the functional teaching line (@-mention to
 * revise); the toolbar band shows the slot's KNOWN facts only (language /
 * pinned aspect — never invented). */
function PlaceholderCard({ node }: { node: FlowNode }) {
  const { t } = useTranslation()
  const ph = node.placeholder
  if (!ph) return null
  const TypeIcon = PRODUCT_TYPE_ICON[ph.type] ?? Clapperboard
  const isText = ph.type === "post" || ph.type === "article"
  const running = node.status === "running"
  const thumbPx = (ph.aspect && PRODUCT_THUMB_PX[ph.aspect]) || PRODUCT_THUMB_DEFAULT_PX
  const info: string[] = []
  if (ph.language) {
    info.push(t(`languages.${ph.language}`, { defaultValue: ph.language }))
  }
  if (!isText && ph.aspect) info.push(ph.aspect)
  const hint = (
    <p className="line-clamp-3 text-xs leading-snug text-muted-foreground">
      {t("results.canvas.placeholderHint")}
    </p>
  )
  return (
    <div className="flex h-full w-full flex-col">
      <NodeCaption label={node.label} Icon={TypeIcon} />
      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg bg-card ring-1 ring-foreground/10">
        {running && <span aria-hidden className="placeholder-wipe" />}
        {isText ? (
          <div className="flex min-h-0 flex-1 flex-col p-3">{hint}</div>
        ) : (
          <>
            <div
              className="flex shrink-0 items-center justify-center bg-muted"
              style={{ height: thumbPx }}
            >
              <TypeIcon className="h-5 w-5 text-muted-foreground" />
            </div>
            <div className="flex min-h-0 flex-1 flex-col gap-1 p-3">{hint}</div>
          </>
        )}
      </div>
      <div className="flex h-[44px] shrink-0 items-start justify-center pt-2">
        {info.length > 0 && (
          <MediaToolbar
            info={info}
            actions={[]}
            menuItems={[]}
            moreLabel={t("results.canvas.more")}
            onAction={() => {}}
          />
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
  const { node, bornIndex, selected, onOutputAction, onExpandMedia, onAssetAction, onRevise } = data
  // Latch the birth frame: the surface drops bornIndex on the next commit
  // (its seen-set absorbs the id), and a follow-up SSE tick can land inside
  // the 420ms keyframe — the class must outlive the animation. A class that
  // stays continuously applied never replays; a remount (the node left the
  // graph and returned) starts a fresh latch.
  const bornLatchRef = useRef<number | undefined>(undefined)
  if (bornIndex !== undefined) bornLatchRef.current = bornIndex
  const born = bornLatchRef.current
  // The product card is a composite (caption + card + action band) — its
  // selected ring hugs the CARD, not the node box; every other skin is a
  // single box and takes the ring on the root.
  const isProduct = node.kind === "output" && !!node.output
  return (
    <div
      className={cn(
        "h-full w-full cursor-pointer rounded-md text-foreground transition-colors",
        // A placeholder slot has no row to open — the click would be a lie.
        node.placeholder && "cursor-default",
        // Placeholders are exempt from the status chrome: a promised slot
        // never dims, and its running signal is the FLORA wipe inside the
        // card (one living signal per card — pulse + wipe would fight).
        // Artifact cards (the plan) are exempt too: their body is
        // birth-complete (server-projected from the confirmed book), so
        // pipeline liveness must not dim settled information — only
        // not-yet-landed products/placeholders read as pending (2026-09-04
        // 验收: a decided plan looked ghostly through the whole queued phase).
        node.status === "pending" &&
          !node.placeholder &&
          node.kind !== "artifact" &&
          "opacity-50",
        node.status === "skipped" && "opacity-40",
        node.status === "running" && !node.placeholder && "flow-node-running",
        born !== undefined && "flow-node-born",
        selected && !isProduct && "rounded-md ring-2 ring-foreground/40",
      )}
      style={born !== undefined ? { animationDelay: `${born * BIRTH_STAGGER_MS}ms` } : undefined}
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
      ) : node.kind === "output" && node.placeholder ? (
        <PlaceholderCard node={node} />
      ) : node.kind === "output" && node.textContent ? (
        <TextProductCard
          node={node}
          selected={selected}
          onOutputAction={onOutputAction}
          onRevise={onRevise}
        />
      ) : node.kind === "output" ? (
        <ProductCard
          node={node}
          selected={selected}
          onOutputAction={onOutputAction}
          onExpandMedia={onExpandMedia}
          onAssetAction={onAssetAction}
          onRevise={onRevise}
        />
      ) : (
        <ThumbCard
          node={node}
          onExpandMedia={onExpandMedia}
          onAssetAction={onAssetAction}
        />
      )}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-0 !w-0 !opacity-0"
      />
    </div>
  )
}
