/** Chat activity presentation has two row families:
 *
 * - WorkSegmentRow owns ONE continuous work segment in both poses: live
 *   Thinking / current milestone, then the settled aggregate receipt at the
 *   SAME timeline unit. Completed tools are facts inside that segment; their
 *   settlement never seals it. The first visible following prose fragment
 *   or a real terminal state does.
 * - ActivityRow renders a standalone terminal failure fact. Cancelled
 *   attempts retire in the timeline projection instead of leaving an error
 *   carcass; a real failure keeps one calm, honest terminal row.
 *
 * Rows are the user-safe projection of the loop's internal events. They never
 * gate Canvas / Confirm / Run, never carry params / results / reasoning, and
 * resolve their copy through i18n. Tool duration_ms remains the tool's own
 * duration; the work segment's separate client wall clock includes the model
 * wait until visible reply and freezes at that display edge. */

import { useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"
import {
  ChevronDown,
  ChevronRight,
  Eye,
  PenLine,
  Play,
  RotateCcw,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react"

import type { ActivityFramePayload } from "@/lib/chat-stream"
import type { ActivityRowFrame } from "@/components/chat/historyReplay"
import { activityCategoryKey, activityFailureKey, foldCategories } from "@/lib/chatTimeline"
import { formatElapsed } from "@/components/chat/workTiming"
import { cn } from "@/lib/utils"

/** Per-kind glyphs (2026-09-24 user ruling, OriginCut parity — 查看项目资源
 * → folder, 查看时间线 → eye): the kind is user-semantic (never a tool
 * name), so its icon reads as WHAT the agent did, not as machinery. The
 * completed row's leading mark IS the kind glyph (the generic ✓ said
 * "success", which the settled register already says); live rows keep the
 * 6px dot (the RunTaskList narrative row's own live mark, 2026-09-25 对齐批).
 * A real failure keeps a quiet alert seat, never a struck-through live
 * label. The `draft` glyph serves the settled storyboard-drafting beat (a
 * born-settled legacy material beat, not a 落定即退役 plan-draft span; the
 * timeline's draft filter keys on chat.activity.* keys and never touches
 * it). */
const KIND_ICONS: Record<ActivityFramePayload["kind"], LucideIcon> = {
  read: Eye,
  draft: PenLine,
  run: Play,
  repair: RotateCcw,
}

/** The live label payload: a wire milestone, or the frontend-synthesized
 * think empty state. "think" is NEVER on the wire and has no durable row of
 * its own; it simply gives the current work segment its base label. `seq`
 * is live-channel bookkeeping — array rows order by position and may omit
 * it. */
export type NowRowPayload = Omit<ActivityFramePayload, "kind" | "seq"> & {
  kind: ActivityFramePayload["kind"] | "think"
  seq?: number
  /** Think-state interpolation (the material beats name the file being
   * read); wire milestones never carry it. */
  name?: string
  /** Batch-progress interpolation (the persisted reading beat's "N/M" —
   * 2026-09-24 素材节拍入库): replay-synthesized beat rows carry it, wire
   * frames never do. */
  total?: number
  /** The material beat's asset type (replay-only, never on the wire): the
   * settled category form forks web_page off it (activityCategoryKey). */
  assetType?: string
}

function activityText(activity: NowRowPayload, t: TFunction): string {
  const { status } = activity
  // 归档归类目: a COMPLETED row drops the instance name and speaks the
  // category. A FAILED row uses terminal failure copy (an explicit failure
  // mirror may keep the target's name), never the active progressive label.
  const settled = status === "completed"
  const labelKey = settled
    ? activityCategoryKey(activity.key, activity.assetType)
    : status === "failed"
      ? activityFailureKey(activity.key)
      : activity.key
  return labelKey
    ? t(labelKey, {
        count: activity.count,
        total: settled ? undefined : activity.total,
        name: settled ? undefined : activity.name,
        // Unknown keys degrade by status: active thinks, failed says so,
        // and only a genuinely completed row may claim completion.
        defaultValue: t(
          status === "active"
            ? "chat.thinking"
            : status === "failed"
              ? "chat.failed"
              : "chat.completed",
        ),
      })
    : t("chat.thinking")
}

export function ActivityRow({ activity }: { activity: NowRowPayload }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const { status } = activity
  const label = activityText(activity, t)
  // E7 诚实边界: expandability IS the payload fact (a count-carrying
  // milestone) — never a chrome affordance on an empty row. Live rows never
  // expand (2026-09-24: the now-line's transient count — "reading N files" —
  // is the label itself, not a payload to unfold). Progress beats
  // (count+total = the N/M batch index) never expand either — a batch index
  // is no payload, and the settled category label no longer carries it.
  const expandable =
    activity.count != null && activity.total == null && status !== "active"
  const duration =
    status !== "active" && activity.duration_ms != null
      ? formatElapsed(activity.duration_ms)
      : null
  // think rows are always active → the spinner seat — so the glyph lookup
  // never sees "think"; the guard is for the type, not the moment.
  const KindIcon = activity.kind === "think" ? null : KIND_ICONS[activity.kind]
  return (
    <div className="flex w-full flex-col gap-1">
      <div
        className={cn(
          // Flora 体感 (flora-parity-ui D4①): the padded hit area reaches 6px
          // past the label via the negative margin (the text column never
          // shifts). Hover NEVER washes the row — expandable rows keep their
          // pointer + click toggle, and hover only brightens the label text.
          // Row metrics = the Flora tools-row anatomy: min-h-8, gap-2.5.
          "-mx-1.5 -my-0.5 group/row flex min-h-8 w-full items-center gap-2.5 rounded-md px-1.5 py-0.5 text-xs transition-colors",
          "text-muted-foreground",
          expandable && "cursor-pointer select-none",
        )}
        role={expandable ? "button" : undefined}
        aria-expanded={expandable ? open : undefined}
        onClick={expandable ? () => setOpen((v) => !v) : undefined}
      >
        {status === "active" ? (
          // The live mark = the RunTaskList narrative row's own dot
          // (2026-09-25 对齐批 — one live register across the flow). The dot
          // RIDES the settled glyphs' 12px seat, centered (2026-09-27: the
          // bare 6px span left-shifted live labels 6px against settled
          // rows), and takes the label's own ink — bg-primary's solid black
          // read as a second register next to the muted text (user ruling).
          <span className="flex h-3 w-3 shrink-0 items-center justify-center">
            <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
          </span>
        ) : status === "completed" && KindIcon ? (
          <KindIcon className="h-3 w-3 shrink-0" />
        ) : (
          // A real failure is a quiet terminal fact. Cancelled attempts
          // normally retire before this component; none becomes a crossed-out
          // live label.
          <TriangleAlert className="h-3 w-3 shrink-0" />
        )}
        <span
          className={cn(
            "min-w-0 truncate",
            status === "active" && "shimmer",
            // Hover brightens ordinary labels only; a failure stays quiet.
            status !== "failed" &&
              "transition-colors group-hover/row:text-foreground",
          )}
        >
          {label}
        </span>
        {/* Left-cluster duration (2026-09-24 user ruling, OriginCut parity —
            "查看时间线 · 893ms"): the elapsed rides the label with a ·
            separator in the same quiet register, nothing floats right. */}
        {duration && (
          <span className="shrink-0 text-xs tabular-nums text-meta-foreground">
            · {duration}
          </span>
        )}
        {expandable &&
          // The OS disclosure convention (> collapsed, ⌄ open) — the row
          // IS the tap target.
          (open ? (
            <ChevronDown className="ml-auto h-3 w-3 shrink-0" />
          ) : (
            <ChevronRight className="ml-auto h-3 w-3 shrink-0" />
          ))}
      </div>
      {expandable && open && (
        <div className="ml-5 flex flex-col gap-0.5 text-xs text-muted-foreground">
          <span className="whitespace-pre-wrap">{label}</span>
          <span className="tabular-nums text-meta-foreground">
            {t("chat.activityMeta.count", { count: activity.count })}
            {duration ? ` · ${duration}` : ""}
          </span>
        </div>
      )}
    </div>
  )
}

/** One work segment in BOTH poses, shared by chat activities and background
 * runs. The header owns the lifecycle; each adapter owns its details. Chat
 * keeps latent tool rows while live and category rows when settled. A run
 * may keep its live step tree visible, then fold the same tree at the seal.
 *
 * Disclosure overrides are pose-scoped: a live user's toggle survives a
 * running → reviewing handoff, but cannot keep the settled row expanded for
 * one extra frame. A post-settle toggle belongs to the settled pose. */
export function WorkSegmentRow({
  rows = [],
  elapsedMs,
  activity = null,
  liveLabel,
  liveTrailing = null,
  liveDetails,
  details,
  settledLabel,
  settledLeading = null,
  failed = false,
}: {
  rows?: ActivityRowFrame[]
  elapsedMs?: number | null
  activity?: NowRowPayload | null
  /** Run adapters already own a builder-written live label; chat passes an
   * activity instead. Either fact makes the row live. */
  liveLabel?: ReactNode
  liveTrailing?: ReactNode
  liveDetails?: ReactNode
  /** Settled details default to chat's category projection. */
  details?: ReactNode
  /** Optional read fallback when a run has no honest elapsed span. */
  settledLabel?: ReactNode
  settledLeading?: ReactNode
  failed?: boolean
}) {
  const { t } = useTranslation()
  const live = activity !== null || liveLabel != null
  const hasLiveDetails = liveDetails != null
  const expandable = live ? hasLiveDetails : details != null || rows.length > 0
  const [openOverride, setOpenOverride] = useState<{
    live: boolean
    open: boolean
  } | null>(null)
  const open =
    openOverride && openOverride.live === live
      ? openOverride.open
      : live && hasLiveDetails
  const elapsed = !live && elapsedMs != null ? formatElapsed(elapsedMs) : null
  const label = live
    ? (liveLabel ?? (activity ? activityText(activity, t) : t("chat.thinking")))
    : (settledLabel ??
      (elapsed
        ? t("chat.activityFold.worked", { elapsed })
        : t("chat.activityFold.actionCount", { count: rows.length })))
  const cats = foldCategories(rows)
  return (
    <div className="flex w-full flex-col gap-1">
      <div
        className={cn(
          "-mx-1.5 -my-0.5 group/row flex items-center rounded-md px-1.5 text-xs text-muted-foreground transition-colors",
          live
            ? "min-h-8 w-full gap-2.5 py-0.5"
            : "h-7 w-fit max-w-full gap-1.5",
          expandable && "cursor-pointer select-none",
        )}
        role={expandable ? "button" : undefined}
        aria-expanded={expandable ? open : undefined}
        onClick={
          expandable
            ? () => setOpenOverride({ live, open: !open })
            : undefined
        }
      >
        {live ? (
          <span className="flex h-3 w-3 shrink-0 items-center justify-center">
            <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
          </span>
        ) : (
          settledLeading
        )}
        <span
          className={cn(
            "min-w-0 truncate transition-colors",
            live && "shimmer",
            !live && failed
              ? "text-destructive"
              : "group-hover/row:text-foreground",
            !live && expandable && open && !failed && "text-foreground",
          )}
        >
          {label}
        </span>
        {live && liveTrailing ? (
          <span className="shrink-0 tabular-nums text-meta-foreground">
            · {liveTrailing}
          </span>
        ) : null}
        {expandable &&
          (open ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-meta-foreground" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-meta-foreground" />
          ))}
      </div>
      {expandable && open
        ? live
          ? liveDetails
          : (details ?? (
              <div className="flex w-full flex-col gap-1">
                {cats.map((c, i) => {
                  const Glyph = KIND_ICONS[c.kind] ?? KIND_ICONS.read
                  const key = activityCategoryKey(c.key, c.assetType)
                  const catLabel = key
                    ? t(key, {
                        count: c.count,
                        defaultValue: t("chat.completed"),
                      })
                    : t("chat.completed")
                  return (
                    <div
                      key={i}
                      className="-mx-1.5 flex min-h-8 w-full items-center gap-2.5 rounded-md px-1.5 py-0.5 text-xs"
                    >
                      <Glyph className="h-3 w-3 shrink-0 text-meta-foreground" />
                      <span className="min-w-0 truncate text-muted-foreground">
                        {catLabel}
                      </span>
                      {c.repeat > 1 && (
                        <span className="ml-auto shrink-0 tabular-nums text-meta-foreground">
                          ×{c.repeat}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            ))
        : null}
    </div>
  )
}
