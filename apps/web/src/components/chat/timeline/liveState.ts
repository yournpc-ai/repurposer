/** Pure, React-free selector for the active chat turn's live presentation state.
 * Consolidates activity/thinking/fold/streaming ownership so AgentThread and
 * ChatConversation share one conflict-free source of truth. */

import { activityAssetKey } from "./history"
import type {
  ActivityFramePayload,
  ConversationUnit,
  NowRowPayload,
  OverlayMessage,
  ProjectAsset,
} from "./types"

export type ChatLiveMode =
  | "idle"
  | "live_working"
  | "live_post_tool_thinking"
  | "streaming_final"

export interface ChatLiveStateInput {
  chatBusy: boolean
  proseActive: boolean
  messages: readonly OverlayMessage[]
  conversationUnits: readonly ConversationUnit[]
  activities: readonly ActivityFramePayload[]
  thinkingPhase: string | null
  liveFocus?: string | null
  assets: readonly ProjectAsset[]
  sentAssetIds: ReadonlySet<string>
  currentActivityRowKeys: ReadonlySet<string>
  recoveredJobTurn: string | null
  interimActivityGateCount: number
}

export interface ChatLiveState {
  mode: ChatLiveMode
  nowRow: NowRowPayload | null
  liveFocus: string | null
  liveWorkFoldKey: string | null
  bottomNowRow: NowRowPayload | null
  postToolThinkingStartedAtMs: number | null
}

type ActivityFoldUnit = Extract<ConversationUnit, { kind: "activityFold" }>

const DRAFT_OVERRIDE_PHASES = new Set(["capturing", "storyboarding", "storyboard_revision"])

function makeThinkRow(
  key: string | null,
  name?: string,
  count?: number,
): NowRowPayload {
  return {
    activity_id: "__now__",
    seq: 0,
    kind: "think",
    status: "active",
    key,
    name,
    count,
  }
}

function latestSettledTimestampMs(fold: ActivityFoldUnit): number | null {
  let latest: number | null = null
  for (const row of fold.rows) {
    const parsed = Date.parse(row.at ?? "")
    if (Number.isNaN(parsed)) continue
    const endMs = parsed + Math.max(0, row.duration_ms ?? 0)
    if (latest === null || endMs > latest) latest = endMs
  }
  return latest ?? fold.startedAtMs
}

export function selectChatLiveState(input: ChatLiveStateInput): ChatLiveState {
  const {
    chatBusy,
    proseActive,
    messages,
    conversationUnits,
    activities,
    thinkingPhase,
    liveFocus: rawLiveFocus = null,
    assets,
    sentAssetIds,
    currentActivityRowKeys,
    recoveredJobTurn,
    interimActivityGateCount,
  } = input

  let workFold: ActivityFoldUnit | undefined
  let currentTurnOpenFold: ActivityFoldUnit | undefined
  for (let i = conversationUnits.length - 1; i >= 0; i -= 1) {
    const unit = conversationUnits[i]
    if (unit.kind !== "activityFold" || !unit.openTail) continue
    if (!workFold) workFold = unit
    if (chatBusy && !currentTurnOpenFold && currentActivityRowKeys.has(unit.rowKey)) {
      currentTurnOpenFold = unit
    }
  }

  const visibleProseTyping =
    proseActive &&
    messages.some((m) => m.streaming && m.content.trim().length > 0)

  const activeActivity = activities.find((a) => a.status === "active" && a.kind !== "focus")
  const trimmedFocus = rawLiveFocus?.trim() || null
  const liveFocus = chatBusy && !visibleProseTyping && trimmedFocus ? trimmedFocus : null
  const processingAssets = assets.filter(
    (a) =>
      sentAssetIds.has(a.id) &&
      (a.processing_status === "pending" || a.processing_status === "processing"),
  )

  const nowRow: NowRowPayload | null = (() => {
    if (
      chatBusy &&
      activeActivity &&
      activeActivity.kind !== "focus" &&
      !(activeActivity.kind === "draft" && DRAFT_OVERRIDE_PHASES.has(thinkingPhase ?? ""))
    ) {
      return activeActivity as NowRowPayload
    }
    if (workFold && recoveredJobTurn && workFold.turnId === recoveredJobTurn && workFold.liveActivity) {
      return workFold.liveActivity
    }
    if (
      chatBusy &&
      !thinkingPhase &&
      workFold?.liveActivity &&
      currentActivityRowKeys.has(workFold.rowKey)
    ) {
      return workFold.liveActivity
    }
    if (chatBusy) {
      return makeThinkRow(thinkingPhase ? `chat.thinkingPhases.${thinkingPhase}` : null)
    }
    if (processingAssets.length > 1) {
      return makeThinkRow("chat.material.readingMany", undefined, processingAssets.length)
    }
    if (processingAssets.length === 1) {
      const lone = processingAssets[0]
      if (lone.processing_stage === "asr") {
        return makeThinkRow("chat.material.transcribing", lone.title ?? undefined)
      }
      if (lone.processing_stage === "speaker_map" || lone.processing_stage === "prosody") {
        return makeThinkRow("chat.material.understandingAsset", lone.title ?? undefined)
      }
      return makeThinkRow(
        activityAssetKey("chat.material.reading", lone.type),
        lone.title ?? undefined,
      )
    }
    return null
  })()

  let liveFold: ActivityFoldUnit | null = currentTurnOpenFold ?? null
  if (workFold && recoveredJobTurn && workFold.turnId === recoveredJobTurn) {
    liveFold = workFold
  }
  const liveWorkFoldKey = liveFold ? liveFold.rowKey : null

  const bottomNowRow =
    liveWorkFoldKey == null && !visibleProseTyping && interimActivityGateCount === 0
      ? nowRow
      : null

  const hasActiveTool = Boolean(activeActivity || liveFold?.liveActivity)
  const isPostToolThinking =
    chatBusy &&
    !visibleProseTyping &&
    liveFold !== null &&
    liveFold.rows.length > 0 &&
    !hasActiveTool

  const postToolThinkingStartedAtMs =
    isPostToolThinking && liveFold !== null
      ? latestSettledTimestampMs(liveFold)
      : null

  const mode: ChatLiveMode = visibleProseTyping
    ? "streaming_final"
    : isPostToolThinking
      ? "live_post_tool_thinking"
      : chatBusy || recoveredJobTurn != null || processingAssets.length > 0
        ? "live_working"
        : "idle"

  return {
    mode,
    nowRow,
    liveFocus,
    liveWorkFoldKey,
    bottomNowRow,
    postToolThinkingStartedAtMs,
  }
}
