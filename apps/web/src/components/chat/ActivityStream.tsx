/** ActivityRow — THE one row of the chat world's "现在" (2026-09-24 合一律,
 * user ruling): the agent turn's milestone stream AND the thinking empty
 * state are the same component with the same anatomy — the live dot +
 * shimmer label while live, kind glyph + duration whisper when settled.
 * Register (2026-09-25 user ruling): the row FULLY shares the RunTaskList
 * narrative row's quiet register (StatusLine quiet — "正在准备你的人设…
 * 7s" seat): text-xs, the same 6px live dot, 12px glyphs / chevron — one
 * glance reads one family. Thinking is the row's empty state (kind "think",
 * frontend-synthesized, never on the wire): it never settles and leaves
 * zero history — the next milestone's content simply replaces it in the
 * same mounted row.
 *
 * Rows are the user-safe projection of the loop's internal events: terminal
 * rows settle static (✗ failed / cancelled struck through — 「被划掉的一
 * 步」, the RunTaskList no-op register's cousin) and stay in the flow as
 * the turn's static history (U9), replaced by the next turn's own. An
 * ACTIVE row never interleaves into the timeline — it is the now-line's
 * content (lib/chatTimeline holds the same law for the units walk).
 *
 * This is a visibility surface ONLY — it never gates Canvas / Confirm /
 * Run (对账规则 8), never carries params / results / reasoning (the wire
 * whitelist is {activity_id, seq, kind, status, key, count, at,
 * duration_ms}), and its copy keys resolve through i18n with the
 * status-appropriate form (the server sends the active-form key on active
 * frames, the past-tense key on completed ones).
 *
 * S7/E7 row additions: a genuinely-active span's settle carries its real
 * duration (whisper at the label's left cluster — `formatElapsed` is the
 * ONE copy); a row
 * expands ONLY when it carries payload (the milestone's `count` — E7 诚实
 * 边界: a payload-less row never pretends to be expandable), and the
 * expanded detail stays inside the wire whitelist (the full untruncated
 * copy line + the raw count + the duration) — candidate CONTENT lives on
 * the canvas cards (R1/R3 seats), never copied onto an activity row. */

import { useState } from "react"
import { useTranslation } from "react-i18next"
import {
  ChevronDown,
  ChevronRight,
  Eye,
  PenLine,
  Play,
  RotateCcw,
  X,
  type LucideIcon,
} from "lucide-react"

import type { ActivityFramePayload } from "@/lib/chat-stream"
import type { ActivityRowFrame } from "@/components/chat/historyReplay"
import { activityCategoryKey, foldCategories } from "@/lib/chatTimeline"
import { formatElapsed } from "@/components/chat/RunTaskList"
import { cn } from "@/lib/utils"

/** Per-kind glyphs (2026-09-24 user ruling, OriginCut parity — 查看项目资源
 * → folder, 查看时间线 → eye): the kind is user-semantic (never a tool
 * name), so its icon reads as WHAT the agent did, not as machinery. The
 * completed row's leading mark IS the kind glyph (the generic ✓ said
 * "success", which the settled register already says); live rows keep the
 * 6px dot (the RunTaskList narrative row's own live mark, 2026-09-25 对齐批),
 * failed/cancelled keep the ✗ seat. The `draft` glyph serves the settled
 * storyboard-drafting beat (a born-settled legacy material beat, not a
 * 落定即退役 plan-draft span; the timeline's draft filter keys on
 * chat.activity.* keys and never touches it). */
const KIND_ICONS: Record<ActivityFramePayload["kind"], LucideIcon> = {
  read: Eye,
  draft: PenLine,
  run: Play,
  repair: RotateCcw,
}

/** The now-line's payload (2026-09-24 user ruling — thinking and the
 * activity row are ONE component): a wire milestone, or the think empty
 * state. "think" is frontend-synthesized, NEVER on the wire (the wire
 * whitelist is unchanged); a think row is always active and never settles —
 * it leaves zero history, the next milestone simply replaces its content in
 * the same mounted row (a morph, never a new row). `seq` is the live
 * channel's bookkeeping — array rows (ADR-108) order by position and may
 * omit it. */
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

export function ActivityRow({ activity }: { activity: NowRowPayload }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const { status } = activity
  // 归档归类目 (ADR-110 修订): a COMPLETED row drops the instance name and
  // speaks the category (the material reading family's keys remap to the
  // name-free materialCategory form) — the filename was the live phase's
  // speech. failed/cancelled rows keep the name: which file failed IS the
  // failure's content.
  const settled = status === "completed"
  const labelKey = settled
    ? activityCategoryKey(activity.key, activity.assetType)
    : activity.key
  const label = labelKey
    ? // 工作会话里程碑 (iter-2 ⑥): count rides as the ONLY interpolation
      // (the wire whitelist's one extension, N-57) — frames without it
      // pass undefined and resolve exactly as before. `name` joins for the
      // frontend-synthesized think beats (the material's filename), never
      // for wire frames.
      t(labelKey, {
        count: activity.count,
        total: settled ? undefined : activity.total,
        name: settled ? undefined : activity.name,
        // 未知键兜底分态：进行中的行回 "Thinking…" 诚实；已落定的行回
        // 中性 "Done" —— 旧资源包遇到新键时若回 "Thinking…"，一条已完成
        // 的行会谎称还在进行（素材待命完成帧实测事故）。
        defaultValue: t(status === "active" ? "chat.thinking" : "chat.completed"),
      })
    : t("chat.thinking")
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
          status === "failed" ? "text-destructive" : "text-muted-foreground",
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
          // failed / cancelled share the ✗ seat — destructive says failure,
          // the strike-through says the attempt was discarded.
          <X className="h-3 w-3 shrink-0" />
        )}
        <span
          className={cn(
            "min-w-0 truncate",
            status === "active" && "shimmer",
            status === "cancelled" && "line-through",
            // Hover brightens the label only — no bg wash; failed rows keep
            // their destructive ink.
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

/** The aggregate row (ADR-110 段聚合, 修订: Flora 解剖 — 折叠说总量,
 * 展开说分解): a settled segment folds into ONE quiet total — 「工作了
 * 2m 7s」; the elapsed is the ONLY collapsed fact (never a fragment
 * digest — the truncated-URL pathology dies at the root, the single-line
 * truncate stays as the dormant guard). Expanded = the category
 * decomposition (foldCategories): rows sharing one copy key merge across
 * the whole segment into a ×N category line (已读网页 ×3) — glyph +
 * category text + ×N at the far right, NO per-row durations (telemetry
 * 不归消费面; the total already rode the header). Ink tiers: the category
 * rows muted, glyphs + counts meta — the header's resting pose reads
 * muted like all chrome (hover / expanded brightens it, never the resting
 * state). The chevron follows the OS disclosure convention (> collapsed,
 * label; the whole row is the tap target. Elapsed 不可测 (存量行无时间
 * 戳) falls back to the honest action count.
 *
 * 物化时机律: this component only ever sees a CLOSED segment — a fold
 * whose boundary doesn't exist yet (the turn's prose hasn't landed) is
 * withheld by the renderer while the turn is busy and materializes with
 * the closing prose (the summary's clock ends where the summary
 * appears); an orphaned turn's tail arrives here once busy ends, on the
 * fallback clock. failed/cancelled rows never
 * reach here — they stay visible as their own struck-through rows. */
export function FoldedActivityRow({
  rows,
  elapsedMs,
}: {
  rows: ActivityRowFrame[]
  elapsedMs?: number | null
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const elapsed = elapsedMs != null ? formatElapsed(elapsedMs) : null
  const label = elapsed
    ? t("chat.activityFold.worked", { elapsed })
    : t("chat.activityFold.actionCount", { count: rows.length })
  const cats = foldCategories(rows)
  return (
    <div className="flex w-full flex-col gap-1">
      <div
        className={cn(
          // Flora 同构: the summary hugs its content (bare label + chevron
          // adjacent — no glyph, never a full-width row with a far-right
          // chevron); the button metrics are Flora's (h-7, gap-1.5); the
          // expanded rows below keep the flow width.
          "-mx-1.5 -my-0.5 group/row flex h-7 w-fit max-w-full cursor-pointer select-none items-center gap-1.5 rounded-md px-1.5 text-xs",
        )}
        role="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {/* Resting quiet (muted — chrome, not prose); the brighten is the
            hover / expanded state, never the resting pose. */}
        <span
          className={cn(
            "min-w-0 truncate text-muted-foreground transition-colors group-hover/row:text-foreground",
            open && "text-foreground",
          )}
        >
          {label}
        </span>
        {open ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-meta-foreground" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0 text-meta-foreground" />
        )}
      </div>
      {open && (
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
      )}
    </div>
  )
}
