/** ActivityRow — one row of the agent turn's milestone stream (ADR-087 §3,
 * Lifecycle Phase 2; iter-3 S7: the fixed bottom block RETIRED into the
 * message flow — rows render at their real moments via lib/chatTimeline's
 * single-stream interleave, this module owns the ROW only).
 *
 * Rows are the user-safe projection of the loop's internal events: the
 * active row shimmers with a spinner; terminal rows settle static (✓
 * completed / ✗ failed / cancelled struck through — 「被划掉的一步」, the
 * RunTaskList no-op register's cousin). A settled turn's rows stay in the
 * flow as its static history (U9) and are replaced by the next turn's own.
 *
 * This is a visibility surface ONLY — it never gates Canvas / Confirm /
 * Run (对账规则 8), never carries params / results / reasoning (the wire
 * whitelist is {activity_id, seq, kind, status, key, count, at,
 * duration_ms}), and its copy keys resolve through i18n with the
 * status-appropriate form (the server sends the active-form key on active
 * frames, the past-tense key on completed ones).
 *
 * S7/E7 row additions: a genuinely-active span's settle carries its real
 * duration (whisper, right side — `formatElapsed` is the ONE copy); a row
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

export function ActivityRow({ activity }: { activity: ActivityFramePayload }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const { status } = activity
  const label = activity.key
    ? // 工作会话里程碑 (iter-2 ⑥): count rides as the ONLY interpolation
      // (the wire whitelist's one extension, N-57) — frames without it
      // pass undefined and resolve exactly as before.
      t(activity.key, {
        count: activity.count,
        defaultValue: t("chat.thinking"),
      })
    : t("chat.thinking")
  // E7 诚实边界: expandability IS the payload fact (a count-carrying
  // milestone) — never a chrome affordance on an empty row.
  const expandable = activity.count != null
  const duration =
    status !== "active" && activity.duration_ms != null
      ? formatElapsed(activity.duration_ms)
      : null
  const KindIcon = KIND_ICONS[activity.kind]
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
        ) : status === "completed" ? (
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
