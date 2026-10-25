/** The conversation timeline layer (ADR-108 数组位置律): the persisted
 * array's order IS the render order — this module MAPS rows to units and
 * never re-sorts (no timestamps, no walk keys, no anchors). Pure, no React
 * (the vitest seam); ChatDock composes the units, this module owns the
 * SHAPE (message vs activity vs fold) and the folding projection. */

import type { ActivityRowFrame, OverlayMessage } from "@/components/chat/historyReplay"

/** One unit of the conversation timeline. An unsealed trailing fold is a
 * WORK SEGMENT, not a finished receipt: the dock lets its last current-turn
 * fold carry the live now label in place. Tool settlement alone never seals
 * that segment; the first visible prose fragment or the turn's real terminal
 * state does.
 *
 * rowKey law (行身份): an activity frame's `activity_id` is PER-TURN scoped
 * (two turns both have an "a1"), so it can never key the cross-turn list —
 * the React identity is the HOST MESSAGE ROW's stable id (`birthKey ?? id`,
 * the OverlayMessage render-key law), stamped here at projection time. A
 * settle merges into the same host row, so the identity survives updates; a
 * fold keys by its FIRST MEMBER's rowKey (the segment's head never changes
 * when later members join or settle). The same host carries the client-only
 * frozen work-segment clock; tool duration_ms remains the tool's own fact. */
export type ConversationUnit =
  | { kind: "message"; message: OverlayMessage }
  | {
      kind: "activity"
      activity: ActivityRowFrame
      rowKey: string
      workStartedAtMs?: number
      workEndedAtMs?: number
    }
  | {
      kind: "activityFold"
      rows: ActivityRowFrame[]
      /** First host's own activity stamp, retained even while every member
       * is still active and `rows` is empty (run receipt anchoring reads it). */
      firstActivityAt: string | undefined
      startedAtMs: number | null
      endedAtMs: number | null
      elapsedMs: number | null
      openTail: boolean
      rowKey: string
    }

/** The draft span never enters the flow (2026-09-28 user ruling —
 * 落定即退役): the docked plan card IS the settled evidence. The server
 * never persists draft/run spans (activity.py's frame_persistence), so this
 * filter is the defensive twin for legacy/migrated rows. The storyboard
 * span is the ONE exception (2026-10-17 user ruling — 分镜不是开工): its
 * settle DOES persist with its honest duration — the markdown message is
 * the deliverable, no dock card absorbs the beat. The PATCH variant's pair
 * (storyboardEdit/storyboardEditDone — a targeted edit, never a fresh
 * design) rides the same exception. */
const STORYBOARD_SPAN_KEYS = new Set([
  "chat.activity.storyboard",
  "chat.activity.storyboardDone",
  "chat.activity.storyboardEdit",
  "chat.activity.storyboardEditDone",
])

export function isDraftSpanRow(a: ActivityRowFrame): boolean {
  const key = a.key ?? ""
  if (STORYBOARD_SPAN_KEYS.has(key)) {
    return false
  }
  return a.kind === "draft" && key.startsWith("chat.activity.")
}

/** The run span's settle (「已开工」) is the same hollow shape (落定即退役
 * 同律): the start speech and the RunTaskList receipt are the evidence. */
export function isRunSpanRow(a: ActivityRowFrame): boolean {
  return a.kind === "run" && (a.key ?? "").startsWith("chat.activity.")
}

/** Array map (ADR-108): each message row maps to ONE unit in place —
 * activity-carrying rows become activity units at their array position.
 * An ACTIVE activity enters the walk immediately: its host is the live work
 * segment's seat, so a short first activity never depends on the bottom
 * now-line becoming visible. A CANCELLED attempt retires from the visible
 * walk (automatic retry / stop is not a finished work receipt); its forensic
 * record remains server-side. Real FAILED rows stay visible. Retired draft /
 * run spans keep their existing card / receipt evidence. */
export function buildConversationUnits(
  messages: OverlayMessage[],
): ConversationUnit[] {
  const units: ConversationUnit[] = []
  for (const m of messages) {
    const a = m.activity
    if (a === undefined) {
      units.push({ kind: "message", message: m })
      continue
    }
    if (a.status === "cancelled") continue // abandoned attempt, not a work receipt
    if (isDraftSpanRow(a) || isRunSpanRow(a)) continue // 落定即退役
    units.push({
      kind: "activity",
      activity: a,
      rowKey: m.birthKey ?? m.id,
      workStartedAtMs: m.workStartedAtMs,
      workEndedAtMs: m.workEndedAtMs,
    })
  }
  return units
}

/** 折叠投影 (呈现层纯函数, ADR-110 段聚合——Claude Code 式坍缩 +
 * Flora 解剖): 两个用户可见散文段之间的活动行属于同一个工作段。
 * COMPLETED rows are its durable evidence; an ACTIVE row joins immediately
 * but supplies only the live seat until it settles. An active-only segment
 * therefore has `rows=[]` and a stable host key, never an empty Worked
 * receipt. FAILED rows pass through and break the run; CANCELLED attempts
 * were retired by the array map and neither render nor split a segment.
 *
 * A fold is OPEN while no later user-visible prose / user / QA boundary
 * exists and its client clock has not been sealed. The dock gives the last
 * CURRENT-TURN open fold the live label; earlier failure-separated open
 * fragments stay withheld, so a busy turn can never show a completed fold
 * above a second thinking row. Empty streaming bubbles do not close a
 * segment — received characters are not yet visible speech. A user message
 * closes the previous segment structurally but never supplies its end
 * clock (user think time is not assistant work). */
export function foldActivityUnits(
  units: ConversationUnit[],
  defaultWorkStartedAtMs?: number,
): ConversationUnit[] {
  const out: ConversationUnit[] = []
  let run: Extract<ConversationUnit, { kind: "activity" }>[] = []
  const flush = () => {
    if (run.length > 0) {
      // Active members own the live seat but are not durable evidence yet.
      // They join `rows` in place when their host settles COMPLETED.
      const rows = run
        .filter((u) => u.activity.status === "completed")
        .map((u) => u.activity)
      const startedAtMs = workStart(out, run[0], defaultWorkStartedAtMs)
      const endedAtMs = run[0].workEndedAtMs ?? null
      out.push({
        kind: "activityFold",
        rows,
        firstActivityAt: run[0].activity.at,
        startedAtMs,
        endedAtMs,
        elapsedMs: foldElapsedMs(rows, startedAtMs, endedAtMs),
        openTail: false, // stamped by the reverse boundary pass below
        // The fold's identity is its first member's host-row id: the
        // segment's head never changes when later members join or settle.
        rowKey: run[0].rowKey,
      })
    }
    run = []
  }
  for (const unit of units) {
    if (
      unit.kind === "activity" &&
      (unit.activity.status === "completed" || unit.activity.status === "active")
    ) {
      run.push(unit)
      continue
    }
    flush()
    out.push(unit)
  }
  flush()

  let closedByLaterSpeech = false
  for (let i = out.length - 1; i >= 0; i -= 1) {
    const unit = out[i]
    if (unit.kind === "message" && closesWorkSegment(unit.message)) {
      closedByLaterSpeech = true
      continue
    }
    if (unit.kind === "activityFold") {
      out[i] = {
        ...unit,
        openTail: !closedByLaterSpeech && unit.endedAtMs == null,
      }
    }
  }
  return out
}

/** Only following user-visible prose / a user / QA row closes a work segment
 * structurally. An empty preview is a pinned array position, not visible
 * prose; candidates and other empty structured rows still split the fold
 * grouping without faking a display timestamp. A terminal ERROR row is a
 * system fact, not following prose: the terminal seal owns its clock edge,
 * so the grey row cannot make the preceding fold ineligible first. */
function closesWorkSegment(m: OverlayMessage): boolean {
  if (m.meta === "error") return false
  return m.role === "user" || m.qa !== undefined || m.content.trim().length > 0
}

function validMs(value: number | undefined): value is number {
  return value != null && Number.isFinite(value)
}

function parseMs(value: string | undefined): number | null {
  const parsed = Date.parse(value ?? "")
  return Number.isNaN(parsed) ? null : parsed
}

/** Live start facts only. A user row's own stamp is the send gesture; a QA
 * row uses the client's option-click display stamp; a prose boundary uses
 * its DRAIN stamp so the previous bubble's playback is never billed to the
 * next segment. Server assistant created_at is deliberately NOT a display
 * timestamp. Without one of those facts, an explicit client work boundary
 * wins over the first tool's execute-entry `at`; with neither, that activity
 * timestamp is the honest available start. */
function workStart(
  previous: ConversationUnit[],
  first: Extract<ConversationUnit, { kind: "activity" }>,
  defaultWorkStartedAtMs?: number,
): number | null {
  if (validMs(first.workStartedAtMs)) return first.workStartedAtMs
  // A Start pill has no user / QA archive row. Its actual click can therefore
  // supply the default without outranking a real preceding prose boundary.
  const fallback = validMs(defaultWorkStartedAtMs)
    ? defaultWorkStartedAtMs
    : parseMs(first.activity.at)
  for (let i = previous.length - 1; i >= 0; i -= 1) {
    const unit = previous[i]
    if (unit.kind !== "message") continue
    const m = unit.message
    if (m.role === "user") return parseMs(m.at) ?? fallback
    if (m.qa) {
      return validMs(m.clientVisibleAtMs) ? m.clientVisibleAtMs : fallback
    }
    if (m.content.trim()) {
      return validMs(m.proseDrainedAtMs) ? m.proseDrainedAtMs : fallback
    }
    if (m.candidates || m.meta || m.runId) return fallback
  }
  return fallback
}

/** Completed work's elapsed wall time. A client-sealed segment includes
 * tool work AND the following model wait, ending at the first visible reply
 * fragment (or a prose-less terminal state), then freezes. Unsealed /
 * replayed rows fall back to the observable activity span. Parallel tool
 * durations are NEVER summed into a pretend wall clock; without timestamps
 * the honest fallback is no elapsed (the row renders an action count). */
function foldElapsedMs(
  rows: ActivityRowFrame[],
  startedAtMs: number | null,
  endedAtMs: number | null,
): number | null {
  if (endedAtMs != null) {
    const liveStart = startedAtMs ?? parseMs(rows[0]?.at)
    if (liveStart != null && endedAtMs > liveStart) {
      return endedAtMs - liveStart
    }
  }
  // Replay / legacy rows have no first-visible client fact. Preserve the
  // observable ACTIVITY span rather than stretching it to an assistant
  // created_at or a later user gesture.
  const start = parseMs(rows[0]?.at)
  if (start != null) {
    const last = rows[rows.length - 1]
    const lastAt = parseMs(last?.at)
    if (lastAt != null) {
      const lastEnd = lastAt + (last.duration_ms ?? 0)
      if (lastEnd > start) return lastEnd - start
    }
  }
  return null
}

/** Seal the CURRENT turn's last open work segment at a real display /
 * terminal timestamp. `currentRowKeys` contains HOST MESSAGE ids observed
 * on this turn's row.append/update channel — never per-turn activity_ids,
 * so an old segment with the same "a1" can neither be sealed nor reopened.
 * The clock lives on the first host row, survives fold remounts and later
 * frame merges, and is write-once. History has no such client fact and keeps
 * its honest activity-span fallback. `defaultWorkStartedAtMs` is the actual
 * client gesture for turns without a user / QA row (Start); it never
 * outranks a preceding visible-prose drain boundary. A display-edge seal
 * passes `beforeRowId`: only a fold BEFORE that exact prose row is eligible,
 * so a preceding checkpoint can never seal the activity segment born after
 * it. Terminal seals omit the boundary and close the current trailing fold. */
export function closeWorkSegment(
  messages: OverlayMessage[],
  currentRowKeys: ReadonlySet<string>,
  endedAtMs: number,
  defaultWorkStartedAtMs?: number,
  beforeRowId?: string,
): OverlayMessage[] {
  if (currentRowKeys.size === 0 || !Number.isFinite(endedAtMs)) return messages
  if (beforeRowId != null && !messages.some((m) => m.id === beforeRowId)) {
    return messages
  }
  const units = foldActivityUnits(
    buildConversationUnits(messages),
    defaultWorkStartedAtMs,
  )
  let fold: Extract<ConversationUnit, { kind: "activityFold" }> | undefined
  let crossedBoundary = beforeRowId == null
  for (let i = units.length - 1; i >= 0; i -= 1) {
    const unit = units[i]
    if (!crossedBoundary) {
      if (unit.kind === "message" && unit.message.id === beforeRowId) {
        crossedBoundary = true
      }
      continue
    }
    if (
      unit.kind === "activityFold" &&
      unit.rows.length > 0 && // an active-only attempt is not completed work
      unit.openTail &&
      currentRowKeys.has(unit.rowKey)
    ) {
      fold = unit
      break
    }
  }
  if (!fold) return messages
  let changed = false
  const next = messages.map((m) => {
    if ((m.birthKey ?? m.id) !== fold.rowKey || !m.activity) return m
    if (m.workEndedAtMs != null) return m
    changed = true
    return {
      ...m,
      ...(m.workStartedAtMs == null && fold.startedAtMs != null
        ? { workStartedAtMs: fold.startedAtMs }
        : {}),
      workEndedAtMs: endedAtMs,
    }
  })
  return changed ? next : messages
}

/** The fold's expanded category rows (ADR-110 修订 — 归档归类目):
 * rows sharing one copy key AND asset type merge across the WHOLE segment
 * into ONE ×N category line (the Flora anatomy — 已读网页 ×3), order =
 * first appearance. Instance names are the live phase's speech; the
 * archive speaks categories. A milestone row whose count IS its content
 * (the explore family's artifact counts — count without total) never
 * merges: two rows can't speak one honest count, so each rides as its own
 * entry. Progress beats (count+total = the N/M reading progress) merge
 * and drop the numbering — a settled row has no progress to report. */
export interface FoldCategory {
  kind: ActivityRowFrame["kind"]
  key: string | null
  /** Merge identity member: same key but different asset types are
   * different categories (web_page beats share the base reading key with
   * file beats — the verb fork predates the type). */
  assetType?: string
  repeat: number
  /** A milestone row's own artifact count (merged categories: undefined). */
  count?: number
}

/** The aggregate row's expanded categories (ADR-110 修订). */
export function foldCategories(rows: ActivityRowFrame[]): FoldCategory[] {
  const cats: FoldCategory[] = []
  for (const r of rows) {
    const mergeable = r.count == null || r.total != null
    const hit = mergeable
      ? cats.find(
          (c) =>
            c.key === r.key &&
            c.assetType === r.assetType &&
            c.count === undefined,
        )
      : undefined
    if (hit) {
      hit.repeat += 1
      continue
    }
    cats.push({
      kind: r.kind,
      key: r.key,
      assetType: r.assetType,
      repeat: 1,
      count: mergeable ? undefined : (r.count ?? undefined),
    })
  }
  return cats
}

/** A FAILED row must speak a terminal fact, never the abandoned attempt's
 * progressive label. Explicit failure mirrors keep their specific copy;
 * every active-only / unknown key falls back to the existing honest failure
 * line rather than claiming ongoing work at a terminal failure. */
export function activityFailureKey(key: string | null): string {
  if (key === "chat.activity.repair" || key?.startsWith("chat.inspectingFailed.")) {
    return key
  }
  return "chat.failed"
}

/** The settled surface's category-form key (归档归类目 — 实例名归 live
 * 期): the material reading family's keys interpolate the file's name
 * (`读完 {{name}}`) — the name is the live phase's speech. Settled rows
 * drop the instance name and speak the category, remapping to the
 * name-free `chat.materialCategory` family. The verb fork follows the
 * key's own _video/_audio suffix; web_page rides the beat's asset_type
 * (its row key falls to the base form — the fork predates the web_page
 * type). Every other family is already category-shaped (inspectingDone /
 * explore interpolate no name). */
export function activityCategoryKey(
  key: string | null,
  assetType?: string | null,
): string | null {
  if (key == null) return null
  const m = /^chat\.material\.readingDone(?:Progress)?(_video|_audio)?$/.exec(key)
  if (!m) return key
  const typed = m[1] ?? (assetType === "web_page" ? "_webPage" : "")
  return `chat.materialCategory.reading${typed}`
}
