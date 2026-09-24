/** ActivityRow — THE one row of the chat world's "现在" (2026-09-24 合一律,
 * user ruling): the agent turn's milestone stream AND the thinking empty
 * state are the same component with the same anatomy — spinner + shimmer
 * label while live, kind glyph + duration whisper when settled. Thinking is
 * the row's empty state (kind "think", frontend-synthesized, never on the
 * wire): it never settles and leaves zero history — the next milestone's
 * content simply replaces it in the same mounted row.
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
  Eye,
  Loader2,
  PenLine,
  Play,
  RotateCcw,
  X,
  type LucideIcon,
} from "lucide-react"

import type { ActivityFramePayload } from "@/lib/chat-stream"
import { formatElapsed } from "@/components/chat/RunTaskList"
import { cn } from "@/lib/utils"

/** Per-kind glyphs (2026-09-24 user ruling, OriginCut parity — 查看项目资源
 * → folder, 查看时间线 → eye): the kind is user-semantic (never a tool
 * name), so its icon reads as WHAT the agent did, not as machinery. The
 * completed row's leading mark IS the kind glyph (the generic ✓ said
 * "success", which the settled register already says); live rows keep the
 * spinner, failed/cancelled keep the ✗ seat. */
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
 * the same mounted row (a morph, never a new row). */
export type NowRowPayload = Omit<ActivityFramePayload, "kind"> & {
  kind: ActivityFramePayload["kind"] | "think"
  /** Think-state interpolation (the material beats name the file being
   * read); wire milestones never carry it. */
  name?: string
  /** Batch-progress interpolation (the persisted reading beat's "N/M" —
   * 2026-09-24 素材节拍入库): replay-synthesized beat rows carry it, wire
   * frames never do. */
  total?: number
}

export function ActivityRow({ activity }: { activity: NowRowPayload }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const { status } = activity
  const label = activity.key
    ? // 工作会话里程碑 (iter-2 ⑥): count rides as the ONLY interpolation
      // (the wire whitelist's one extension, N-57) — frames without it
      // pass undefined and resolve exactly as before. `name` joins for the
      // frontend-synthesized think beats (the material's filename), never
      // for wire frames.
      t(activity.key, {
        count: activity.count,
        total: activity.total,
        name: activity.name,
        defaultValue: t("chat.thinking"),
      })
    : t("chat.thinking")
  // E7 诚实边界: expandability IS the payload fact (a count-carrying
  // milestone) — never a chrome affordance on an empty row. Live rows never
  // expand (2026-09-24: the now-line's transient count — "reading N files" —
  // is the label itself, not a payload to unfold).
  const expandable = activity.count != null && status !== "active"
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
          "flex w-full items-center gap-2 text-sm",
          status === "failed" ? "text-destructive" : "text-muted-foreground",
          expandable && "cursor-pointer select-none",
        )}
        role={expandable ? "button" : undefined}
        aria-expanded={expandable ? open : undefined}
        onClick={expandable ? () => setOpen((v) => !v) : undefined}
      >
        {status === "active" ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
        ) : status === "completed" && KindIcon ? (
          <KindIcon className="h-3.5 w-3.5 shrink-0" />
        ) : (
          // failed / cancelled share the ✗ seat — destructive says failure,
          // the strike-through says the attempt was discarded.
          <X className="h-3.5 w-3.5 shrink-0" />
        )}
        <span
          className={cn(
            "min-w-0 truncate",
            status === "active" && "shimmer",
            status === "cancelled" && "line-through",
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
        {expandable && (
          <ChevronDown
            className={cn(
              "ml-auto h-3.5 w-3.5 shrink-0 transition-transform",
              open && "rotate-180",
            )}
          />
        )}
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
