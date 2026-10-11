import { Handle, Position, type Node, type NodeProps } from "@xyflow/react"
import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from "react"
import { createPortal } from "react-dom"
import {
  ArrowUp,
  AudioLines,
  ChevronLeft,
  ChevronRight,
  Clapperboard,
  Copy,
  Download,
  FileText,
  Image as ImageIcon,
  Images,
  Maximize2,
  MoreHorizontal,
  Newspaper,
  PencilLine,
  Quote,
  Send,
  TriangleAlert,
  Type,
  Video,
  Volume2,
  VolumeX,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { BrandLoader } from "@/components/BrandLoader"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { apiPut, fetchAssetTranscript, putAssetTranscript, toAbsoluteUrl, type AssetTranscript } from "@/lib/api"
import { cn, formatDuration } from "@/lib/utils"
import type { GraphEdgeType, Output, ProjectArtifact } from "@/lib/types"

import { BIRTH_STAGGER_MS, PRODUCT_LABEL_PX, PRODUCT_PAGER_PX, PRODUCT_THUMB_DEFAULT_PX, PRODUCT_THUMB_PX, PROGRAM_REGION_PX, PRODUCT_TOOLBAR_PX, TRANSCRIPT_SECTION_PX, cornerStackedInPorts, hasProgramRegion, hasTrackStack, nleModifierLanes, trackVideoPortBasePx } from "./layout"
import { useSoundMutex } from "./sound-mutex"
import type {
  FlowAssetAction,
  FlowAssetInfo,
  FlowNode,
  FlowOutputAction,
  LineageHover,
  OutPortType,
} from "./types"

export interface FlowCardData extends Record<string, unknown> {
  node: FlowNode
  /** Reveal index for birth choreography (undefined = render instantly). */
  bornIndex?: number
  selected: boolean
  /** The node's visible ports (ADR-057 端口法则 — computed by FlowView from
   * the incident typed edges): in-ports stack from the consumption region's
   * bottom-left corner (typed by what the consumer takes), out-ports from
   * the production region's top-right (typed by the node's own medium —
   * 出锚语义律 2026-09-11). Undefined = an untyped surface (the recipe
   * 说明书 — the legacy invisible handles render instead). */
  ports?: { in: Exclude<GraphEdgeType, "ctx">[]; out: OutPortType[] }
  /** Product-toolbar dispatch (ADR-041 D5) — the surface owns the actions. */
  onOutputAction?: (outputId: string, action: FlowOutputAction) => void
  /** 选区引用 (2026-09-11 — 段落级指认): the user selected a passage on a
   * text product's card face and pinned it — the surface inserts an @output
   * chip carrying the quote into the dock. */
  onQuoteOutput?: (outputId: string, quote: string) => void
  /** Asset-toolbar dispatch (2026-08-17) — the surface owns asset actions. */
  onAssetAction?: (asset: FlowAssetInfo, action: FlowAssetAction) => void
  /** Media expand dispatch — the surface opens the lightbox for the node.
   * `outputId` overrides the node's own row when the pager has the card
   * displaying a sibling (the lightbox must show what the card shows). */
  onExpandMedia?: (nodeId: string, outputId?: string) => void
  /** The pager's displayed product (mount + flip) — the surface tracks it
   * so a node click selects what the user is LOOKING at. */
  onDisplayChange?: (nodeId: string, outputId: string) => void
  /** Card-face prompt direct edit (ADR-057 K4): the card reports the new
   * program; the surface opens the pricing confirmation (锚定子图 + 估价)
   * — nothing touches the graph until the confirm's CODE-built ops land. */
  onPromptEdit?: (nodeId: string, text: string) => void
  /** The edit's optimistic echo (ADR-058): while the confirm is open or
   * the stamp is in flight, the program region shows the user's verbatim
   * text instead of the domain's last stamp — never a revert flash. */
  pendingProgram?: string | null
  /** 动作住节点内 (2026-09-10 判词①): the prompt edit's pricing
   * confirmation docks INSIDE the program region (the retired overlay's
   * facts verbatim) — blast labels (锚定子图), the credit range, the
   * balance soft-compare, and the two gestures. */
  promptConfirm?: {
    blastLabels: string[]
    blastSingle: boolean
    low: number
    high: number
    /** 估价诚实面: unquoted nodes in the blast (estimate_credits null —
     * transform chains price mid-run). */
    unquoted: number
    balance: number | null
    onConfirm: () => void
    onCancel: () => void
  } | null
  /** cross-highlight (ADR-113 §6 — 唯一跨卡通道): the deliverable card's
   * video-lane block hover reports the source interval through this
   * channel; the surface holds it and hands it back as `lineageHover`. */
  onLineageHover?: (hover: LineageHover | null) => void
  /** The live cross-highlight — the asset card whose id matches lights its
   * overlapping strip blocks / cue rows (`bg-lineage`). */
  lineageHover?: LineageHover | null
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
 * actions (copy-or-download + publish; the ⋯ menu is retired, 2026-09-10).
 * The bar hugs its content — width is NOT capped
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
 * band as its own pill STACKED ABOVE the bar (2026-09-13 用户拍板 — the
 * side-by-side row outgrew the card's width), NEVER merged with the hover
 * items switcher (条目切换 ≠ 版本切换). */
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

/** L1 读数 chip (信息秩三分, ADR-115): the hover layer's ONE shape — a
 * transient reading floating ABOVE the hovered block (never baked into the
 * block, never covering the row below it), portal'd to document.body
 * (视口锚浮层律), pointer-events-none, overlay-surface frost. One instance
 * per card: the host reports the anchor's rect + content on hover, null on
 * leave/scroll. Pure presentation — the chip never intercepts a gesture. */
function HoverChip({ chip }: { chip: HoverChipState }) {
  if (!chip) return null
  const W = 300
  // SSR-safe: a chip exists only after a client pointer event.
  const cx = Math.min(
    Math.max(chip.rect.left + chip.rect.width / 2, W / 2 + 8),
    window.innerWidth - W / 2 - 8,
  )
  const above = chip.rect.top > 96
  return createPortal(
    <div
      className="overlay-surface pointer-events-none fixed z-[100] max-w-[300px] rounded-lg px-2 py-1.5 text-[11px] leading-snug text-foreground"
      style={{
        left: cx,
        top: above ? chip.rect.top - 10 : chip.rect.bottom + 10,
        transform: above ? "translate(-50%, -100%)" : "translate(-50%, 0)",
      }}
    >
      {chip.content}
    </div>,
    document.body,
  )
}

/** The chip's second line — the quiet reading under the title. */
function HoverChipMeta({ children }: { children: ReactNode }) {
  return (
    <div className="mt-0.5 text-[10px] tabular-nums text-muted-foreground">
      {children}
    </div>
  )
}

/** The transcript section's shared cache (the canvas's seat — keyed by the
 * asset id, so every card of one asset reads one fetch; a save writes the
 * fresh response straight back). */
const transcriptCache = new Map<string, AssetTranscript | null>()

/** The asset card's transcript data channel (ADR-113 §1 — the transcript's
 * ONE seat is the asset row): mount-fetches from the asset's transcript
 * endpoint, cached module-wide; a processing-stage flip invalidates (mid-
 * flight ASR drops the snapshot, the terminal flip refetches); a save
 * writes the fresh response straight back. Lives at the CARD level
 * (ThumbCard, ADR-115) so the stage skin (the media's bottom edge) and the
 * cue flow read one snapshot. */
function useAssetTranscript(asset: FlowAssetInfo | undefined): {
  tx: AssetTranscript | null | undefined
  saving: boolean
  save: (next: string | null) => Promise<boolean>
} {
  const assetId = asset?.id ?? ""
  const projectId = asset?.project_id ?? null
  const [tx, setTx] = useState<AssetTranscript | null | undefined>(() =>
    assetId ? transcriptCache.get(assetId) : undefined,
  )
  const [saving, setSaving] = useState(false)
  const processing =
    asset?.processing_status === "pending" || asset?.processing_status === "processing"
  useEffect(() => {
    if (!assetId || !projectId) return
    if (processing) {
      transcriptCache.delete(assetId)
      setTx(undefined)
      return
    }
    if (transcriptCache.has(assetId)) {
      setTx(transcriptCache.get(assetId))
      return
    }
    let cancelled = false
    void fetchAssetTranscript(projectId, assetId).then((res) => {
      transcriptCache.set(assetId, res)
      if (!cancelled) setTx(res)
    })
    return () => {
      cancelled = true
    }
  }, [assetId, projectId, processing])

  const save = useCallback(
    async (next: string | null): Promise<boolean> => {
      if (!projectId || !assetId || saving) return false
      setSaving(true)
      try {
        const res = await putAssetTranscript(projectId, assetId, next)
        if (res) {
          // Optimistic echo + the shared cache's invalidation in one write —
          // the card face shows the user's words NOW; the next mount agrees.
          transcriptCache.set(assetId, res)
          setTx(res)
          return true
        }
        return false
      } finally {
        setSaving(false)
      }
    },
    [assetId, projectId, saving],
  )
  return { tx, saving, save }
}

/** The HoverChip's anchor — a real DOMRect (a hovered row) or a synthetic
 * one (the stage skin's cursor point). */
type HoverChipState = {
  rect: { left: number; width: number; top: number; bottom: number }
  content: ReactNode
} | null

/** 舞台检视皮 (ADR-115 素材卡阅读型解剖): the time axis as a 3px skin on
 * the media's own bottom edge — cue segments ∝ their span (pauses read as
 * air), the playhead needle riding the player's clock; the media hover
 * fattens it to 8px, a click seeks (只拨头, the ambient-muted law
 * untouched), the hover reading ("m:ss / m:ss") floats in the L1 chip. The
 * axis lives ON the stage it describes — the in-section time strip retired,
 * the cue flow keeps its full band. Time formatting here is player chrome
 * (the scrubber readout's one client seat — formatDuration, shared with
 * the lightbox player), never a data row. The lineage interval lights the
 * overlapping segments amber (ADR-113 §6). */
function StageSkin({
  cues,
  duration,
  playhead,
  onSeek,
  highlight,
}: {
  cues: NonNullable<AssetTranscript["cues"]>
  duration: number
  playhead: number
  onSeek: (seconds: number) => void
  highlight?: { srcStart: number; srcEnd: number } | null
}) {
  const [chip, setChip] = useState<HoverChipState>(null)
  if (duration <= 0) return null
  const pct = (v: number) => `${(v / duration) * 100}%`
  const lit = (start: number, end: number) =>
    !!highlight && end > highlight.srcStart && start < highlight.srcEnd
  return (
    <div
      className="nodrag absolute inset-x-0 bottom-0 z-[2] h-[3px] cursor-pointer bg-white/20 transition-[height] group-hover/media:h-2"
      onClick={(e) => {
        e.stopPropagation()
        const r = e.currentTarget.getBoundingClientRect()
        onSeek(((e.clientX - r.left) / r.width) * duration)
      }}
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect()
        const t = ((e.clientX - r.left) / r.width) * duration
        setChip({
          rect: { left: e.clientX, width: 0, top: r.top, bottom: r.top },
          content: (
            <span className="tabular-nums text-muted-foreground">
              {formatDuration(t)} / {formatDuration(duration)}
            </span>
          ),
        })
      }}
      onMouseLeave={() => setChip(null)}
    >
      {cues.map((cue, i) => (
        <span
          key={i}
          aria-hidden
          className={cn(
            "absolute top-0 bottom-0",
            lit(cue.start, cue.end) ? "bg-lineage" : "bg-white/50",
          )}
          style={{
            left: pct(cue.start),
            width: `${Math.max(((cue.end - cue.start) / duration) * 100, 0.8)}%`,
          }}
        />
      ))}
      <span
        aria-hidden
        className="pointer-events-none absolute top-0 bottom-0 w-0.5 bg-white"
        style={{ left: `${Math.min((playhead / duration) * 100, 100)}%` }}
      />
      <HoverChip chip={chip} />
    </div>
  )
}

/** The asset's content layer (ADR-113 §3; ADR-115 阅读型解剖): the cue flow
 * IS the reading face — the header (title + edit affordance), then the
 * sentence rows on ONE scroll axis. The time axis moved ONTO the stage
 * (StageSkin at the media's bottom edge); the row's time reading floats in
 * the L1 chip ABOVE the row (never covers the text). The playing row
 * lights (`bg-accent`), the cross-highlighted interval lights amber
 * (`bg-lineage`, ADR-113 §6). Paste/extraction yields carry no time axis —
 * the honest plain-text face. The edit overlay (edited_text) reads as
 * plain text (the user's own words carry no honest time alignment);
 * editing writes the overlay only (C4 — times never enter the textarea). */
function TranscriptSection({
  tx,
  saving,
  onSave,
  videoRef,
  playhead,
  onSeek,
  fill,
  highlight,
}: {
  tx: AssetTranscript | null | undefined
  saving: boolean
  onSave: (next: string | null) => Promise<boolean>
  videoRef?: RefObject<HTMLVideoElement | null>
  /** The inline player's clock — the now-row's light. Absent/0 without a
   * player (medialess assets read a timeless face). */
  playhead?: number
  onSeek: (seconds: number) => void
  /** Medialess assets (paste/transcript): the section IS the card body
   * (flex-1); below media it keeps its fixed reservation (frame law — the
   * anchor/flex seats never move mid-life). */
  fill?: boolean
  /** cross-highlight (ADR-113 §6): the interval a deliverable card's lane
   * block hover named — cue rows overlapping it light up (`bg-lineage`).
   * Already resolved to THIS asset by the card. */
  highlight?: { srcStart: number; srcEnd: number } | null
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [chip, setChip] = useState<HoverChipState>(null)

  useEffect(() => {
    if (editing && textareaRef.current) {
      textareaRef.current.focus()
      const len = textareaRef.current.value.length
      textareaRef.current.setSelectionRange(len, len)
    }
  }, [editing])

  // Same native-wheel stop as the retired document card's edit region —
  // React Flow's pane listens natively, so a synthetic stopPropagation is
  // not enough.
  useEffect(() => {
    const el = textareaRef.current
    if (!el || !editing) return
    const stopWheel = (e: WheelEvent) => e.stopPropagation()
    el.addEventListener("wheel", stopWheel, { passive: true })
    return () => el.removeEventListener("wheel", stopWheel)
  }, [editing])

  const cues = tx?.edited_text == null ? (tx?.cues ?? null) : null
  const bodyText = tx ? (tx.edited_text ?? tx.text) : ""
  // cross-highlight (ADR-113 §6): does a region overlap the interval the
  // deliverable card's hover named? Half-open overlap on the source axis.
  const lit = (start: number, end: number) =>
    !!highlight && end > highlight.srcStart && start < highlight.srcEnd
  // The now-row's light — only with a live player.
  const now = (start: number, end: number) =>
    !!videoRef && playhead != null && playhead >= start && playhead < end

  // The section's flex law (一条律两世界): below media it grows to the
  // frame's reservation (TRANSCRIPT_SECTION_PX — the divider holds its
  // first 1px) but compresses to its floor inside a legacy short frame
  // (born pre-section) — the media keeps its share, the cue flow scrolls
  // tighter, never an overlap/crush. Medialess assets: the section IS the
  // body (plain flex-1, no cap).
  const sectionClass = fill
    ? "flex min-h-0 flex-1 flex-col"
    : "flex min-h-[96px] flex-1 flex-col"
  const sectionStyle = fill ? undefined : { maxHeight: TRANSCRIPT_SECTION_PX - 1 }

  const saveDraft = async (next: string | null) => {
    const current = tx?.edited_text ?? tx?.text ?? ""
    if (next !== null && next === current) {
      setEditing(false)
      return
    }
    if (await onSave(next)) setEditing(false)
  }

  if (tx === undefined) {
    // Load-quiet law: the frame reserved this section at birth — the box
    // holds its seat empty, never a spinner.
    return <div className={sectionClass} style={sectionStyle} />
  }

  return (
    <div className={cn(sectionClass, "gap-1.5 px-3 pb-3 pt-2")} style={sectionStyle}>
      {/* The section header: title + the edit affordance (✎). Zero-chrome
          law — the header is quiet meta chrome, the body the content. */}
      <div className="flex h-5 shrink-0 items-center justify-between">
        <span className="text-meta text-[10px]">
          {t("results.canvas.transcript")}
        </span>
        {!editing && tx !== null && (tx.text || tx.edited_text) ? (
          <button
            type="button"
            aria-label={t("results.canvas.editTranscript")}
            onClick={(e) => {
              e.stopPropagation()
              setDraft(tx.edited_text ?? tx.text)
              setEditing(true)
            }}
            className="nodrag flex h-5 w-5 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <PencilLine className="h-3 w-3" />
          </button>
        ) : null}
      </div>
      {editing ? (
        <div className="relative min-h-0 flex-1">
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => void saveDraft(draft)}
            onWheel={(e) => {
              e.stopPropagation()
              e.preventDefault()
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault()
                setEditing(false)
              } else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                e.preventDefault()
                void saveDraft(draft)
              }
            }}
            disabled={saving}
            className="nowheel nopan thin-scroll h-full w-full resize-none overflow-y-auto overscroll-contain bg-transparent text-xs leading-relaxed outline-none"
          />
          {tx?.edited_text != null ? (
            // 恢复原文 (overlay reset): mousedown keeps the textarea's focus
            // so the blur-save never fires ahead of the reset.
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={(e) => {
                e.stopPropagation()
                void saveDraft(null)
              }}
              className="nodrag absolute right-1 bottom-1 rounded-md bg-accent px-2 py-1 text-[11px] text-foreground ring-1 ring-foreground/10 transition-colors hover:bg-accent/70"
            >
              {t("results.canvas.resetToSource")}
            </button>
          ) : null}
        </div>
      ) : cues && cues.length > 0 ? (
        /* cue 流: the sentence blocks on ONE scroll axis — the time reading
           floats ABOVE the row (L1 chip, never covers the text); click =
           seek (with a player); the playing row lights, the lineage
           interval lights amber. */
        <div
          className="nowheel nopan thin-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain [-webkit-mask-image:linear-gradient(to_bottom,black_calc(100%_-_32px),transparent_100%)] [mask-image:linear-gradient(to_bottom,black_calc(100%_-_32px),transparent_100%)]"
          onScroll={() => setChip(null)}
        >
          <div className="flex flex-col gap-1">
            {cues.map((cue, i) => (
              <div
                key={i}
                role={videoRef ? "button" : undefined}
                tabIndex={videoRef ? 0 : undefined}
                onClick={
                  videoRef
                    ? (e) => {
                        e.stopPropagation()
                        onSeek(cue.start)
                      }
                    : undefined
                }
                onMouseEnter={
                  videoRef
                    ? (e) =>
                        setChip({
                          rect: e.currentTarget.getBoundingClientRect(),
                          content: (
                            <span className="tabular-nums text-muted-foreground">
                              {cue.label}
                            </span>
                          ),
                        })
                    : undefined
                }
                onMouseLeave={() => setChip(null)}
                className={cn(
                  "relative rounded-md px-1.5 -mx-1.5 transition-colors hover:bg-accent",
                  videoRef && "cursor-pointer",
                  now(cue.start, cue.end) && "bg-accent",
                  // cross-highlight (ADR-113 §6): the interval the
                  // deliverable card's lane hover named lights here.
                  lit(cue.start, cue.end) && "bg-lineage",
                )}
              >
                <p className="whitespace-pre-wrap text-xs leading-relaxed">{cue.text}</p>
              </div>
            ))}
            {tx?.truncated ? (
              <p className="text-meta px-1.5 text-[10px]">
                {t("results.canvas.transcriptTruncated")}
              </p>
            ) : null}
          </div>
        </div>
      ) : bodyText ? (
        <div className="nowheel nopan thin-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain">
          <p className="whitespace-pre-wrap text-xs leading-relaxed">{bodyText}</p>
          {tx?.truncated ? (
            <p className="text-meta mt-1 text-[10px]">
              {t("results.canvas.transcriptTruncated")}
            </p>
          ) : null}
        </div>
      ) : tx !== null ? (
        // 空稿诚实面: ASR completed with zero words (silence / music-only) —
        // say so, never a blank card. Load-failure (null) renders nothing.
        <p className="text-xs leading-relaxed text-muted-foreground">
          {t("results.canvas.transcriptEmpty")}
        </p>
      ) : (
        <div className="min-h-0 flex-1" />
      )}
      <HoverChip chip={chip} />
    </div>
  )
}

/** The deliverable card's NLE 检视轴 (ADR-115 — 成片卡检视解剖): below the
 * media, a read-only timeline — the RULER (server-formatted scale, click
 * = seek), the VIDEO lane (kept segments as real clip objects — multi-block
 * multi-source, per-block lineage hover + click seek), the TEXT lane
 * (caption blocks with ZERO inner text — the sentence and its range ride
 * the L1 hover chip), and any MODIFIER lanes (music/dub presence face).
 * All lanes ONE height (34px). The score is NOT here — it rides the media's
 * hover chrome (MediaProductRegion).
 * READ-ONLY + seek (L3 — never an orchestration surface: no drag, no
 * add/remove track, no transition handles; the lanes are how the user READS
 * the product). 信息秩三分: L0 structure persists on the card, L1 readings
 * hover (HoverChip), L2 detail clicks through to the inspector. The lanes
 * are in the anatomy FROM BIRTH (draft/running render muted empty rows —
 * the waiting seat), so the video in-port's anchor (锚点律, NodePorts)
 * never moves mid-life; modifier lanes arrive on the product-landing beat
 * and shift the anchor on that same beat (the version pager's precedent).
 * Block geometry is ∝ the output clock; every time label arrives
 * preformatted from the server (the client never formats time). */
function NleAxis({
  output,
  videoRef,
  onLineageHover,
}: {
  /** The displayed product (the pager's shown member — a flip re-reads the
   * lanes off the new member). Stack-less (draft / non-clip) = the muted
   * empty rows. */
  output?: Output
  videoRef?: RefObject<HTMLVideoElement | null>
  onLineageHover?: FlowCardData["onLineageHover"]
}) {
  const { t } = useTranslation()
  const stack = output?.track_stack ?? null
  const lane = stack?.video_lane ?? []
  const sentences = stack?.text_lane ?? []
  const ruler = stack?.ruler ?? []
  // The output axis total = the video lane's concatenated end (the
  // product's duration); the server clamps the text blocks inside it.
  const total = lane.length > 0 ? lane[lane.length - 1].out_end : 0
  const modifiers = stack?.modifiers ?? {}
  const activeModifiers = (["music", "dub"] as const).filter((m) => modifiers[m])
  // The needle rides the inline player's own clock (timeupdate is ~4Hz —
  // cheap). Re-bind when the displayed member flips (the pager swaps the
  // <video> element under the stable ref).
  const [playhead, setPlayhead] = useState(0)
  useEffect(() => {
    const v = videoRef?.current
    if (!v) return
    const onTime = () => setPlayhead(v.currentTime)
    v.addEventListener("timeupdate", onTime)
    return () => v.removeEventListener("timeupdate", onTime)
  }, [videoRef, output?.id])
  const seek = (seconds: number) => {
    // 文本驱动 seek 只拨头 — the ambient-muted law is untouched (never an
    // autoplay-with-sound side effect).
    const v = videoRef?.current
    if (v) v.currentTime = seconds
  }
  // L1 读数 chip: one per axis; the hovered block reports its rect + reading.
  const [chip, setChip] = useState<{ rect: DOMRect; content: ReactNode } | null>(null)
  const chipFrom = (e: React.MouseEvent, content: ReactNode) =>
    setChip({ rect: e.currentTarget.getBoundingClientRect(), content })
  const frac = total > 0 ? Math.min(Math.max(playhead / total, 0), 1) : 0
  const pct = (v: number) => `${(v / total) * 100}%`
  return (
    <div className="shrink-0 px-4 pb-1 pt-1">
      {/* Ruler: the server-formatted scale — click seeks, the needle's host
          box (its left/right edges ARE the lanes'). */}
      <div
        className="nodrag relative h-[22px] cursor-pointer"
        onClick={(e) => {
          e.stopPropagation()
          if (total <= 0) return
          const r = e.currentTarget.getBoundingClientRect()
          seek(((e.clientX - r.left) / r.width) * total)
        }}
      >
        {total > 0 &&
          ruler.map((tick, i) => (
            <span key={i}>
              <span
                aria-hidden
                className="absolute bottom-0 h-[9px] w-px bg-meta-foreground opacity-90"
                style={{ left: pct(tick.t) }}
              />
              <span
                aria-hidden
                className="text-meta absolute top-0 -translate-x-1/2 text-[9px] tabular-nums"
                style={{ left: pct(tick.t) }}
              >
                {tick.label}
              </span>
            </span>
          ))}
        {total > 0 && (
          /* 跨道播放头: one needle from the ruler's top through the lanes —
             its host box spans exactly the lanes' width. Height = ruler 22 +
             ruler gap 6 + video 34 + lane gap 8 + text 34 + 42 per modifier
             lane (mirror of layout.ts NLE_* — change one, change both). */
          <span
            aria-hidden
            className="pointer-events-none absolute top-0 z-10 w-px bg-foreground"
            style={{
              left: `${frac * 100}%`,
              height: 22 + 6 + 34 + 8 + 34 + activeModifiers.length * 42,
            }}
          >
            <span className="absolute -top-0.5 left-1/2 h-0 w-0 -translate-x-1/2 border-x-[3.5px] border-t-[5px] border-x-transparent border-t-foreground" />
          </span>
        )}
      </div>
      {/* The lanes: full-width boxes, no gutter icons (the lane's fill hue
          is its label). mt = the ruler→lane gap; gap = the inter-lane beat
          (layout.ts NLE_RULER_GAP_PX / NLE_LANE_GAP_PX — one law, two
          mirrors). */}
      <div className="mt-1.5 flex flex-col gap-2">
        <div
          className="relative h-[34px]"
          role="group"
          aria-label={t("results.canvas.videoTrack")}
        >
            {lane.length === 0 || total <= 0 ? (
              <span className="absolute inset-0 rounded-md bg-muted" />
            ) : (
              lane.map((block, i) => {
                const label = t("results.canvas.trackSegment", {
                  n: i + 1,
                  src: block.src_label,
                })
                return (
                  <button
                    key={i}
                    type="button"
                    aria-label={label}
                    onClick={(e) => {
                      e.stopPropagation()
                      seek(block.out_start)
                    }}
                    onMouseEnter={(e) => {
                      chipFrom(
                        e,
                        <>
                          <div>
                            {t("results.canvas.trackSegmentTitle", { n: i + 1 })}
                          </div>
                          <HoverChipMeta>
                            {t("results.canvas.trackSegmentOut", {
                              out: block.out_label,
                              src: block.src_label,
                            })}
                          </HoverChipMeta>
                        </>,
                      )
                      if (block.asset_id) {
                        onLineageHover?.({
                          assetId: block.asset_id,
                          srcStart: block.src_start,
                          srcEnd: block.src_end,
                        })
                      }
                    }}
                    onMouseLeave={() => {
                      setChip(null)
                      onLineageHover?.(null)
                    }}
                    className="nodrag absolute top-0 bottom-0 flex items-center overflow-hidden rounded-md bg-track-video px-2 text-left text-track-video-foreground ring-1 ring-inset ring-track-video-foreground/25 transition-[filter] hover:brightness-[0.96] dark:hover:brightness-110"
                    style={{
                      left: pct(block.out_start),
                      // 分段分界: a block that doesn't touch the axis's end
                      // shaves 1px off its right — ring + hairline air reads
                      // each kept segment as its own clip object.
                      width:
                        block.out_end >= total
                          ? pct(block.out_end - block.out_start)
                          : `calc(${pct(block.out_end - block.out_start)} - 1px)`,
                    }}
                  >
                    <span className="truncate text-[11px] leading-none">{label}</span>
                  </button>
                )
              })
            )}
          </div>
        <div
          className="relative h-[34px]"
          role="group"
          aria-label={t("results.canvas.textTrack")}
        >
            {sentences.length === 0 || total <= 0 ? (
              <span className="absolute inset-0 rounded-md bg-muted" />
            ) : (
              sentences.map((block, i) => (
                <button
                  key={i}
                  type="button"
                  aria-label={block.text}
                  onClick={(e) => {
                    e.stopPropagation()
                    seek(block.out_start)
                  }}
                  onMouseEnter={(e) =>
                    chipFrom(
                      e,
                      <>
                        <div className="whitespace-pre-wrap">{block.text}</div>
                        <HoverChipMeta>{block.label}</HoverChipMeta>
                      </>,
                    )
                  }
                  onMouseLeave={() => setChip(null)}
                  className="nodrag absolute top-0 bottom-0 rounded-md bg-muted ring-1 ring-inset ring-foreground/10 transition-colors hover:bg-accent"
                  style={{
                    left: pct(block.out_start),
                    // 分段分界 — same law as the video lane: a block that
                    // doesn't touch the axis's end shaves 1px off its right.
                    width:
                      block.out_end >= total
                        ? pct(block.out_end - block.out_start)
                        : `calc(${pct(block.out_end - block.out_start)} - 1px)`,
                  }}
                />
              ))
            )}
          </div>
        {/* 修饰道 (presence face — the content face is a later batch): arrive
            with the product, BELOW the text lane (the NLE order); the anchor
            shifts on that same beat (pager precedent). */}
        {activeModifiers.map((m) => (
          <div
            key={m}
            className="relative h-[34px]"
            role="group"
            aria-label={
              m === "music"
                ? t("results.canvas.modifierMusic")
                : t("results.canvas.modifierDub")
            }
          >
            <span className="absolute inset-0 flex items-center rounded-md bg-track-audio px-2 text-track-audio-foreground">
              <span className="truncate text-[10px]">
                {m === "music"
                  ? t("results.canvas.modifierMusic")
                  : t("results.canvas.modifierDub")}
              </span>
            </span>
          </div>
        ))}
      </div>
      <HoverChip chip={chip} />
    </div>
  )
}

function ThumbCard({
  node,
  onExpandMedia,
  onAssetAction,
  lineageHover,
}: {
  node: FlowNode
  onExpandMedia?: (nodeId: string) => void
  onAssetAction?: FlowCardData["onAssetAction"]
  /** cross-highlight (ADR-113 §6): the live hover — lights this card's
   * transcript section when it names THIS asset. */
  lineageHover?: LineageHover | null
}) {
  const { t } = useTranslation()
  // The fallback glyph follows the dossier's asset type (graph canvas —
  // the read face already mapped the row to its medium kind); the recipe
  // surface's manual asset node keeps the prose default.
  const asset = node.asset
  const TypeIcon =
    asset?.type === "video"
      ? Clapperboard
      : asset?.type === "image"
        ? ImageIcon
        : FileText
  const FallbackIcon = asset ? TypeIcon : node.kind === "asset" ? FileText : Clapperboard
  // The inline video's ambient playback is muted by default (autoplay
  // policy); the hover sound icon flips it. 全局声音指针 (2026-09-13): the
  // mute rides the project-wide mutex — unmuting here mutes every other
  // media on the canvas (local-state fallback off-canvas).
  const { muted, toggle: toggleMuted } = useSoundMutex(node.id)
  // Media facts for the toolbar are read off the loaded media itself — the
  // real pixels, never a hardcoded table.
  const [dims, setDims] = useState<string | null>(null)
  const expandable = !!(node.videoUrl || node.thumbUrl) && !!onExpandMedia
  const videoRef = useRef<HTMLVideoElement>(null)

  // The asset toolbar (results canvas only — a node without the action
  // channel, e.g. the recipe manual, renders no bar): media facts on the
  // left (filename / duration / resolution), then download ONLY — delete
  // leaves every canvas toolbar (2026-09-13 二轮拍板, extending the same
  // day's product-bar ruling: no node carries a destructive affordance;
  // the delete API + handler branch stay retained like the products').
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

  // ADR-113 §3: the content layer's seat inside the asset card — text-
  // yielding assets (a dossier on the results canvas; the recipe surface's
  // dossier-less manual node never grows one).
  const textBearing =
    !!asset &&
    (asset.type === "video" ||
      asset.type === "audio" ||
      asset.type === "transcript" ||
      asset.type === "past_material")
  // Paste/extraction assets carry no media — the transcript section IS the
  // card body (no media box, no stage skin).
  const medialess = asset?.type === "transcript" || asset?.type === "past_material"

  // ADR-115 阅读型解剖: the transcript channel lives at the CARD level —
  // the stage skin (the media's bottom edge) and the cue flow read one
  // snapshot. The edit overlay hides the cue axis (no honest alignment).
  const { tx, saving, save } = useAssetTranscript(textBearing ? asset : undefined)
  const cues = tx?.edited_text == null ? (tx?.cues ?? null) : null
  const duration = asset?.duration_seconds ?? cues?.[cues.length - 1]?.end ?? 0
  // The stage skin's needle + the cue flow's now-row ride the inline
  // player's own clock (timeupdate is ~4Hz — cheap).
  const [playhead, setPlayhead] = useState(0)
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    const onTime = () => setPlayhead(v.currentTime)
    v.addEventListener("timeupdate", onTime)
    return () => v.removeEventListener("timeupdate", onTime)
  }, [node.videoUrl])
  const seek = (seconds: number) => {
    const v = videoRef.current
    if (v) v.currentTime = seconds
  }
  const highlight =
    lineageHover && asset && lineageHover.assetId === asset.id
      ? { srcStart: lineageHover.srcStart, srcEnd: lineageHover.srcEnd }
      : null

  return (
    <div className="flex h-full w-full flex-col">
      <NodeCaption label={node.label} Icon={asset ? TypeIcon : undefined} />
      {/* 一体环 (ADR-115): media + transcript inside ONE ring — the card IS
          the reading surface. The stage keeps its aspect-pinned reservation
          (flex-1 against the section's fixed anatomy — the frame math pins
          it, never a mid-life squeeze); object-cover = zero letterbox, the
          display-class bucket bounds the crop. */}
      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg bg-card ring-1 ring-foreground/10">
        {medialess ? null : (
          <div
            className={cn(
              "group/media relative min-h-0 flex-1",
              node.videoUrl || node.containThumb ? "bg-black" : "bg-muted",
            )}
          >
            {node.videoUrl ? (
              /* The source video node plays inline — muted ambient loop,
                 first frame instantly (preload=metadata), non-interactive:
                 clicks and drags belong to the canvas. object-COVER
                 (2026-09-28 黑底走查): the frame's aspect bucket never
                 matches the source's real ratio to the pixel (960×544 in a
                 16:9 bucket = pillarbox strips) — cover fills the box and
                 crops the sub-percent sliver instead of showing the
                 bg-black letterbox. */
              <video
                ref={videoRef}
                src={node.videoUrl}
                aria-label={node.label}
                className="pointer-events-none h-full w-full object-cover"
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
                onClick={toggleMuted}
              >
                {muted ? (
                  <VolumeX className="h-3.5 w-3.5" />
                ) : (
                  <Volume2 className="h-3.5 w-3.5" />
                )}
              </MediaHoverButton>
            )}
            {/* 舞台检视皮 (ADR-115): the time axis ON the stage's bottom
                edge — the in-section strip's successor. The edit overlay
                hides it (cues null — no honest time alignment). */}
            {node.videoUrl && cues && cues.length > 0 ? (
              <StageSkin
                cues={cues}
                duration={duration}
                playhead={playhead}
                onSeek={seek}
                highlight={highlight}
              />
            ) : null}
            {/* 时长角标: the duration rides the stage's bottom-right corner
                (clears the fattened skin); player-chrome formatting
                (formatDuration), never a data row. */}
            {node.videoUrl && duration > 0 ? (
              <span
                aria-hidden
                className="pointer-events-none absolute right-2 bottom-3.5 z-[2] rounded-md bg-black/45 px-1.5 py-1 text-[10px] leading-none text-white tabular-nums backdrop-blur-sm"
              >
                {formatDuration(duration)}
              </span>
            ) : null}
          </div>
        )}
        {textBearing && asset ? (
          <>
            {medialess ? null : (
              <div aria-hidden className="mx-3 h-px shrink-0 bg-foreground/10" />
            )}
            <TranscriptSection
              tx={tx}
              saving={saving}
              onSave={save}
              videoRef={node.videoUrl ? videoRef : undefined}
              playhead={playhead}
              onSeek={seek}
              fill={medialess}
              highlight={highlight}
            />
          </>
        ) : null}
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
            ]}
            menuItems={[
              // ⋯ 菜单全量退役（2026-09-10 用户拍板——所有 toolbar 的 ⋯ 都去掉：
              // open 与悬停放大/卡点击同源，reprocess 暂无召回路径；空数组 =
              // 既有 length 守卫不渲染 ⋯。真有第二操作时往这里加回一行。
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

/** The document node's card (ADR-057 — the plan, the FLORA text-node
 * form). Parked on the same dot grid as the dock, so it takes the
 * dock-surface frost (the canvas's dots read through) + the hairline,
 * never a shadow: the produced text IS the body copy. 全文卡律 (2026-09-10
 * 判词④) + 封顶滚动律 (2026-09-11): the body carries the FULL text — never
 * a clamp, never an ellipsis — and SCROLLS in place past the card's cap
 * (layout.ts DOCUMENT_MAX_H; the text product card's nowheel+nopan
 * posture). Phase 3 Batch A (2026-09-19 判词 1, ADR-070 唯一座位律): the
 * canvas is NOT a Confirmation Seat — the task_book card's in-card confirm
 * (price + Start) is RETIRED; Confirm/Start lives on the dock pill alone,
 * the canvas only reads and reviews. 最小产物尾
 * (C5 已拍板): a text node holding products (the writer card's post-upgrade
 * regression fix) gets a bottom factsbar — the version pager (版本累积现成
 * 语义, the body follows the shown version) + copy + open-inspector; the
 * quote-selection pill stays with the UI batch. */
/** Render-in-flight = the node's OWN busy beat (2026-09-24 user ruling —
 * unify the loading chrome): a clip output whose render job is still on
 * the wire (pending/rendering, no video yet) drives the SAME node wipe and
 * edge packet as status="running". The producing step lands the output row
 * and the node's status flips done while the render runs async — keying
 * the chrome off node.status alone (the 转写-era wiring) read the render
 * beat as a dead black node with silent edges. */
export function nodeRenderActive(node: FlowNode): boolean {
  return (node.outputs ?? []).some(
    (o) =>
      o.type === "clip" &&
      !o.files?.video &&
      (o.render_status === "pending" || o.render_status === "rendering"),
  )
}

/** The legacy text document card (task_book / transcript retired — ADR-113
 * + Workspace 合同 v4.2 C1-b; only pre-v3 legacy rows render here). Read-only
 * body + the minimal product tail. */
function DocumentCard({
  node,
  onOutputAction,
}: {
  node: FlowNode
  onOutputAction?: FlowCardData["onOutputAction"]
}) {
  const { t } = useTranslation()
  const outputs = node.outputs ?? []
  // The version pager's display member: null = the LATEST (the node's
  // spec.text IS the newest version's content — the sync back-write); a
  // flip pins an older version by id (refetch-stable).
  const [displayId, setDisplayId] = useState<string | null>(null)
  const output =
    (displayId ? outputs.find((o) => o.id === displayId) : null) ??
    outputs[outputs.length - 1]
  const shownIdx = Math.max(0, outputs.findIndex((o) => o.id === output?.id))
  const shownContent =
    output && typeof (output.payload as { content?: unknown } | undefined)?.content === "string"
      ? ((output.payload as { content: string }).content || null)
      : null
  const bodyText = shownContent ?? node.spec?.text

  // One running expression with GraphCard: the shared wipe + the incoming
  // edge's packet read this state raw (nodeRenderActive is clip-only —
  // inert here, kept so both cards speak one gate).
  const running = node.status === "running" || nodeRenderActive(node)

  return (
    <div className="flex h-full w-full flex-col">
      <NodeCaption label={node.label} Icon={FileText} />
      <div className="dock-surface relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl ring-foreground/10 ring-1">
        {/* 公用 loading (2026-09-28 用户拍板): running = 左到右擦除 (封顶
            96%) + 入边 packet——卡面零自养 loading 表达。 */}
        {running && <span aria-hidden className="node-fill-wipe" />}
        {/* 收边结构律 (2026-09-13 走查拍板): the padding lives on a WRAPPER
            around the scrollport, never on the scrollport itself — scroll-
            container padding only shows at scroll-end (mid-scroll content
            slides into it), while the wrapper's bottom padding holds the
            scrollport's box itself off the card edge in EVERY scroll state.
            NO scroll-fade (2026-09-24 user ruling): the top/bottom mask read
            as a haze over the document's own text — a hard clip at the inset
            edge is the honest boundary for a reading surface. */}
        <div className="flex min-h-0 flex-1 flex-col p-4">
          <div className="nowheel nopan thin-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain">
            {bodyText ? (
              <p className="text-xs leading-relaxed whitespace-pre-wrap">{bodyText}</p>
            ) : (
              <p className="text-xs leading-relaxed text-muted-foreground">{node.detail}</p>
            )}
          </div>
        </div>
        {output ? (
          // 最小产物尾 (C5): version pager + copy + open-inspector — the
          // bar lives INSIDE the card (no external band — the in-port
          // seats' 16px base never shifts).
          <div className="flex shrink-0 items-center justify-end gap-2 px-4 pb-3">
            {outputs.length > 1 && (
              <VersionPager
                current={shownIdx}
                total={outputs.length}
                onFlip={(delta) => {
                  const next = outputs[shownIdx + delta]
                  if (next) {
                    setDisplayId(next.id === outputs[outputs.length - 1]?.id ? null : next.id)
                  }
                }}
              />
            )}
            <MediaToolbar
              info={[]}
              actions={[
                { action: "copy", Icon: Copy, label: t("chat.copy") },
                { action: "open", Icon: Maximize2, label: t("results.canvas.open") },
              ]}
              menuItems={[]}
              moreLabel={t("results.canvas.more")}
              onAction={(action) => {
                // 打开 OutputInspector = the surface's selection channel
                // (the dossier swap-in, same door as the node click).
                onOutputAction?.(output.id, action as FlowOutputAction)
              }}
            />
          </div>
        ) : null}
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
 * affordances: expand top-LEFT, sound top-RIGHT; the score is hover chrome
 * too on tracked cards (the NLE axis carries no head row — 2026-10-11
 * 走查拍板), a persistent bottom-left badge on the untracked anatomies;
 * quality rides the media's bottom-right; a rendering clip projects its
 * state in place as the BrandLoader (never a spinner, never a status
 * line). */
function MediaProductRegion({
  node,
  output,
  topClipScore,
  onExpandMedia,
  fill,
  videoRef,
  hoverScore,
}: {
  node: FlowNode
  output: Output
  topClipScore?: number
  onExpandMedia?: (nodeId: string, outputId?: string) => void
  /** 无程序区卡 (editor/manual): the media fills the freed program band —
   * flex-1 inside the card body, absorbing the frame cap and the facet
   * strip's growth (letterbox, never a clip); the fixed-px thumb stays the
   * generator anatomy's law. */
  fill?: boolean
  /** The card's product video element (ADR-113 §4): the track stack's lane
   * blocks seek it (`currentTime = out_start` — 只拨头, the ambient-muted
   * law untouched). */
  videoRef?: RefObject<HTMLVideoElement | null>
  /** score 回舞台 hover (2026-10-11 走查拍板): a tracked card reads its
   * score as a hover-revealed badge on the media face (the axis carries no
   * head row); untracked anatomies keep the persistent badge. */
  hoverScore?: boolean
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
  // 全局声音指针 (2026-09-13): same mutex as the asset card — one sound
  // source per project canvas.
  const { muted, toggle: toggleMuted } = useSoundMutex(node.id)
  const clipAspect = output.aspect ?? null
  const wantedThumbPx =
    (clipAspect && PRODUCT_THUMB_PX[clipAspect]) || PRODUCT_THUMB_DEFAULT_PX
  // Never outgrow the born frame (the reservation law, 判词②): a node
  // stamped before the source dims were known keeps its conservative frame —
  // the media caps to the frame's budget (contain slivers return for that
  // legacy/raced case), the next column-mate never bleeds. Frames born with
  // dims are aspect-exact — the cap is inert. graphNodeSize mirrors it.
  // (fill 模式不读这里: the flex region absorbs the frame's shape directly.)
  const frameThumbBudget =
    !fill && node.frame?.h
      ? node.frame.h - PRODUCT_LABEL_PX - PROGRAM_REGION_PX - PRODUCT_TOOLBAR_PX
      : null
  const thumbPx =
    frameThumbBudget != null
      ? Math.min(wantedThumbPx, frameThumbBudget)
      : wantedThumbPx
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
      className={cn(
        "group/media relative",
        fill ? "min-h-0 flex-1" : "shrink-0",
        clipAspect
          ? /* 舞台钉死画幅 (ADR-115): the known-aspect stage is an
               aspect-pinned box centered in the region — card-bg flanks on
               a legacy short frame, full bleed on an aspect-exact one.
               Never a black containment field. */
            "flex items-center justify-center"
          : "bg-muted",
      )}
      style={fill ? undefined : { height: thumbPx }}
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
        /* The aspect-pinned stage: the box hugs the file's own ratio and
           the pixels COVER it — zero letterbox, zero crop when the frame's
           reservation is aspect-exact. Aspect-unknown (legacy) rows keep
           the honest contain fallback on the muted field. */
        <div
          className={cn("relative", clipAspect ? "h-full max-w-full" : "h-full w-full")}
          style={
            clipAspect
              ? { aspectRatio: clipAspect.replace(":", "/") }
              : undefined
          }
        >
          <video
            ref={videoRef}
            src={videoUrl}
            poster={mediaThumb ?? undefined}
            aria-label={node.label}
            className={cn(
              "pointer-events-none h-full w-full",
              clipAspect ? "object-cover" : "object-contain",
            )}
            muted={muted}
            loop
            playsInline
            autoPlay
            preload="metadata"
            disablePictureInPicture
          />
        </div>
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
      {/* Media meta badges: the score rides the bottom-left corner — hover-
          revealed on tracked cards (the NLE axis owns no head row), persistent
          on the untracked anatomies; the top corners belong to the hover
          affordances (expand left, sound right). The duration is NOT a badge
          — it lives in the factsbar below the card (2026-08-17 二轮走查拍板). */}
      {score !== null && !renderFailed && (
        <span
          title={output.score?.reason ?? undefined}
          className={cn(
            "absolute bottom-2 left-2 rounded px-1.5 py-0.5 text-[10px] font-medium",
            topPick ? "bg-primary text-primary-foreground" : "bg-black/70 text-white",
            // Same reveal law as MediaHoverButton — pointer-hover gated,
            // always on under (hover: none) (iPad 触摸, 2026-08-19 R4).
            hoverScore &&
              "opacity-0 transition-opacity group-hover/media:opacity-100 [@media(hover:none)]:opacity-100",
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
          onClick={toggleMuted}
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
 * 改字免费即时, persisted via PUT /outputs; never a program change).
 * 选区引用 (2026-09-11 用户拍板 — 段落级指认): selecting a passage in the
 * read body offers 「引用这段」 — the pin rides into the dock as an @output
 * chip WITH the quoted passage (the agent revises THAT passage; manual
 * editing stays the escape hatch, never the story). The read body is a DIV,
 * never a <button> — buttons swallow text selection (the 09-08 "scrolls +
 * selects directly" posture was silently broken by the button), and a
 * selection-owning click never enters edit mode. */
function TextProductRegion({
  output,
  onQuote,
}: {
  output: Output
  onQuote?: (quote: string) => void
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
  // 选区引用: the live passage selection inside the read body (null = none).
  // Captured on mouse-up; cleared when the document selection collapses or
  // leaves the body.
  const [quoteSelection, setQuoteSelection] = useState<string | null>(null)
  const readBodyRef = useRef<HTMLDivElement>(null)

  /** The selection inside the read body, if any (both ends must live here —
   * a drag ending outside the card is not a quote). */
  const readSelection = useCallback((): string | null => {
    const el = readBodyRef.current
    const sel = window.getSelection()
    if (!el || !sel || sel.isCollapsed || sel.rangeCount === 0) return null
    if (!el.contains(sel.anchorNode) || !el.contains(sel.focusNode)) return null
    const text = sel.toString().replace(/\s+/g, " ").trim()
    return text || null
  }, [])

  useEffect(() => {
    // The pill follows the selection's life: gone when the selection
    // collapses or moves elsewhere (a click into the dock must not leave a
    // stale pill on the card).
    const handler = () => setQuoteSelection((prev) => (readSelection() ? prev : null))
    document.addEventListener("selectionchange", handler)
    return () => document.removeEventListener("selectionchange", handler)
  }, [readSelection])

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

  // nowheel + nopan (2026-09-08 user ruling): the region scrolls + selects
  // DIRECTLY — react-flow's pane gestures yield to elements carrying the
  // classes (wheel → zoom, drag → pan both stay local), so the full body
  // reads in place without the click-to-edit first. The 12-line budget
  // still caps the NODE's height (layout.ts); the body scrolls inside it
  // instead of truncating (clamp retired — scrolling carries the reading
  // burden now).
  const contentClass =
    "nowheel nopan h-full w-full overflow-y-auto overscroll-contain rounded-lg px-3 py-3 text-left text-xs leading-relaxed thin-scroll"

  return (
    <div
      className="relative flex min-h-0 flex-1 flex-col"
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
        <div
          ref={readBodyRef}
          role="button"
          tabIndex={0}
          onClick={(e) => {
            // Entering inline edit is NOT the node-select gesture — a node
            // click selects (the dossier swaps in); the card itself is the
            // reader (in-place scroll + inline edit — the separate reader
            // modal retired 2026-09-09). Same stopPropagation contract as
            // the toolbar buttons. A click that OWNS a text selection is the
            // quote gesture (选区引用), never an edit entry.
            e.stopPropagation()
            if (readSelection()) return
            setEditing(true)
          }}
          onMouseUp={() => {
            // The quote pill appears only when a real passage is selected.
            setQuoteSelection(readSelection())
          }}
          onKeyDown={(e) => {
            // role="button" parity — the retired <button> entered edit mode
            // on Enter/Space; the div must not lose the keyboard path.
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              setEditing(true)
            }
          }}
          className={cn(contentClass, "cursor-text select-text")}
        >
          {title ? (
            <p className="mb-1 line-clamp-1 text-sm font-medium leading-snug">{title}</p>
          ) : null}
          <p className="whitespace-pre-wrap">{body}</p>
          {clipped.length > 0 ? (
            <p className="mt-2 line-clamp-1 text-[10px] text-muted-foreground">
              {clipped.map((h) => `#${h}`).join(" ")}
            </p>
          ) : null}
        </div>
      )}
      {/* 选区引用 pill: pinned to the REGION's bottom-right, never inside the
          scrollport (it would ride the text as it scrolls and clip at the
          overflow edge). */}
      {quoteSelection && onQuote && !editing ? (
        <button
          type="button"
          // mousedown must not collapse the selection before the click
          // reads it; the pill never selects the node (same contract as the
          // toolbar buttons).
          onMouseDown={(e) => e.preventDefault()}
          onClick={(e) => {
            e.stopPropagation()
            // One cap, at birth (选区引用): the passage is user truth; 200
            // chars covers a sentence or two — a longer need is the
            // whole-output mention's job.
            onQuote(quoteSelection.slice(0, 200))
            setQuoteSelection(null)
            window.getSelection()?.removeAllRanges()
          }}
          className="nodrag absolute right-2 bottom-2 rounded-md bg-accent px-2 py-1 text-[11px] text-foreground ring-1 ring-foreground/10 transition-colors hover:bg-accent/70"
        >
          {t("results.canvas.quotePassage")}
        </button>
      ) : null}
    </div>
  )
}

/** The draft/quiet body (ADR-057 §5 — 状态原地表达): the un-run node is a
 * dashed empty region reading its own quotation (「运行后生成 · 约 N 积分」);
 * queued reads 排队中 without the price (already committed); a landed-empty
 * node (research — its product is internal) reads its summary line in the
 * same body. */
/** The one estimate+balance price line (判词② 封装 — the confirm region /
 * the pricing confirm / the draft chip all read it): the 估价诚实面
 * (2026-09-10) — when unquoted nodes ride the fold (transform chains price
 * only once their clips exist, mid-run), the line says so: an all-null
 * total is "Priced at run time" (never the lie "≈ 0"), a partial fold
 * carries the open "+" bound. `balance` = the soft compare (destructive
 * when short). */
function EstimatePriceLine({
  low,
  high,
  unquoted = 0,
  balance,
  className,
}: {
  low: number
  high: number
  unquoted?: number
  balance?: number | null
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <p className={cn("text-xs tabular-nums", className)}>
      {unquoted > 0 && high === 0 ? (
        <span className="text-muted-foreground">{t("results.canvas.estimateAtRun")}</span>
      ) : unquoted > 0 ? (
        low === high
          ? t("results.canvas.estimateOpen", { count: low })
          : t("results.canvas.estimateRangeOpen", { low, high })
      ) : low === high ? (
        t("results.canvas.estimateSingle", { count: low })
      ) : (
        t("credits.range", { low, high })
      )}
      {!(unquoted > 0 && high === 0) && balance != null && (
        <span
          className={cn(
            "ml-1 text-[11px]",
            balance < low ? "text-destructive" : "text-meta-foreground",
          )}
        >
          · {t("credits.balance")} {balance.toLocaleString()}
        </span>
      )}
    </p>
  )
}

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
          {/* A [0,0] fold = a free node (or one whose mid-run children are
              unquoted — materialize's render fan-out) — its face stays
              quiet; only a real price earns the chip (估价诚实面). */}
          {est && (est[0] > 0 || est[1] > 0) ? (
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
          {/* 失败人话行 (2026-09-11): the family's baked line (spec.error —
              user_error_line at fail time) speaks in place; the generic
              「运行失败」 is the fallback for pre-error rows only. */}
          {typeof node.spec?.error === "string" && node.spec.error
            ? node.spec.error
            : t("results.canvas.runFailed")}
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

/** The program region (ADR-057 §5 — the card-face spec; ADR-076 程序区按
 * prototype 门控, C5): GENERATOR cards read their prompt — and on a node
 * that has products (done / stale), the region is DIRECTLY EDITABLE (K4,
 * the prototype's scene-C anatomy): click drafts in place, Enter sends, Esc
 * cancels. Sending does NOT touch the graph — it lifts the new program to
 * the surface's pricing confirmation (锚定子图 + 估价), and only the
 * confirmed turn rides the chat channel (零旁路). EDITOR/MANUAL cards
 * render no prompt area — the composed echo's display side retires ahead
 * of its builder (compose 本体 B5 才拆; the lever row lands with 批 B4) —
 * only the slack absorber keeps the card's flex anatomy. */
function ProgramRegion({
  node,
  editable,
  onPromptEdit,
  pendingProgram,
  promptConfirm,
}: {
  node: FlowNode
  editable?: boolean
  onPromptEdit?: (nodeId: string, text: string) => void
  pendingProgram?: string | null
  promptConfirm?: FlowCardData["promptConfirm"]
}) {
  const { t } = useTranslation()
  const stampedPrompt = node.spec?.prompt
  // 乐观回显 (ADR-058): while the edit is pending (confirm open / stamp in
  // flight), the card face shows the user's verbatim program — sending
  // never reverts the display to the old stamp.
  const prompt = pendingProgram ?? stampedPrompt
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

  // The media card's program region FILLS its reservation (2026-09-13 用户
  // 拍板): the media region above is fixed-px (frame anatomy), so this
  // region grows to absorb the leftover band height — the hover wash covers
  // the whole area, never a white strip under the prompt. Text cards keep
  // shrink-0: their body region is already the flex-1 slack absorber (same
  // for the quiet/draft body's wrapper), so this region sits flush at the
  // card bottom there.
  const firstOutput = (node.outputs ?? [])[0]
  const fillSlack =
    !!firstOutput && firstOutput.type !== "post" && firstOutput.type !== "article"

  // 程序区按 prototype 门控 (ADR-076): only generator cards carry the
  // program region. Editor/manual cards (and the prototype-less
  // transitional words) drop the region AND its reservation from the
  // anatomy — the media region fills the freed band (fill mode), the
  // height math and the in-port corner stack live in layout.ts
  // (graphNodeSize / declaredHandles, 一条律两镜像).
  if (node.spec?.prototype !== "generator") return null
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
        "px-3 py-2 transition-colors",
        fillSlack ? "min-h-0 flex-1" : "shrink-0",
        editable && !editing && !promptConfirm && "cursor-text hover:bg-accent/50",
      )}
      // 2026-09-13 卡面直改入口暂时停用（用户拍板）: the editing anatomy
      // (label + 3-row textarea + send row ≈112px) overflows the 88px
      // program reservation — the send button poked past the card bottom.
      // The click entry is commented out until the editing layout is
      // redesigned; prompt revision still rides the chat dock meanwhile.
      // onClick={(e) => {
      //   if (!editable || editing || promptConfirm) return
      //   // Entering the draft is NOT the node-select gesture.
      //   e.stopPropagation()
      //   setEditing(true)
      // }}
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
      {promptConfirm && !editing ? (
        // 动作住节点内 (判词①): the pricing confirmation docks here — the
        // staged program above (the card face already reads it), the blast
        // chips (锚定子图), the estimate + balance, and the two gestures.
        <div
          className="mt-2 border-t border-foreground/8 pt-2"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
            <span>
              {promptConfirm.blastSingle
                ? t("results.canvas.confirmBlastSingle")
                : t("results.canvas.confirmBlast", { count: promptConfirm.blastLabels.length })}
            </span>
            {promptConfirm.blastLabels.map((label, i) => (
              <span
                key={i}
                className="rounded bg-inset px-1.5 py-0.5 text-[10px] whitespace-nowrap"
              >
                {label}
              </span>
            ))}
          </div>
          <EstimatePriceLine
            className="mt-2"
            low={promptConfirm.low}
            high={promptConfirm.high}
            unquoted={promptConfirm.unquoted}
            balance={promptConfirm.balance}
          />
          <div className="mt-2.5 flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-8"
              onClick={(e) => {
                e.stopPropagation()
                promptConfirm.onCancel()
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button
              size="sm"
              className="h-8"
              onClick={(e) => {
                e.stopPropagation()
                promptConfirm.onConfirm()
              }}
            >
              {t("results.canvas.confirmStart")}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

/** The deliverable card's facet strip (ADR-097 §3/§4) — failure-only chrome
 * (2026-10-09 用户拍板): 失败才展开工序级定位, each failed station gets its
 * own destructive row; a healthy artifact renders NO strip at all (成功安静 —
 * a display-typed deliverable card stays a clean media face, same as the
 * input asset card), so there is no healthy names line and no birth-time
 * frame reservation (runtime rows are absorbed by the flex media region). */
function ArtifactFacetStrip({ artifact }: { artifact: ProjectArtifact }) {
  const { t } = useTranslation()
  const failedIds = new Set(artifact.activity.failed_node_ids)
  const failed = artifact.facets.filter((f) => failedIds.has(f.node_id))
  if (failed.length === 0) return null
  return (
    <div className="shrink-0 border-t border-foreground/8 px-3 py-1.5 text-[11px] leading-snug">
      {failed.map((f) => (
        <p key={f.node_id} className="truncate text-destructive">
          {f.label ? `${f.label} · ` : ""}
          {t("results.canvas.runFailed")}
        </p>
      ))}
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
  onQuoteOutput,
  onExpandMedia,
  onDisplayChange,
  onPromptEdit,
  pendingProgram,
  promptConfirm,
  onLineageHover,
}: {
  node: FlowNode
  selected: boolean
  onOutputAction?: FlowCardData["onOutputAction"]
  onQuoteOutput?: FlowCardData["onQuoteOutput"]
  onExpandMedia?: FlowCardData["onExpandMedia"]
  onDisplayChange?: FlowCardData["onDisplayChange"]
  onPromptEdit?: FlowCardData["onPromptEdit"]
  pendingProgram?: FlowCardData["pendingProgram"]
  promptConfirm?: FlowCardData["promptConfirm"]
  onLineageHover?: FlowCardData["onLineageHover"]
}) {
  const { t } = useTranslation()
  const outputs = node.outputs ?? []
  // The card's product video element — the track stack's lane blocks seek
  // it (ADR-113 §4; the ref lands on MediaProductRegion's <video>).
  const productVideoRef = useRef<HTMLVideoElement>(null)
  // 轨道栈谓词 (ADR-113 §4; layout.ts hasTrackStack — the tool-set mirror of
  // graph_store._TRACKED_CLIP_TOOLS): the two inspection lanes are in the
  // anatomy from birth, so the video in-port's anchor never moves mid-life.
  const tracked = hasTrackStack(node)
  // The pager flips the display AND the action target among the node's
  // products; displayId survives refetches (ids are stable).
  const [displayId, setDisplayId] = useState<string | null>(null)
  // 版本累积 (the version lineage): a re-fill landing NEW products flips
  // the display to the newest version — the revision's arrival is seen in
  // place (原型 C's 2/2). Mount keeps the first (the chain's birth order).
  const seenOutputIdsRef = useRef<Set<string> | null>(null)
  useEffect(() => {
    const ids = new Set(outputs.map((o) => o.id))
    const prev = seenOutputIdsRef.current
    seenOutputIdsRef.current = ids
    if (prev === null) return
    const added = outputs.filter((o) => !prev.has(o.id))
    if (added.length > 0) setDisplayId(added[added.length - 1].id)
  }, [outputs])
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
    // The language fact is earned only where it isn't self-evident (2026-
    // 09-09 走查拍板): a text product's language IS its content — never
    // restate it on the bar; a clip's dub language can't be seen without
    // playing, so media keeps it.
    if (output.language && !isText) {
      info.push(t(`languages.${output.language}`, { defaultValue: output.language }))
    }
    const clipAspect = output.aspect ?? null
    if (clipAspect && clipAspect !== "original") info.push(clipAspect)
    const duration = output.type === "clip" ? ((output.payload.duration as number | undefined) ?? null) : null
    if (duration !== null && duration > 0) info.push(`${duration}s`)
    // 模型事实分面 (2026-10-09 用户拍板): only GENERATOR cards carry the
    // model chips — a prose-program product's model is provenance of the
    // writing; an editor/manual card's models are fixed pipeline facts
    // (never a user choice), which stay in the lightbox's info column
    // (ADR-051 H) and off the bar.
    if (node.spec?.prototype === "generator") {
      const models = (output.model_facts ?? []).map((f) => f.model)
      info.push(...models)
    }
  }
  // An un-run / quiet node carries NO factsbar chips (2026-09-11 用户拍板):
  // its params restate what the caption already names (Translate captions
  // ·FR + a "French" chip = the same fact twice) and the bar holds zero
  // actions until a product lands — a buttonless bar is dead chrome, so the
  // length guard below simply never lets it render. The band's reservation
  // stays in the height math (geometry never shifts).

  const hasVideo = !!output?.files.video
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
    // The primary action speaks the product's verb (2026-09-09 走查拍板):
    // a text product is PASTED somewhere (LinkedIn, a newsletter) — its
    // first action is Copy; media files are downloaded. (A .md download of
    // a post was the old default — retired, nobody opens one.) The second
    // seat is Publish (2026-09-13 用户拍板 — it replaces Delete on the bar:
    // the dossier's two doors moved onto the card when the video-click
    // popup retired; product deletion lost its canvas home with this swap).
    if (isText) {
      actions.push({ action: "copy", Icon: Copy, label: t("chat.copy") })
    } else if (canDownload) {
      actions.push({
        action: "download",
        Icon: Download,
        label: t("results.canvas.download"),
      })
    }
    actions.push({ action: "publish", Icon: Send, label: t("results.canvas.publish") })
  }
  const menuItems: { action: string; label: string }[] = output
    ? [
        // ⋯ 菜单全量退役（2026-09-10 用户拍板——所有 toolbar 的 ⋯ 都去掉；
        // 发布没有回这里——2026-09-13 直接坐上栏）。空菜单 = 既有
        // length 守卫自动不渲染 ⋯。
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

  const running = node.status === "running" || nodeRenderActive(node)
  const failed = node.status === "failed"
  const renderFailed =
    !!output && output.type === "clip" && output.render_status === "failed"

  return (
    <div className="relative flex h-full w-full flex-col">
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
            <TextProductRegion
              output={output}
              // 选区引用: undefined where the surface owns no quote channel
              // (the recipe manual) — the pill never renders there.
              onQuote={
                onQuoteOutput
                  ? (quote) => onQuoteOutput(output.id, quote)
                  : undefined
              }
            />
          ) : (
            <MediaProductRegion
              node={node}
              output={output}
              topClipScore={node.topClipScore}
              onExpandMedia={onExpandMedia}
              fill={!hasProgramRegion(node)}
              videoRef={tracked ? productVideoRef : undefined}
              hoverScore={tracked}
            />
          )
        ) : (
          <div className="flex min-h-0 flex-1 flex-col p-3">
            <QuietBody node={node} />
          </div>
        )}
        {failed && output ? (
          <p className="shrink-0 px-3 py-1.5 text-[11px] leading-snug text-destructive">
            {/* 失败人话行 — same baked line as the quiet body. */}
            {typeof node.spec?.error === "string" && node.spec.error
              ? node.spec.error
              : t("results.canvas.runFailed")}
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
          // ADR-076 闸门 (one truth with the write door's EditPromptOp):
          // the executing body's presence (spec.tool) marks an editable
          // program — a tool-less document never offers the wash. 直改暂停期
          // (b367e94) 只驱动 hover wash 诚实.
          editable={
            !!node.spec?.tool &&
            outputs.length > 0 &&
            node.status !== "queued" &&
            node.status !== "running"
          }
          onPromptEdit={onPromptEdit}
          pendingProgram={pendingProgram}
          promptConfirm={promptConfirm}
        />
        {/* ADR-097 §3/§4: the artifact's facet strip (deliverable cards
            only) — the hidden stations' read-only summary; 失败才展开工序
            级定位. */}
        {node.artifact && node.artifact.facets.length > 0 && (
          <ArtifactFacetStrip artifact={node.artifact} />
        )}
        {/* ADR-115 NLE 检视轴: the inspection timeline — LAST inside the
            card, so the failure chrome above (failure lines / facet strip)
            grows INTO the media's flex and the lane seats (the video
            in-port's anchor, 锚点律) never move. In the anatomy from birth:
            draft renders muted empty lanes. */}
        {tracked && (
          <NleAxis
            output={output}
            videoRef={productVideoRef}
            onLineageHover={onLineageHover}
          />
        )}
      </div>

      {/* The factsbar band under the card (外置律): runtime facts + actions,
          with the version pager STACKED ABOVE the bar when the node holds
          more than one product (2026-09-13 用户拍板 — never beside it: the
          side-by-side row outgrew the card's width). One 8px rhythm
          throughout: card → pager → bar. The band is reserved even while
          quiet; the pager's extra row (PRODUCT_PAGER_PX) lands on the same
          beat as the second version's arrival, one coherent reflow. The
          stale badge rides the bar's left end (可重跑 — the program moved
          after the product landed). */}
      <div
        className={cn(
          "flex shrink-0 flex-col items-center gap-2 pt-2",
          outputs.length > 1 ? "h-[88px]" : "h-[44px]",
        )}
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

/** The port-law handles (ADR-057 §5; 2026-09-08 FLORA 收编——外置圆形锚点):
 * visible typed ports as 28px tinted circles parked FULLY OUTSIDE the card
 * with a 6px gap (the anchor floats off the node — edges attach at the
 * circle's center, the fill hides the line's inner half, so the stroke
 * touches the anchor and never the card face) — in = the consumption
 * region's bottom-left corner, stacked up; out = the production region's
 * top-right corner, stacked down. 出锚语义律 (2026-09-11 用户拍板): the OUT
 * anchor names the NODE'S OWN production medium — one anchor, every out-edge
 * leaves from it — while the IN anchor names what the consumer takes (the
 * edge's carried type); an edge between different media reads "from X to Y"
 * (video's rim → the transcript's T) and the transformation lives on the
 * edge, never as a foreign glyph on the source. Glyph vocabulary
 * (2026-09-09 FLORA 收编): text = the letter T, video = the camera, audio =
 * the waveform; image = the still-visual family (render-side out anchor
 * only, never an edge type). The ctx reference flow has NO glyph of its own
 * (2026-09-12 用户拍板 — the @ anchor is banned from the canvas): it folds
 * into the shared T in-anchor upstream (FlowView port derivation), so a
 * node's left rail only ever shows T / video / audio. Untyped surfaces (the
 * recipe 说明书) keep the legacy invisible pair. */
const PORT_ICON: Record<Exclude<OutPortType, "ctx">, typeof Clapperboard> = {
  video: Video,
  audio: AudioLines,
  text: Type,
  image: ImageIcon,
}

function NodePorts({ node, ports }: { node: FlowNode; ports?: { in: Exclude<GraphEdgeType, "ctx">[]; out: OutPortType[] } }) {
  if (!ports) {
    return (
      <>
        <Handle type="target" position={Position.Left} className="!h-0 !w-0 !opacity-0" />
        <Handle type="source" position={Position.Right} className="!h-0 !w-0 !opacity-0" />
      </>
    )
  }
  // The consumption anchor's VERTICAL seat = the consumed region's BOTTOM-
  // LEFT corner (2026-09-10 用户拍板——红圈裁定，一条角律两个区域). Two
  // in-port seat laws by anatomy:
  //  - GENERATOR media cards: media flows (video/audio) feed the CONTENT
  //    region — their in-ports park 16px above the PROMPT divider, stacking
  //    upward; text/ctx flows feed the PROMPT region, parking 16px above
  //    the factsbar band (document has no band — its region is the card
  //    bottom).
  //  - Media cards WITHOUT a program region (editor/manual/过渡词): the
  //    prompt divider does not exist, so every in-port shares ONE corner
  //    stack at the card's bottom-left, stacking upward in port order
  //    (角落栈 — mirror of layout.ts cornerStackedInPorts/declaredHandles).
  //  - 锚点律 (ADR-113 §5, the track-stack exception): a TRACKED card's
  //    video in-port leaves the corner stack and parks at the VIDEO lane's
  //    Y-center — the edge lands on the lane it feeds. The lanes are in the
  //    anatomy from birth (draft = muted empty rows), so the seat never
  //    moves mid-life; the mirror lives in layout.ts trackVideoPortBasePx.
  // Each family stacks its own ports by 34px (clears the 28px circles); the
  // 34px side offset parks each circle fully outside the card with a 6px
  // gap. The version pager's stacked row grows the factsbar band by
  // PRODUCT_PAGER_PX when the node holds more than one product — every
  // bottom-anchored corner seat rides the band, so the bases shift.
  const pagerPx = (node.outputs?.length ?? 0) > 1 ? PRODUCT_PAGER_PX : 0
  // 词表 v3 (C5): the 全文卡 family (text/table — the C1-dormant values,
  // now the only document anatomy) takes the 16px text-port base; the
  // mirror constant lives in layout.ts inTextPortBasePx (一条律两镜像).
  const inTextBase = node.kind === "text" || node.kind === "table" ? 16 : 60 + pagerPx
  // Bottom furniture of a media-consuming generator card: factsbar band +
  // program region, then the 16px inset into the content region — the
  // corner seat. Media in-ports never occur on the 全文卡 family (the port
  // law's accepts), so one base covers every real seat.
  const inMediaBase = PRODUCT_TOOLBAR_PX + pagerPx + PROGRAM_REGION_PX + 16
  const outBase = 40
  const unified = cornerStackedInPorts(node)
  const inMediaIdx = new Map<string, number>()
  const inTextIdx = new Map<string, number>()
  let cornerCount = 0
  let mediaCount = 0
  let textCount = 0
  for (const t of ports.in) {
    if (t === "video" || t === "audio") inMediaIdx.set(t, mediaCount++)
    else inTextIdx.set(t, textCount++)
  }
  // Edge anchor = the circle's RIM (2026-09-10 ElevenLabs 解剖收编): xyflow
  // natively anchors a handle at its OUTER RIM in the position direction
  // (Position.Right → rect.right, Position.Left → rect.left) — so the visible
  // 28px circle IS the Handle, and the bezier's horizontal tangent exits the
  // source's right rim and enters the target's left rim, plugging INTO the
  // circle's edge (the ElevenLabs silk: the full curve stays visible and
  // docks at the boundary). Center-anchoring (0×0 ghost handle, 09-09) and
  // the center-to-center straight line (09-10 上午) both retired same-day:
  // the first made the stroke dive under the circle fill and read as a miss,
  // the second was a straightjacket for a problem the rim solves natively.
  return (
    <>
      {ports.in.map((type) => {
        const Icon = PORT_ICON[type]
        const isMedia = type === "video" || type === "audio"
        // 角落栈: bottom-anchored at the card's bottom-left, stacking upward
        // in port order; generator cards keep the two-family seats (each
        // region bottom-anchored at its own corner, 34px per sibling).
        // 锚点律 (ADR-113 §5; ADR-115 NLE 轴): a tracked card's video
        // in-port leaves the corner stack for the video lane's Y-center —
        // the edge lands on the lane it feeds (mirror: layout.ts
        // trackVideoPortBasePx) — and does NOT consume a corner-stack slot.
        // Live modifier lanes (below the text lane) raise the seat by
        // NLE_MODIFIER_ROW_PX each on their arrival beat.
        const laneSeat = type === "video" && hasTrackStack(node)
        const base = laneSeat
          ? trackVideoPortBasePx(pagerPx, nleModifierLanes(node))
          : unified
            ? inTextBase + cornerCount++ * 34
            : isMedia
              ? inMediaBase + (inMediaIdx.get(type) ?? 0) * 34
              : inTextBase + (inTextIdx.get(type) ?? 0) * 34
        return (
          <Handle
            key={`in:${type}`}
            id={`in:${type}`}
            type="target"
            position={Position.Left}
            className={cn("flow-port", `flow-port-${type}`)}
            style={{ top: "auto", bottom: base, left: -34 }}
          >
            <Icon />
          </Handle>
        )
      })}
      {ports.out.map((type, i) => {
        // 出锚语义律: the out anchor speaks the node's own medium — ctx is
        // structurally impossible here (productionPort never returns it);
        // the fold is a type-level exhaustiveness guard, never a real case.
        const Icon = PORT_ICON[type === "ctx" ? "text" : type]
        const offset = outBase + i * 34
        return (
          <Handle
            key={`out:${type}`}
            id={`out:${type}`}
            type="source"
            position={Position.Right}
            className={cn("flow-port", `flow-port-${type}`)}
            style={{ top: offset, right: -34 }}
          >
            <Icon />
          </Handle>
        )
      })}
    </>
  )
}

/** The one node card renderer — recipe skins (asset/output thumbs, step
 * pill) and the ADR-057 graph skins (asset / document / graph card).
 * Birth choreography: `flow-node-born` keyframe staggered by `bornIndex`
 * (the real compile order, replayed slowly — ADR-036 补记 3). */
export function FlowNodeCard({ data }: NodeProps<FlowCardNode>) {
  const { node, bornIndex, selected, ports, onOutputAction, onQuoteOutput, onExpandMedia, onAssetAction, onDisplayChange, onPromptEdit, pendingProgram, promptConfirm, onLineageHover, lineageHover } = data
  // Latch the birth frame: the surface drops bornIndex on the next commit
  // (its seen-set absorbs the id), and a follow-up SSE tick can land inside
  // the 420ms keyframe — the class must outlive the animation. A class that
  // stays continuously applied never replays; a remount (the node left the
  // graph and returned) starts a fresh latch.
  const bornLatchRef = useRef<number | undefined>(undefined)
  if (bornIndex !== undefined) bornLatchRef.current = bornIndex
  const born = bornLatchRef.current
  // 词表 v3 媒介卡 (ADR-076, C5 收窄): the three media values by type +
  // the two transitional read-face words (modifier / materialize — their
  // products are media, their program region is gated off below).
  const isGraphCard =
    node.kind === "video" ||
    node.kind === "image" ||
    node.kind === "audio" ||
    node.kind === "modifier" ||
    node.kind === "materialize"
  return (
    <div
      className={cn(
        "h-full w-full cursor-pointer rounded-md text-foreground transition-colors",
        // 状态原地表达 (ADR-057 §5): skipped is the one whole-card dim; a
        // filling node keeps its quiet pulse; draft/queued/failed/stale all
        // speak inside the card, never on it.
        node.status === "skipped" && "opacity-40",
        (node.status === "running" || nodeRenderActive(node)) &&
          "flow-node-running",
        selected && !isGraphCard && "rounded-md ring-2 ring-foreground/40",
      )}
    >
      {/* 锚点测量律 (批C1 提前, 2026-09-13 演示走查): the root stays STATIC —
          xyflow measures the handles (NodePorts) off this box at mount, and
          the born keyframe's transform (translateY+scale) on this element
          pollutes that measurement mid-animation; the final frame is
          identity so no resize ever re-fires and the edges stay crooked
          forever. The birth choreography rides the content wrapper instead;
          ports keep the edge draw-on delay for their entrance. */}
      <NodePorts node={node} ports={ports} />
      <div
        className={cn("h-full w-full", born !== undefined && "flow-node-born")}
        style={born !== undefined ? { animationDelay: `${born * BIRTH_STAGGER_MS}ms` } : undefined}
      >
      {node.kind === "step" ? (
        <StepCard node={node} />
      ) : node.asset ? (
        // 素材卡 (C4 读面后资产行已是媒介 kind — the joined dossier is its
        // birth certificate; the recipe surface's manual asset node carries
        // no dossier and lands on the ThumbCard fallthrough below).
        <ThumbCard
          node={node}
          onExpandMedia={onExpandMedia}
          onAssetAction={onAssetAction}
          lineageHover={lineageHover}
        />
      ) : node.kind === "text" || node.kind === "table" ? (
        // 词表 v3 (ADR-076, C5): text/table derive the 全文卡 anatomy —
        // the table card's own anatomy lands with the UI batch.
        <DocumentCard
          node={node}
          onOutputAction={onOutputAction}
        />
      ) : isGraphCard ? (
        <GraphCard
          node={node}
          selected={selected}
          onOutputAction={onOutputAction}
          onQuoteOutput={onQuoteOutput}
          onExpandMedia={onExpandMedia}
          onDisplayChange={onDisplayChange}
          onPromptEdit={onPromptEdit}
          pendingProgram={pendingProgram}
          promptConfirm={promptConfirm}
          onLineageHover={onLineageHover}
        />
      ) : (
        <ThumbCard
          node={node}
          onExpandMedia={onExpandMedia}
          onAssetAction={onAssetAction}
          lineageHover={lineageHover}
        />
      )}
      </div>
    </div>
  )
}
