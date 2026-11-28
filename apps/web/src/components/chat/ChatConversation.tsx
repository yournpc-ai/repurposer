/** The single常驻 conversation scroller and its message/activity/Run renderers.
 * The dock owns form geometry and state; this component owns no second message
 * truth and mounts no additional scroller. */

import { Fragment, useEffect, useMemo, useRef, useState, type RefObject } from "react"
import { useTranslation } from "react-i18next"
import { Download, Minimize2 } from "@/components/ui/icons"

import { ActivityRow, activityText, isSyntheticRepair, StepsPlanCard, WorkSegmentRow, type NowRowPayload } from "@/components/chat/ActivityStream"
import { AnsweredQuestion } from "@/components/chat/AnsweredQuestion"
import { CandidateSurfaceCard } from "@/components/chat/CandidateSurface"
import { TurnMinimap, type TurnMinimapItem } from "@/components/chat/TurnMinimap"
import { useOptionalWorkbench } from "@/components/workbench/WorkbenchContext"
import { ComponentSlot } from "./blocks/ComponentSlot"
import type { RegisterStructureVisibility } from "./structureVisibility"
import { AssistantResponse } from "./blocks/AssistantResponse"
import { TurnBlock } from "./blocks/TurnBlock"
import { Button } from "@/components/ui/button-clean"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
  useMessageScroller,
} from "@/components/chat/MessageScroller"
import { deliveredOutputsForRefs } from "@/lib/anchorCards"
import { useSettingsDialog } from "@/components/settings/settings-dialog-context"
import type { Output } from "@/lib/types"
import { skillOptionForReference, type SkillOption } from "@/lib/skills"
import { AssistantText } from "./rows/AssistantText"
import { MessageActionBar } from "./rows/MessageActionBar"
import { FailureCheckpointCard, FocusRow, TurnErrorRow } from "./rows/MetaRow"
import { UserBubble } from "./rows/UserMessage"
import type {
  CandidateSurface,
  CompactSummary,
  ConversationBlock,
  ConversationUnit,
  MessageFeedbackSummary,
  OverlayMessage,
  StepPlanItem,
  SuggestionPill,
} from "./timeline/types"
import { buildConversationBlocks } from "./timeline/project"
import type { ChatLiveMode } from "./timeline/liveState"
import { deliveryOutputReveal, hasMessageOutputs, type VideoPresentationRecoveryFact } from "./timeline/reveal"


/** Sending a message returns the thread to the live edge. */
function ScrollerSendBridge({
  apiRef,
}: {
  apiRef: React.RefObject<(() => void) | null>
}) {
  const { scrollToEnd } = useMessageScroller()
  useEffect(() => {
    apiRef.current = () => scrollToEnd({ behavior: "auto" })
  }, [apiRef, scrollToEnd])
  return null
}

function ScrollerTurnMinimap({ turns }: { turns: TurnMinimapItem[] }) {
  const { viewport } = useMessageScroller()
  return <TurnMinimap turns={turns} viewportRef={viewport} />
}

function CompactContextDivider({ summary }: { summary: CompactSummary }) {
  const { t } = useTranslation()
  return (
    <div
      data-slot="compact-divider"
      role="separator"
      className="my-2 flex items-center gap-3 text-[11px] text-muted-foreground"
      title={summary.summary}
    >
      <span className="h-px flex-1 bg-border/80" />
      <span className="inline-flex items-center gap-1.5 rounded-full border border-border/70 bg-muted/40 px-2.5 py-0.5">
        <Minimize2 className="size-3 shrink-0 opacity-75" />
        <span>{t("chat.compactDivider")}</span>
        {summary.message_count > 0 ? (
          <span className="text-muted-foreground/75">
            · {t("chat.compactDividerDetail", { count: summary.message_count })}
          </span>
        ) : null}
      </span>
      <span className="h-px flex-1 bg-border/80" />
    </div>
  )
}

function isCheckpoint(slot: ConversationUnit) {
  return slot.kind === "message" && slot.message.meta === "error" &&
    Boolean(slot.message.failureCheckpoint) && !slot.message.creditTopup
}

function isIsolatedFailure(slot: ConversationUnit) {
  if (slot.kind === "activity") return slot.activity.status === "failed" && isSyntheticRepair(slot.activity)
  if (slot.kind !== "activityFold" || slot.liveActivity) return false
  const rows = slot.failure ? [...slot.rows, slot.failure] : slot.rows
  return rows.some(row => row.status === "failed") && rows.every(isSyntheticRepair) &&
    slot.trail.every(entry => entry.kind === "activity" && isSyntheticRepair(entry.activity))
}

function isAssistantOutcome(slot: ConversationUnit) {
  if (slot.kind !== "message") return false
  const m = slot.message
  return m.role === "assistant" && !m.meta && !m.streaming && !m.interim &&
    m.displayRole !== "stage_note" && m.displayRole !== "rail_note" &&
    Boolean(m.content.trim() || m.outputRefs?.length || m.blocks?.length)
}

function blockMaxSeq(block: ConversationBlock): number | null {
  let max: number | null = null
  const note = (seq?: number | null) => {
    if (typeof seq === "number" && (max == null || seq > max)) max = seq
  }
  if (block.kind === "turn" && block.user) note(block.user.seq)
  for (const unit of block.slots) {
    if (unit.kind === "message") note(unit.message.seq)
  }
  return max
}

function extractBlockVersionLabel(block: Extract<ConversationBlock, { kind: "turn" }>): string | null {
  let version: number | null = null
  for (const slot of block.slots) {
    if (slot.kind === "activityFold") {
      for (const row of slot.rows) {
        if (row.receipt?.kind === "video_revision") {
          version = row.receipt.version
        }
      }
    } else if (slot.kind === "message" && slot.message.blocks?.length) {
      for (const b of slot.message.blocks) {
        if (b.kind === "video_storyboard" && typeof b.version === "number") {
          version = b.version
        }
      }
    }
  }
  return version != null ? `v${version}` : null
}

interface ChatConversationProps {
  conversationUnits: ConversationUnit[]
  chatOutputs: Output[]
  skillOptions: SkillOption[]
  openOutputViewer: (outputId: string) => void
  chatBusy: boolean
  onSuggestionClick: (suggestion: SuggestionPill) => void
  onSelectCandidate?: (message: string, memberIndex: number, surface: CandidateSurface) => void
  onStructureVisible: RegisterStructureVisibility
  presentationRecovery: VideoPresentationRecoveryFact | null
  currentActivityRowKeysRef: RefObject<Set<string>>
  liveWorkFoldKey: string | null
  liveMode?: ChatLiveMode
  liveFocus?: string | null
  liveSteps?: StepPlanItem[] | null
  compactSummary?: CompactSummary | null
  onFeedbackChange?: (messageId: string, next: MessageFeedbackSummary | null) => void
  postToolThinkingStartedAtMs?: number | null
  nowRow: NowRowPayload | null
  bottomNowRow: NowRowPayload | null
  activeTurnId: string | null
  activeRunId?: string | null
  onRetryCheckpoint?: () => void
  scrollerSendRef: RefObject<(() => void) | null>
}

const CHAT_STATUS_MIN_DISPLAY_MS = 1000
const LEGACY_DELIVERY_BOILERPLATE = new Set([
  "正式成片已交付。",
  "Your reviewed MP4 is ready.",
])

function useChatStatusLabel(label: string | null, standalone: boolean) {
  const [displayedLabel, setDisplayedLabel] = useState<string | null>(null)
  const nextChangeAt = useRef<number | null>(null)

  useEffect(() => {
    if (label === null) {
      nextChangeAt.current = null
      setDisplayedLabel(null)
      return
    }
    if (label === displayedLabel) return

    const showLabel = () => {
      nextChangeAt.current = performance.now() + CHAT_STATUS_MIN_DISPLAY_MS
      setDisplayedLabel(label)
    }
    if (displayedLabel === null && !standalone) {
      showLabel()
      return
    }

    // Suppress short gaps before mounting the standalone row. Once visible,
    // coalesce updates into the latest label at the end of the display window.
    nextChangeAt.current ??= performance.now() + CHAT_STATUS_MIN_DISPLAY_MS
    const remainingMs = nextChangeAt.current - performance.now()
    if (remainingMs <= 0) {
      showLabel()
      return
    }
    const timer = window.setTimeout(showLabel, Math.ceil(remainingMs))
    return () => window.clearTimeout(timer)
  }, [label, standalone, displayedLabel])

  if (label === null) return null
  return displayedLabel ?? (standalone ? null : label)
}

export function ChatConversation({
  conversationUnits,
  chatOutputs,
  skillOptions,
  openOutputViewer,
  chatBusy,
  onSuggestionClick,
  onSelectCandidate,
  onStructureVisible,
  presentationRecovery,
  currentActivityRowKeysRef,
  liveWorkFoldKey,
  liveMode,
  liveFocus = null,
  liveSteps = null,
  compactSummary = null,
  onFeedbackChange,
  postToolThinkingStartedAtMs,
  nowRow,
  bottomNowRow,
  activeTurnId,
  activeRunId = null,
  onRetryCheckpoint,
  scrollerSendRef,
}: ChatConversationProps) {
  const { t } = useTranslation()
  const { openCreditTopup } = useSettingsDialog()
  const liveActivity = liveWorkFoldKey != null ? nowRow : bottomNowRow
  // Always track the real running tool action (tool_name / semantic detail) in
  // the live status header so it never gets stuck on a stale update_focus string.
  // Between tool batches (live_post_tool_thinking), surface "Thinking…" honestly
  // rather than snapping back to an earlier phase's focus label.
  const activeToolLabel =
    liveActivity &&
    liveActivity.status === "active" &&
    (liveActivity.tool_name || liveActivity.key)
      ? activityText(liveActivity, t)
      : null
  const rawStatusLabel = activeToolLabel
    ? activeToolLabel
    : liveMode === "live_post_tool_thinking"
      ? t("chat.thinking")
      : liveFocus && chatBusy
        ? liveFocus
        : liveActivity
          ? activityText(liveActivity, t)
          : null
  const chatStatusLabel = useChatStatusLabel(
    rawStatusLabel,
    liveWorkFoldKey == null,
  )
  const bottomStatusLabel = bottomNowRow != null ? chatStatusLabel : null

  /** One conversation message with its anchors: superseded plan-version
   * chips sit right after the echo bubble whose turn produced them; an
   * in-flight live plan card anchors after its own echo bubble. */
  const renderConversationMessage = (
    m: OverlayMessage,
    opts?: { checkpointSuperseded?: boolean; checkpointRecovered?: boolean },
  ) => {
    const deliveryOutputSlot = hasMessageOutputs(m) ? (
      <div data-message-scroller-reading-edge>
        <ComponentSlot
          slot={{
            kind: "output",
            key: `delivery-output:${m.id}`,
            reviewedVersionId: m.reviewedVersionId,
            outputs: deliveredOutputsForRefs(m.outputRefs ?? [], chatOutputs),
            ...deliveryOutputReveal(m),
          }}
          onOpen={openOutputViewer}
          structureId={m.serverMessageId}
          structureTurnId={m.turnId}
          onStructureVisible={onStructureVisible}
        />
      </div>
    ) : null
    // Empty speech rows remain in the timeline projection for identity and
    // work-segment boundaries, but a zero-height DOM item still consumes the
    // parent AssistantResponse's flex gap. Mount a slot only when one of the
    // branches below has a visible payload.
    if (
      m.role === "assistant" &&
      !m.qa &&
      m.meta == null &&
      !m.content &&
      deliveryOutputSlot == null &&
      (m.suggestions?.length ?? 0) === 0 &&
      !m.candidates &&
      (m.blocks?.length ?? 0) === 0
    ) return null
    return (
    // Keyed by birthKey (OverlayMessage law): a interim_prose-promoted row's
    // id changes (streamId → #ipN) but its key must not — an id-keyed list
    // remounts at the promotion and replays the entrance animation (the
    // flicker). Every other row's id never changes, so the fallback is free.
    <Fragment key={m.birthKey ?? m.id}>
      <MessageScrollerItem
        data-message-id={m.id}
        data-message-scroller-reading-edge={
          m.role === "assistant" && m.content ? "" : undefined
        }
      >
        {m.qa ? (
          <>
            <AnsweredQuestion
              question={m.qa.question}
              questionDetail={m.qa.detail}
              answer={m.qa.answer}
              items={m.qa.items}
              muted={m.qa.muted}
              hydrated={m.hydrated}
            />
            {deliveryOutputSlot}
          </>
        ) : m.meta === "error" ? (
          m.failureCheckpoint && !m.creditTopup ? (
            <FailureCheckpointCard
              text={m.content}
              checkpoint={m.failureCheckpoint}
              recovered={opts?.checkpointRecovered}
              disabled={chatBusy}
              onRetry={opts?.checkpointSuperseded ? undefined : onRetryCheckpoint}
            />
          ) : (
            <div className="flex flex-col items-start gap-1">
              <TurnErrorRow text={m.content} />
              {m.creditTopup && (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => openCreditTopup(m.creditTopup)}
                >
                  {t("credits.buyTitle")}
                </Button>
              )}
            </div>
          )
        ) : m.role === "user" ? (
          <div className="flex w-full flex-col gap-2">
            {/* The turn's persisted focus rides as a gray prefix row (D8
                修订 — 焦点入流): system fact first, the bubble below it. */}
            {m.focus ? <FocusRow label={m.focus.label} /> : null}
            <UserBubble
              text={m.content}
              assets={m.assets}
              skill={m.skill ? skillOptionForReference(m.skill, skillOptions) : undefined}
              createdAt={m.at}
            />
          </div>
        ) : (
          <div className="group/msg">
            {m.content &&
            !(
              deliveryOutputSlot != null &&
              Boolean(m.reviewedVersionId) &&
              LEGACY_DELIVERY_BOILERPLATE.has(m.content.trim())
            ) ? (
              <AssistantText
                text={m.content}
                streaming={m.streaming}
                hydrated={m.hydrated}
                stageNote={Boolean(
                  m.interim ||
                    m.displayRole === "stage_note" ||
                    m.displayRole === "rail_note",
                )}
              />
            ) : null}
            {deliveryOutputSlot}
            {/* Candidate Surface (v4.2 C8-c): the candidate card anchors
                under its turn's reply — replayed from the candidates_log
                dump or live-born from the SSE frame, same seat. */}
            {m.candidates ? (
              <CandidateSurfaceCard
                surface={m.candidates}
                hydrated={m.hydrated}
                serverMessageId={m.serverMessageId}
                turnId={m.turnId}
                onStructureVisible={onStructureVisible}
                onSelectCandidate={onSelectCandidate}
                selectionDisabled={chatBusy}
              />
            ) : null}
            {m.blocks?.map((block, index) => {
              const key = `${m.id}-b${index}`
              const priorDrained = m.hydrated === true || m.proseDrainedAtMs != null
              const suppressRedundantStoryboard =
                block.kind === "video_storyboard" &&
                (deliveryOutputSlot != null || Boolean(m.content?.includes("#workbench:storyboard/")))
              const slot =
                block.kind === "video_storyboard" && !suppressRedundantStoryboard
                  ? { kind: "storyboard" as const, key, message: m, block }
                  : block.kind === "system_notice"
                    ? { kind: "systemNotice" as const, key, block, priorDrained, history: m.hydrated }
                    : block.kind === "audio_playback" || block.kind === "image_preview"
                      ? { kind: "mediaPreview" as const, key, block, priorDrained, history: m.hydrated }
                      : null
              return slot ? (
                <ComponentSlot
                  key={key}
                  slot={slot}
                  presentationRecovery={presentationRecovery}
                  structureId={m.serverMessageId}
                  structureTurnId={m.turnId}
                  onStructureVisible={onStructureVisible}
                />
              ) : null
            })}
            {m.content &&
            !(
              deliveryOutputSlot != null &&
              Boolean(m.reviewedVersionId) &&
              LEGACY_DELIVERY_BOILERPLATE.has(m.content.trim())
            )
              ? (() => {
                  if (
                    m.streaming ||
                    m.interim ||
                    m.displayRole === "stage_note" ||
                    m.displayRole === "rail_note" ||
                    m.displayRole === "question_framing_stub" ||
                    m.jobReceipt ||
                    m.fromJobReceipt ||
                    !(m.serverMessageId || m.hydrated)
                  ) {
                    return null
                  }
                  const isQuestionFraming =
                    m.displayRole === "question_framing" ||
                    Boolean(m.questionEcho)
                  if (isQuestionFraming) {
                    const substantive =
                      m.displayRole === "question_framing" ||
                      (m.displayRole == null && m.content.trim().length >= 40)
                    if (!substantive) return null
                    return (
                      <MessageActionBar
                        messageId={m.serverMessageId ?? (m.hydrated ? m.id : undefined)}
                        text={m.content}
                        createdAt={m.at}
                        feedback={m.feedback}
                        onFeedbackChange={onFeedbackChange}
                        revealOnHover
                        hideTimestamp
                      />
                    )
                  }
                  const ownRunBusy =
                    chatBusy &&
                    (activeRunId != null && m.runId != null
                      ? m.runId === activeRunId && !m.turnProse
                      : activeTurnId != null && m.turnId === activeTurnId && !m.turnProse)
                  if (ownRunBusy) return null
                  return (
                    <MessageActionBar
                      messageId={m.serverMessageId ?? (m.hydrated ? m.id : undefined)}
                      text={m.content}
                      createdAt={m.at}
                      feedback={m.feedback}
                      onFeedbackChange={onFeedbackChange}
                    />
                  )
                })()
              : null}
            {/* 建议 pills (T3 触发回合): the closing review's next steps —
                quiet outline buttons under the review's own speech, landing
                only after the prose drains. send = speaks the pill's text
                as the user's next message; download = the output cards'
                own channel. Never a second intent surface. */}
            {m.suggestions && m.suggestions.length > 0 ? (
              <div className="ui-th-message">
                <div className="mt-1 flex flex-wrap gap-2">
                  {m.suggestions.map((s, index) => (
                    <Button
                      key={`${m.id}-s${index}`}
                      variant="secondary"
                      size="sm"
                      className="gap-1.5 rounded-md"
                      disabled={s.action === "send" && chatBusy}
                      onClick={() => onSuggestionClick(s)}
                    >
                      {s.action === "download" ? (
                        <Download className="size-3.5" />
                      ) : null}
                      {s.label}
                    </Button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        )}
      </MessageScrollerItem>
    </Fragment>
    )
  }

  /** One activity renderer for BOTH walks. The current open fold and the
   * bottom seat can never own the same segment; failure-separated earlier
   * fragments wait for the seal instead of prematurely saying "Worked". */
  const renderActivityUnit = (
    unit: Exclude<ConversationUnit, { kind: "message" }>,
    recovered = false,
    attachedSteps?: StepPlanItem[],
  ) => {
    if (unit.kind === "activity") {
      return (
        <MessageScrollerItem key={unit.rowKey}>
          <ActivityRow activity={unit.activity} />
        </MessageScrollerItem>
      )
    }
    const currentOpen =
      chatBusy &&
      unit.openTail &&
      currentActivityRowKeysRef.current.has(unit.rowKey)
    if (currentOpen && unit.rowKey !== liveWorkFoldKey) return null
    const live = unit.rowKey === liveWorkFoldKey
    const postToolThinking =
      live && liveMode === "live_post_tool_thinking"
        ? {
            label: liveFocus ? t("chat.thinking") : (chatStatusLabel ?? t("chat.thinking")),
            startedAtMs: postToolThinkingStartedAtMs ?? unit.startedAtMs,
          }
        : null
    // An active-only host is a live seat, never an empty settled receipt.
    // Once that attempt is cancelled its visible row retires; a later retry
    // births its own host instead of leaving a struck-through failure row.
    if (unit.rows.length === 0 && !unit.failure && !live && !attachedSteps?.length) return null
    return (
      <MessageScrollerItem key={unit.rowKey}>
        <WorkSegmentRow
          trail={unit.trail}
          startedAtMs={unit.startedAtMs}
          onOpen={openOutputViewer}
          outputs={chatOutputs}
          elapsedMs={unit.elapsedMs}
          liveLabel={live ? chatStatusLabel : null}
          postToolThinking={postToolThinking}
          failure={unit.failure}
          recovered={recovered}
          attachedSteps={attachedSteps}
        />
      </MessageScrollerItem>
    )
  }

  const conversationBlocks = buildConversationBlocks(conversationUnits)
  const lastOutcomeBlock = conversationBlocks.reduce(
    (last, block, index) => block.slots.some(isAssistantOutcome) ? index : last, -1,
  )
  let bottomSeatBlockKey: string | null = null
  for (const block of conversationBlocks) {
    // An answer resumes the same server turn, but starts a new visible
    // response below the QA card, even before its first stream row arrives.
    if (block.kind === "standalone" && block.factKind === "qa") bottomSeatBlockKey = null
    if (block.kind !== "turn") continue
    // A world fact may split one turn into contiguous blocks. The live seat
    // belongs to the LAST matching block, never an earlier pre-fact fragment.
    if (block.turnId === activeTurnId) bottomSeatBlockKey = block.key
  }

  const minimapTurns = useMemo<TurnMinimapItem[]>(() => {
    const items: TurnMinimapItem[] = []
    let turnNumber = 0
    for (const block of conversationBlocks) {
      if (block.kind !== "turn" || !block.user) continue
      turnNumber += 1
      items.push({
        id: block.turnId,
        index: turnNumber,
        preview: block.user.content,
        versionLabel: extractBlockVersionLabel(block),
      })
    }
    return items
  }, [conversationBlocks])

  const compactAfterBlockIndex = useMemo(() => {
    if (!compactSummary || compactSummary.compacted_through_seq <= 0) return -1
    let lastIdx = -1
    for (let i = 0; i < conversationBlocks.length; i += 1) {
      const maxSeq = blockMaxSeq(conversationBlocks[i])
      if (maxSeq != null && maxSeq <= compactSummary.compacted_through_seq) {
        lastIdx = i
      }
    }
    return lastIdx
  }, [compactSummary, conversationBlocks])

  const workbench = useOptionalWorkbench()
  const showMinimap = minimapTurns.length > 1 && !workbench?.isOpen

  // Resolve persisted macro step plans per turnId so both mid-turn refreshes
  // (from opening user row) and settled refreshes (from assistant reply) mount
  // one clean StepsPlanCard on the turn's final execution block, without ever
  // duplicating steps inside ThinkingState's tool drawer.
  const turnStepsByBlockKey = useMemo(() => {
    const map = new Map<string, StepPlanItem[]>()
    const lastTurnBlockKeyByTurnId = new Map<string, string>()
    const openingStepsByTurnId = new Map<string, StepPlanItem[]>()
    const settledStepsByTurnId = new Map<string, StepPlanItem[]>()

    for (const block of conversationBlocks) {
      if (block.kind !== "turn") continue
      lastTurnBlockKeyByTurnId.set(block.turnId, block.key)
      if (block.user?.steps && block.user.steps.length >= 2) {
        openingStepsByTurnId.set(block.turnId, block.user.steps)
      }
      for (const slot of block.slots) {
        if (slot.kind === "message" && slot.message.steps && slot.message.steps.length >= 2) {
          settledStepsByTurnId.set(block.turnId, slot.message.steps)
        }
      }
    }

    for (const [turnId, blockKey] of lastTurnBlockKeyByTurnId.entries()) {
      const persisted = settledStepsByTurnId.get(turnId) ?? openingStepsByTurnId.get(turnId)
      if (persisted && persisted.length >= 2) {
        map.set(blockKey, persisted)
      }
    }

    if ((chatBusy || activeRunId != null) && liveSteps && liveSteps.length >= 2 && bottomSeatBlockKey) {
      map.set(bottomSeatBlockKey, liveSteps)
    }

    return map
  }, [activeRunId, bottomSeatBlockKey, chatBusy, conversationBlocks, liveSteps])

  return (
    <MessageScrollerProvider>
      <ScrollerSendBridge apiRef={scrollerSendRef} />
      <MessageScroller className="h-full">
        <ScrollerTurnMinimap turns={showMinimap ? minimapTurns : []} />
        <MessageScrollerViewport className="ui-th-lane scroll-fade-y thin-scroll">
          <MessageScrollerContent
            className="ui-th-col"
            data-has-minimap={showMinimap || undefined}
            role="log"
            aria-busy={chatBusy}
          >
            {/* ONE row stream: transcript rows keep their array order;
                the run adapter pins bottom while live and anchors at the
                run end once terminal. */}
            {conversationBlocks.map((block, blockIndex) => {
              const blockSteps = block.kind === "turn" ? turnStepsByBlockKey.get(block.key) : undefined
              const hasStepsCard = Boolean(blockSteps && blockSteps.length >= 2)
              const checkpointRuns = block.slots.flatMap(slot =>
                slot.kind === "message" && isCheckpoint(slot)
                  ? [slot.message.runId ?? slot.message.failureCheckpoint?.run_id]
                  : [],
              )
              const visibleSlots = checkpointRuns.length ? block.slots.filter(slot =>
                slot.kind === "message" || !isIsolatedFailure(slot) ||
                !checkpointRuns.some(run => !run || !slot.runId || slot.runId === run),
              ) : block.slots
              let stepsHostIndex = -1
              if (hasStepsCard) {
                for (let i = visibleSlots.length - 1; i >= 0; i -= 1) {
                  if (visibleSlots[i].kind === "activityFold") {
                    stepsHostIndex = i
                    break
                  }
                }
              }
              const attachToBottomSeat =
                hasStepsCard &&
                stepsHostIndex < 0 &&
                block.key === bottomSeatBlockKey &&
                bottomStatusLabel !== null
              const slots = visibleSlots.map((slot, slotIndex) => {
                const laterSlots = visibleSlots.slice(slotIndex + 1)
                const hasJobFailure =
                  slot.kind === "activityFold" &&
                  slot.rows.some(
                    (row) =>
                      row.jobReceipt &&
                      (row.status === "failed" || row.jobReceipt.status === "provider_unknown"),
                  )
                const hasLaterOutcome =
                  slot.kind === "activityFold" &&
                  !hasJobFailure &&
                  laterSlots.some(
                    (later) =>
                      later.kind === "activityFold" ||
                      later.kind === "activity" ||
                      (later.kind === "message" &&
                        later.message.role === "assistant" &&
                        !later.message.meta &&
                        Boolean(
                          later.message.content.trim() ||
                            later.message.outputRefs?.length ||
                            later.message.blocks?.length,
                        )),
                  )
                if (slot.kind === "message") {
                  const checkpointSuperseded = isCheckpoint(slot) && (
                    blockIndex < conversationBlocks.length - 1 ||
                    laterSlots.some(later => later.kind !== "message" || isCheckpoint(later) || isAssistantOutcome(later))
                  )
                  return renderConversationMessage(slot.message, {
                    checkpointSuperseded,
                    checkpointRecovered: checkpointSuperseded &&
                      (lastOutcomeBlock > blockIndex || laterSlots.some(isAssistantOutcome)),
                  })
                }
                return renderActivityUnit(slot, hasLaterOutcome, slotIndex === stepsHostIndex ? blockSteps : undefined)
              })
              const divider =
                compactSummary && blockIndex === compactAfterBlockIndex ? (
                  <CompactContextDivider summary={compactSummary} />
                ) : null
              if (block.kind === "standalone") {
                return (
                  <Fragment key={block.key}>
                    <AssistantResponse>
                      {slots}
                    </AssistantResponse>
                    {divider}
                  </Fragment>
                )
              }
              return (
                <Fragment key={block.key}>
                  <TurnBlock
                    turnMinimapId={block.user ? block.turnId : undefined}
                    user={block.user ? renderConversationMessage(block.user) : null}
                  >
                    {hasStepsCard && stepsHostIndex < 0 && !attachToBottomSeat && blockSteps ? (
                      <MessageScrollerItem key={`steps:${block.key}`}>
                        <StepsPlanCard steps={blockSteps} />
                      </MessageScrollerItem>
                    ) : null}
                    {slots}
                    {block.key === bottomSeatBlockKey && bottomStatusLabel !== null ? (
                      <MessageScrollerItem key={`now:${block.key}`}>
                        <WorkSegmentRow
                          liveLabel={bottomStatusLabel}
                          attachedSteps={attachToBottomSeat ? blockSteps : undefined}
                        />
                      </MessageScrollerItem>
                    ) : null}
                  </TurnBlock>
                  {divider}
                </Fragment>
              )
            })}

            {/* Bottom work-segment seat: used only until a current
                durable activity fold can own the live row in the
                timeline (and for pure, non-expandable Thinking). The
                SAME WorkSegmentRow covers both seats and both poses. */}
            {bottomStatusLabel !== null && bottomSeatBlockKey == null ? (
              <AssistantResponse>
                <MessageScrollerItem>
                  <WorkSegmentRow liveLabel={bottomStatusLabel} />
                </MessageScrollerItem>
              </AssistantResponse>
            ) : null}
          </MessageScrollerContent>
        </MessageScrollerViewport>
        {/* Jump-to-latest pill — appears only when the user has scrolled
            up off the bottom (the primitive tracks visibility). */}
        <MessageScrollerButton />
      </MessageScroller>
    </MessageScrollerProvider>
  )
}
