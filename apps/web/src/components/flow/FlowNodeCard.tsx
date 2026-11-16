import { Handle, Position, type Node, type NodeProps } from "@xyflow/react"
import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from "react"
import { createPortal } from "react-dom"
import {
  AudioLines,
  Clapperboard,
  Download,
  FileText,
  Image as ImageIcon,
  Maximize2,
  MoreHorizontal,
  PencilLine,
  Type,
  Video,
  Volume2,
  VolumeX,
} from "lucide-react"
import { useTranslation } from "react-i18next"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { fetchAssetTranscript, putAssetTranscript, type AssetTranscript } from "@/lib/api"
import { cn, formatDuration } from "@/lib/utils"
import type { GraphEdgeType } from "@/lib/types"

import { ASSET_TEXT_OUT_BOTTOM_PX, BIRTH_STAGGER_MS, TRANSCRIPT_SECTION_PX } from "./layout"
import { useSoundMutex } from "./sound-mutex"
import type {
  FlowAssetAction,
  FlowAssetInfo,
  FlowNode,
  LineageHover,
  OutPortType,
} from "./types"

export interface FlowCardData extends Record<string, unknown> {
  node: FlowNode
  bornIndex?: number
  selected: boolean
  ports?: { in: Exclude<GraphEdgeType, "ctx">[]; out: OutPortType[] }
  onAssetAction?: (asset: FlowAssetInfo, action: FlowAssetAction) => void
  onExpandMedia?: (nodeId: string) => void
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
    <div className="dock-surface flex items-center gap-1 rounded-lg p-1 border border-subtle">
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

/** Per-type corner-label icons (the node's type glyph, top-left). Also the
 * lightbox's type chip icon source. */
const MANUAL_NODE_ICON: Record<string, typeof FileText> = {
  text: FileText,
  table: FileText,
  image: ImageIcon,
  video: Clapperboard,
  audio: AudioLines,
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
              className="nodrag absolute right-1 bottom-1 rounded-md bg-accent px-2 py-1 text-[11px] text-foreground transition-colors hover:bg-accent/70"
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
      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg bg-card border border-subtle">
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

function GraphCard({ node, selected }: { node: FlowNode; selected: boolean }) {
  const text = node.spec?.prompt ?? node.spec?.text ?? node.detail ?? ""
  return (
    <div className="relative flex h-full w-full flex-col">
      <NodeCaption label={node.label} Icon={MANUAL_NODE_ICON[node.kind] ?? FileText} />
      <div className={cn(
        "flex min-h-0 flex-1 overflow-hidden rounded-lg bg-card p-3",
        selected ? "outline-2 outline-foreground/40" : "border border-subtle",
      )}>
        <p className="overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-foreground">
          {text}
        </p>
      </div>
    </div>
  )
}

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
  let outStackCount = 0
  return (
    <>
      {ports.in.map((type, index) => {
        const Icon = PORT_ICON[type]
        return (
          <Handle
            key={`in:${type}`}
            id={`in:${type}`}
            type="target"
            position={Position.Left}
            className={cn("flow-port", `flow-port-${type}`)}
            style={{ top: "auto", bottom: 16 + index * 34, left: -34 }}
          >
            <Icon />
          </Handle>
        )
      })}
      {ports.out.map((type) => {
        const Icon = PORT_ICON[type === "ctx" ? "text" : type]
        const assetType = node.asset?.type
        const regionSeat = type === "text" && (assetType === "video" || assetType === "audio")
        const offset = regionSeat ? 0 : 40 + outStackCount++ * 34
        return (
          <Handle
            key={`out:${type}`}
            id={`out:${type}`}
            type="source"
            position={Position.Right}
            className={cn("flow-port", `flow-port-${type}`)}
            style={regionSeat
              ? { top: "auto", bottom: ASSET_TEXT_OUT_BOTTOM_PX, right: -34 }
              : { top: offset, right: -34 }}
          >
            <Icon />
          </Handle>
        )
      })}
    </>
  )
}

/** Asset media/transcript and ordinary manual nodes share this card renderer. */
export function FlowNodeCard({ data }: NodeProps<FlowCardNode>) {
  const { node, bornIndex, selected, ports, onExpandMedia, onAssetAction, lineageHover } = data
  const bornLatchRef = useRef<number | undefined>(undefined)
  if (bornIndex !== undefined) bornLatchRef.current = bornIndex
  const born = bornLatchRef.current
  return (
    <div
      data-flow-node-id={node.id}
      className={cn(
        "h-full w-full cursor-pointer rounded-md text-foreground transition-colors",
        selected && !node.asset && "rounded-md outline-2 outline-foreground/40",
      )}
    >
      <NodePorts node={node} ports={ports} />
      <div
        className={cn("h-full w-full", born !== undefined && "flow-node-born")}
        style={born !== undefined ? { animationDelay: `${born * BIRTH_STAGGER_MS}ms` } : undefined}
      >
        {node.asset ? (
          <ThumbCard
            node={node}
            onExpandMedia={onExpandMedia}
            onAssetAction={onAssetAction}
            lineageHover={lineageHover}
          />
        ) : (
          <GraphCard node={node} selected={selected} />
        )}
      </div>
    </div>
  )
}
