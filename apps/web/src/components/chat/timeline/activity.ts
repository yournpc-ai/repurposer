/** Activity-span filtering and work-segment folding. Pure presentation
 * projection: no React, transport, or layout ownership. */

import type {
  ActivityRowFrame,
  ConversationUnit,
  OverlayMessage,
  VideoReviewReceipt,
} from "./types"
import { parseActivityReceipt } from "./history"

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
  // The video family's pairs (Video Project phase B) ride the same
  // exception: the storyboard card is the deliverable, no dock card
  // absorbs the beat, so the settle persists with its honest duration.
  "chat.activity.videoDesign",
  "chat.activity.videoDesignDone",
  "chat.activity.videoRevise",
  "chat.activity.videoReviseDone",
  "chat.activity.videoReview",
  "chat.activity.videoReviewDone",
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

/** 折叠投影 (呈现层纯函数, ADR-110 段聚合——Claude Code 式坍缩 +
 * Flora 解剖): 两个用户可见散文段之间的活动行属于同一个工作段。
 * COMPLETED rows are its durable evidence; an ACTIVE row joins immediately
 * but supplies only the live seat until it settles. An active-only segment
 * therefore has `rows=[]` and a stable host key, never an empty Worked
 * receipt. A FAILED row adjacent to the current run becomes that segment's
 * terminal fact instead of a second top-level status; an isolated failure
 * still passes through. CANCELLED attempts were retired by the array map and
 * neither render nor split a segment.
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
  const flush = (failure: ActivityRowFrame | null = null) => {
    if (run.length > 0) {
      // Active members own the live seat but are not durable evidence yet.
      // They join `rows` in place when their host settles COMPLETED.
      const rows = run
        .filter((u) => u.activity.status === "completed")
        .map((u) => u.activity)
      const startedAtMs = workStart(out, run[0], defaultWorkStartedAtMs)
      // A failed activity owns its own terminal edge. Do not move the first
      // host's clock to a later turn envelope or add the tool duration to the
      // segment's wall clock.
      const endedAtMs = run[0].workEndedAtMs ?? activityEndMs(failure)
      out.push({
        kind: "activityFold",
        rows,
        failure,
        firstActivityAt: run[0].activity.at,
        startedAtMs,
        endedAtMs,
        elapsedMs: foldElapsedMs(rows, startedAtMs, endedAtMs, failure),
        openTail: false, // stamped by the reverse boundary pass below
        // The fold's identity is its first member's host-row id: the
        // segment's head never changes when later members join or settle.
        rowKey: run[0].rowKey,
        turnId: run[0].turnId,
        independentKind: run[0].independentKind,
      })
    }
    run = []
  }
  for (const unit of units) {
    if (unit.kind === "activity" && unit.activity.status === "failed" && run.length > 0) {
      // One continuous segment settles into ONE failed receipt. The failure
      // remains available in its expanded details, never as a sibling status.
      flush(unit.activity)
      continue
    }
    if (
      unit.kind === "activity" &&
      (unit.activity.status === "completed" || unit.activity.status === "active")
    ) {
      // A WorkSegment may fold only within one explicit ownership domain.
      // Legacy rows share a non-semantic "legacy" domain (their existing
      // fold stays readable); different real turns never merge.
      if (run.length > 0 && activityOwner(run[0]) !== activityOwner(unit)) flush()
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
        openTail:
          unit.failure == null && !closedByLaterSpeech && unit.endedAtMs == null,
      }
    }
  }
  return out
}

function activityOwner(
  unit: Extract<ConversationUnit, { kind: "activity" }>,
): string {
  if (unit.independentKind) return `independent:${unit.independentKind}`
  return unit.turnId ? `turn:${unit.turnId}` : "legacy"
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

function activityEndMs(activity: ActivityRowFrame | null): number | null {
  if (!activity || !validMs(activity.duration_ms)) return null
  const startedAtMs = parseMs(activity.at)
  return startedAtMs == null ? null : startedAtMs + Math.max(0, activity.duration_ms)
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
  failure: ActivityRowFrame | null = null,
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
  const start = parseMs(rows[0]?.at ?? failure?.at)
  if (start != null) {
    const last = failure ?? rows[rows.length - 1]
    const lastAt = parseMs(last?.at)
    if (lastAt != null) {
      const lastEnd = lastAt + (last.duration_ms ?? 0)
      if (lastEnd > start) return lastEnd - start
    }
  }
  return null
}

/** The fold's expanded category rows (ADR-110 修订 — 归档归类目):
 * rows sharing one copy key AND asset type merge across the WHOLE segment
 * into ONE ×N category line (the Flora anatomy — 已读网页 ×3), order =
 * first appearance. Typed review receipts are the exception: each retains
 * its own evidence row and order. Instance names are the live phase's speech;
 * the archive speaks categories. A milestone row whose count IS its content
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
  /** Typed review evidence keeps its own row and is never folded into ×N. */
  receipt?: VideoReviewReceipt
}

/** The aggregate row's expanded categories (ADR-110 修订). */
export function foldCategories(rows: ActivityRowFrame[]): FoldCategory[] {
  const cats: FoldCategory[] = []
  for (const r of rows) {
    // Live wire frames and hydrated rows share this tolerant reader. Invalid
    // evidence falls back to the existing category without breaking replay.
    const receipt = parseActivityReceipt(r.receipt)
    const mergeable = receipt === undefined && (r.count == null || r.total != null)
    const hit = mergeable
      ? cats.find(
          (c) =>
            c.key === r.key &&
            c.assetType === r.assetType &&
            c.count === undefined &&
            c.receipt === undefined,
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
      ...(receipt ? { receipt } : {}),
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
