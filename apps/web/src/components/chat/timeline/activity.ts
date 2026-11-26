/** Activity-span filtering and work-segment folding. Pure presentation
 * projection: no React, transport, or layout ownership. */

import type {
  ActivityRowFrame,
  ConversationUnit,
  OverlayMessage,
  WorkTrailEntry,
} from "./types"

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
  "chat.activity.videoSave",
  "chat.activity.videoSaveDone",
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

const PRIMARY_LIVE_TOOLS = new Set([
  "create_video",
  "export_video",
  "review_video",
  "deliver_video",
  "preview_range",
  "generate_sfx",
  "generate_voice",
  "generate_music",
  "generate_image",
  "analyze_brand",
  "prepare_video_materials",
  "capture_web",
  "set_composition_style",
  "insert_motion_block",
  "update_motion_block",
  "insert_text",
  "edit_text",
])

function pickLiveActivity(active: ActivityRowFrame[]): ActivityRowFrame | undefined {
  const running = active.filter((a) => a.call_state === "running")
  const primaryRunning = running.find((a) => a.tool_name && PRIMARY_LIVE_TOOLS.has(a.tool_name))
  if (primaryRunning) return primaryRunning
  if (running.length > 0) return running.at(-1)
  const primaryActive = active.find((a) => a.tool_name && PRIMARY_LIVE_TOOLS.has(a.tool_name))
  return primaryActive ?? active.at(-1)
}

type ActivityUnit = Extract<ConversationUnit, { kind: "activity" }>
type MessageUnit = Extract<ConversationUnit, { kind: "message" }>

export function isConversationBoundary(m: OverlayMessage): boolean {
  return m.role === "user" || !!(
    m.turnProse ||
    m.questionEcho ||
    m.displayRole === "question_framing" ||
    m.displayRole === "question_framing_stub" ||
    m.independentKind ||
    m.qa ||
    m.meta ||
    m.candidates ||
    m.outputRefs?.length ||
    m.blocks?.length ||
    m.suggestions?.length
  )
}

/** Declaration order is local to a batch. A later group may restart at zero. */
function orderTrail(entries: WorkTrailEntry[]): WorkTrailEntry[] {
  const ordered: WorkTrailEntry[] = []
  let batch: Extract<WorkTrailEntry, { kind: "activity" }>[] = []
  const finishBatch = () => {
    ordered.push(...batch.sort((a, b) => (a.activity.call_index ?? 0) - (b.activity.call_index ?? 0)))
    batch = []
  }
  for (const entry of entries) {
    const group = entry.kind === "activity" && entry.activity.group_id
    if (batch.length && batch[0].activity.group_id !== group) finishBatch()
    if (entry.kind === "activity" && group) batch.push(entry)
    else ordered.push(entry)
  }
  finishBatch()
  return ordered
}

/** One contiguous work trail per opening. Pending prose becomes a note only
 * when another activity arrives. Keep the last prose visible on a silent
 * terminal edge, even when that means lifting it out of the folded trail. */
export function foldActivityUnits(
  units: ConversationUnit[],
  defaultWorkStartedAtMs?: number,
  liveTurnId?: string | null,
): ConversationUnit[] {
  const out: ConversationUnit[] = []
  let run: ActivityUnit[] = []
  let trail: WorkTrailEntry[] = []
  let pending: MessageUnit[] = []
  let leadingInterim: MessageUnit[] = []
  let lastNote: MessageUnit | undefined
  let clockHost: ActivityUnit | undefined

  const flushLeadingInterim = () => {
    if (!leadingInterim.length) return
    out.push(...leadingInterim)
    leadingInterim = []
  }

  const flush = (
    failure: ActivityRowFrame | null = null,
    following?: OverlayMessage,
    settledBoundary = false,
  ) => {
    flushLeadingInterim()
    const first = run[0]
    if (first && clockHost) {
      const rows = run.map(u => u.activity).filter(a => a.status !== "active" || a.call_id || a.group_id)
      const active = run.map(u => u.activity).filter(a => a.jobReceipt
        ? ["accepted", "queued", "running", "active"].includes(a.jobReceipt.status)
        : a.status === "active")
      const liveActivity = pickLiveActivity(active)
      const startedAtMs = workStart(out, first, defaultWorkStartedAtMs)
      const nextSpeech = pending.find(u => u.message.content.trim())?.message ?? following
      const displayEdge = nextSpeech?.independentKind || nextSpeech?.qa ? undefined : nextSpeech?.clientVisibleAtMs
      const endedAtMs = activityEndMs(failure) ?? clockHost.workEndedAtMs ?? displayEdge ?? null
      const hasFollowingResult = Boolean(
        following && (following.content.trim() || following.outputRefs?.length || following.blocks?.length),
      )
      const isFrozenEarlierRun = Boolean(
        settledBoundary || following?.qa || following?.independentKind || endedAtMs != null,
      )
      const keepLast = Boolean(
        lastNote &&
          (first.turnId !== liveTurnId || isFrozenEarlierRun) &&
          !hasFollowingResult &&
          !pending.some(u => u.message.content.trim()),
      )
      if (keepLast && lastNote) {
        const key = lastNote.message.birthKey ?? lastNote.message.id
        trail = trail.filter(entry => entry.rowKey !== key)
      }
      out.push({
        kind: "activityFold", trail: orderTrail(trail), rows, failure, liveActivity,
        firstActivityAt: first.activity.at, startedAtMs, endedAtMs,
        elapsedMs: foldElapsedMs(rows, startedAtMs, endedAtMs, failure),
        openTail: !failure && endedAtMs == null,
        rowKey: first.rowKey, clockRowKey: clockHost.rowKey,
        turnId: first.turnId, runId: first.runId, independentKind: first.independentKind,
      })
      if (keepLast && lastNote) out.push(lastNote)
    }
    out.push(...pending)
    run = []
    trail = []
    pending = []
    lastNote = undefined
    clockHost = undefined
  }

  for (const unit of units) {
    const first = run[0]
    if (unit.kind === "activity") {
      // Background web/asset reading receipts persisted without a turn_id
      // (asset-reading:*) must never shatter an active turn's work fold.
      const isOrphanAssetReading =
        Boolean(first?.turnId) &&
        !first?.independentKind &&
        !unit.turnId &&
        !unit.independentKind &&
        Boolean(unit.activity.activity_id?.startsWith("asset-reading:"))
      if (isOrphanAssetReading) {
        run.push(unit)
        trail.push({ kind: "activity", rowKey: unit.rowKey, activity: unit.activity })
        continue
      }
      const differentRun = Boolean(first?.runId && unit.runId && first.runId !== unit.runId)
      if (first && (first.turnId !== unit.turnId || differentRun || first.independentKind || unit.independentKind)) {
        flush(null, undefined, true)
      }
      if (unit.activity.status === "failed" && !unit.activity.call_id && !unit.activity.group_id &&
        (!run.length || !unit.turnId)) {
        if (run.length && !pending.length) flush(unit.activity)
        else {
          flush()
          out.push(unit)
        }
        continue
      }
      flushLeadingInterim()
      if (!run.length || pending.length) clockHost = unit
      for (const prose of pending) {
        if (!prose.message.content.trim()) continue
        lastNote = prose
        trail.push({ kind: "note", rowKey: prose.message.birthKey ?? prose.message.id, text: prose.message.content })
      }
      pending = []
      run.push(unit)
      trail.push({ kind: "activity", rowKey: unit.rowKey, activity: unit.activity })
    } else if (
      unit.kind === "message" &&
      (unit.message.interim ||
        unit.message.displayRole === "stage_note" ||
        unit.message.displayRole === "rail_note")
    ) {
      // Option A — Single-Rail Interleaved Narrative (Antigravity parity):
      // 1. An opening stage_note BEFORE the Run's first tool (`!first`) stays
      //    as quiet visible prose above the work rail — NEVER swallowed.
      // 2. Any subsequent mid-run note (`rail_note` or a later interim note
      //    arriving while an activity fold for the SAME (turnId, runId) is
      //    already open) goes directly inside that ONE work rail's `trail`,
      //    so a continuous Run never shatters into `工作了 6s / 11s / 1m 6s`.
      const sameOpenRun = Boolean(
        first &&
          !first.independentKind &&
          unit.message.turnId === first.turnId &&
          !(first.runId && unit.message.runId && first.runId !== unit.message.runId),
      )
      if (sameOpenRun) {
        if (unit.message.content.trim()) {
          lastNote = unit
          trail.push({
            kind: "note",
            rowKey: unit.message.birthKey ?? unit.message.id,
            text: unit.message.content,
          })
        }
      } else {
        flush(null, unit.message)
        if (unit.message.displayRole !== "rail_note" || unit.message.content.trim()) {
          out.push(unit)
        }
      }
    } else if (unit.kind === "message" && first?.turnId && !first.independentKind &&
      unit.message.turnId === first.turnId &&
      !(first.runId && unit.message.runId && first.runId !== unit.message.runId) &&
      !isConversationBoundary(unit.message)) {
      pending.push(unit)
    } else {
      const following = unit.kind === "message" && unit.message.turnId === first?.turnId &&
        !(first?.runId && unit.message.runId && first.runId !== unit.message.runId) &&
        unit.message.role === "assistant" && !unit.message.meta ? unit.message : undefined
      const isBoundaryClose = Boolean(
        unit.kind === "message" && (unit.message.qa || unit.message.independentKind || unit.message.role === "user"),
      )
      flush(null, following, isBoundaryClose)
      out.push(unit)
    }
  }
  flush()

  // Empty streaming placeholders and terminal error notices must leave the
  // preceding host eligible for its real first-visible / terminal clock seal.
  let closed = false
  for (let i = out.length - 1; i >= 0; i--) {
    const unit = out[i]
    if (unit.kind === "message") {
      const m = unit.message
      if (!m.meta && (isConversationBoundary(m) || m.content.trim())) closed = true
    } else if (unit.kind === "activityFold") {
      if (closed && unit.openTail) out[i] = { ...unit, openTail: false }
      closed = true
    } else {
      closed = true
    }
  }
  return out
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
    if (unit.kind !== "message") return fallback
    const m = unit.message
    if (m.turnId && first.turnId && m.turnId !== first.turnId) return fallback
    if (m.role === "user") return parseMs(m.at) ?? fallback
    if (m.qa) {
      return validMs(m.clientVisibleAtMs) ? m.clientVisibleAtMs : fallback
    }
    if (m.content.trim()) {
      return validMs(m.proseDrainedAtMs) ? m.proseDrainedAtMs : fallback
    }
    if (isConversationBoundary(m)) return fallback
  }
  return fallback
}

/** Completed work's elapsed wall time. A client-sealed segment includes
 * tool work AND the following model wait, ending at the first visible reply
 * fragment (or a prose-less terminal state), then freezes. Unsealed /
 * replayed rows fall back to the observable activity span. Parallel tool
 * durations are NEVER summed into a pretend wall clock; without timestamps
 * the honest fallback is no elapsed (the header omits the time). */
function foldElapsedMs(
  rows: ActivityRowFrame[],
  startedAtMs: number | null,
  endedAtMs: number | null,
  failure: ActivityRowFrame | null = null,
): number | null {
  if (endedAtMs != null) {
    const liveStart = startedAtMs ?? parseMs(rows[0]?.at)
    if (liveStart != null && endedAtMs >= liveStart) {
      return endedAtMs - liveStart
    }
  }
  // Replay / legacy rows have no first-visible client fact. Preserve the
  // observable ACTIVITY span rather than stretching it to an assistant
  // created_at or a later user gesture.
  const observations = failure ? [...rows, failure] : rows
  let earliest = Infinity
  let latest = -Infinity
  for (const row of observations) {
    const at = parseMs(row.at)
    if (at == null) continue
    earliest = Math.min(earliest, at)
    latest = Math.max(latest, at + Math.max(0, row.duration_ms ?? 0))
  }
  if (latest > earliest) return latest - earliest
  return null
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
