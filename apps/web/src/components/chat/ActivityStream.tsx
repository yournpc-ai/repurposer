/** ActivityStream — the append-oriented milestone stream of one agent turn
 * (ADR-087 §3, Lifecycle Phase 2).
 *
 * Rows are the user-safe projection of the loop's internal events: the
 * active row shimmers with a spinner; terminal rows settle static (✓
 * completed / ✗ failed / cancelled struck through — 「被划掉的一步」, the
 * RunTaskList no-op register's cousin). The block STAYS as the turn's
 * settled history after the envelope (U9: ordered history survives the
 * turn's end in-session) and is replaced by the next turn's own stream.
 *
 * This is a visibility surface ONLY — it never gates Canvas / Confirm /
 * Run (对账规则 8), never carries params / results / reasoning (the wire
 * whitelist is {activity_id, seq, kind, status, key}), and its copy keys
 * resolve through i18n with the status-appropriate form (the server sends
 * the active-form key on active frames, the past-tense key on completed
 * ones). */

import { useTranslation } from "react-i18next"
import { Check, Loader2, X } from "lucide-react"

import type { ActivityFramePayload } from "@/lib/chat-stream"
import { cn } from "@/lib/utils"

function ActivityRow({ activity }: { activity: ActivityFramePayload }) {
  const { t } = useTranslation()
  const { status } = activity
  return (
    <div
      className={cn(
        "flex w-full items-center gap-2 text-sm",
        status === "failed" ? "text-destructive" : "text-muted-foreground",
      )}
    >
      {status === "active" ? (
        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
      ) : status === "completed" ? (
        <Check className="h-3.5 w-3.5 shrink-0" />
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
        {/* 工作会话里程碑 (iter-2 ⑥): count rides as the ONLY interpolation
            (the wire whitelist's one extension, N-57) — frames without it
            pass undefined and resolve exactly as before. */}
        {activity.key
          ? t(activity.key, {
              count: activity.count,
              defaultValue: t("chat.thinking"),
            })
          : t("chat.thinking")}
      </span>
    </div>
  )
}

export function ActivityStream({
  activities,
}: {
  activities: ActivityFramePayload[]
}) {
  if (activities.length === 0) return null
  return (
    <div className="flex w-full flex-col gap-1.5 py-1">
      {activities.map((a) => (
        <ActivityRow key={a.activity_id} activity={a} />
      ))}
    </div>
  )
}
