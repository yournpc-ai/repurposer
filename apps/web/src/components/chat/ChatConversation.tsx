/** The single常驻 conversation scroller and its message/activity/Run renderers.
 * The dock owns form geometry and state; this component owns no second message
 * truth and mounts no additional scroller. */

import { Fragment, useEffect, useRef, useState, type ReactNode, type RefObject } from "react"
import { useTranslation } from "react-i18next"
import { Download } from "lucide-react"

import { ActivityRow, activityText, WorkSegmentRow, type NowRowPayload } from "@/components/chat/ActivityStream"
import { AnsweredQuestion } from "@/components/chat/AnsweredQuestion"
import { CandidateSurfaceCard } from "@/components/chat/CandidateSurface"
import { RunCard } from "@/components/chat/RunCard"
import { ComponentSlot } from "./blocks/ComponentSlot"
import type { RegisterStructureVisibility } from "./structureVisibility"
import { AssistantResponse } from "./blocks/AssistantResponse"
import { TurnBlock } from "./blocks/TurnBlock"
import { Button } from "@/components/ui/button"
import { Message, MessageContent } from "@/components/ui/message"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
  useMessageScroller,
} from "@/components/ui/message-scroller"
import { deliveredOutputsForRefs } from "@/lib/anchorCards"
import { useSettingsDialog } from "@/components/settings/settings-dialog-context"
import type { Output, WorkflowStep } from "@/lib/types"
import { skillOptionForReference, type SkillOption } from "@/lib/skills"
import type { InferredIntent } from "./chatProtocol"
import { AssistantText } from "./rows/AssistantText"
import { FocusRow, TurnErrorRow } from "./rows/MetaRow"
import { UserBubble } from "./rows/UserMessage"
import type {
  ConversationUnit,
  AssistantResponseSlot,
  RunResponseSlot,
  OverlayMessage,
  ProjectAsset,
  SuggestionPill,
} from "./timeline/types"
import { buildConversationBlocks } from "./timeline/project"
import { deliveryOutputReveal, hasMessageOutputs, type VideoPresentationRecoveryFact } from "./timeline/reveal"


/** Send-time follow re-arm (2026-09-24, user-reported auto-scroll failures).
 * The scroller library only auto-follows while its mode is "following-
 * bottom", which disengages the moment the viewport sits >8px off the
 * bottom — and items' content-visibility intrinsic-size estimates can hold
 * the geometry there (the stray ↓ button reads the same drift). SENDING is
 * the user's explicit "take me to the live edge" intent, so every send
 * calls scrollToEnd: the library's own entry both jumps AND re-engages
 * following-bottom (the just-appended bubble is then caught by the
 * content-change handler under the same follow mode). This bridge lives
 * inside the Provider — the hook can't be called from the dock's body. */
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

interface ChatConversationProps {
  messages: OverlayMessage[]
  planVersions: { messageId: string; plan: InferredIntent }[]
  renderPlanVersion: (
    version: { messageId: string; plan: InferredIntent },
    index: number,
  ) => ReactNode
  conversationUnits: ConversationUnit[]
  chatOutputs: Output[]
  skillOptions: SkillOption[]
  openOutputViewer: (outputId: string) => void
  runId: string | null
  chatBusy: boolean
  onSuggestionClick: (suggestion: SuggestionPill) => void
  onRunStarted: (runId: string) => void
  onStructureVisible: RegisterStructureVisibility
  pendingPlanMessageId: string | null
  presentationRecovery: VideoPresentationRecoveryFact | null
  currentActivityRowKeysRef: RefObject<Set<string>>
  liveWorkFoldKey: string | null
  nowRow: NowRowPayload | null
  bottomNowRow: NowRowPayload | null
  activeTurnId: string | null
  steps: WorkflowStep[]
  runTitle: string
  runCreatedAt: string | null
  terminal: boolean
  status: string | null
  reviewPending: boolean
  runWorkEndedAtMs: number | null
  runFallbackOutputs: Output[]
  hasUploads: boolean
  assets: ProjectAsset[]
  panel: boolean
  scrollerSendRef: RefObject<(() => void) | null>
}

const CHAT_STATUS_MIN_DISPLAY_MS = 1000

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
  messages,
  planVersions,
  renderPlanVersion,
  conversationUnits,
  chatOutputs,
  skillOptions,
  openOutputViewer,
  runId,
  chatBusy,
  onSuggestionClick,
  onRunStarted,
  onStructureVisible,
  pendingPlanMessageId,
  presentationRecovery,
  currentActivityRowKeysRef,
  liveWorkFoldKey,
  nowRow,
  bottomNowRow,
  activeTurnId,
  steps,
  runTitle,
  runCreatedAt,
  terminal,
  status,
  reviewPending,
  runWorkEndedAtMs,
  runFallbackOutputs,
  hasUploads,
  assets,
  panel,
  scrollerSendRef,
}: ChatConversationProps) {
  const { t } = useTranslation()
  const { openCreditTopup } = useSettingsDialog()
  const liveActivity = liveWorkFoldKey != null ? nowRow : bottomNowRow
  const chatStatusLabel = useChatStatusLabel(
    liveActivity ? activityText(liveActivity, t) : null,
    liveWorkFoldKey == null,
  )
  const bottomStatusLabel = bottomNowRow != null ? chatStatusLabel : null

  /** One conversation message with its anchors: superseded plan-version
   * chips sit right after the echo bubble whose turn produced them; an
   * in-flight live plan card anchors after its own echo bubble. */
  const deliveryAttemptCounts = new Map<string, number>()
  for (const message of messages) {
    if (!message.runDelivery || !message.runId) continue
    deliveryAttemptCounts.set(
      message.runId,
      (deliveryAttemptCounts.get(message.runId) ?? 0) + 1,
    )
  }
  const renderConversationMessage = (m: OverlayMessage) => {
    const deliveryOutputSlot = hasMessageOutputs(m) ? (
      <div data-message-scroller-reading-edge>
        <ComponentSlot
          slot={{
            kind: "output",
            key: `delivery-output:${m.id}`,
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
        messageId={m.id}
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
          <div className="flex flex-col items-start gap-1">
            <TurnErrorRow text={m.content} />
            {m.creditTopup && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => openCreditTopup(m.creditTopup)}
              >
                {t("credits.buyTitle")}
              </Button>
            )}
          </div>
        ) : m.role === "user" ? (
          <div className="flex w-full flex-col gap-2">
            {/* The turn's persisted focus rides as a gray prefix row (D8
                修订 — 焦点入流): system fact first, the bubble below it. */}
            {m.focus ? <FocusRow label={m.focus.label} /> : null}
            <UserBubble
              text={m.content}
              assets={m.assets}
              skill={m.skill ? skillOptionForReference(m.skill, skillOptions) : undefined}
            />
          </div>
        ) : (
          <>
            {m.content ? (
              <AssistantText
                text={m.content}
                streaming={m.streaming}
                hydrated={m.hydrated}
              />
            ) : null}
            {deliveryOutputSlot}
            {/* 建议 pills (T3 触发回合): the closing review's next steps —
                quiet outline buttons under the review's own speech, landing
                only after the prose drains. send = speaks the pill's text
                as the user's next message; download = the output cards'
                own channel. Never a second intent surface. */}
            {m.suggestions && m.suggestions.length > 0 ? (
              <Message align="start">
                <MessageContent>
                  <div className="mt-1 flex flex-wrap gap-2">
                    {m.suggestions.map((s, index) => (
                      <Button
                        key={`${m.id}-s${index}`}
                        variant="outline"
                        size="sm"
                        className="gap-1.5 rounded-md"
                        disabled={s.action === "send" && (chatBusy || (runId != null && !terminal))}
                        onClick={() => onSuggestionClick(s)}
                      >
                        {s.action === "download" ? (
                          <Download className="size-3.5" />
                        ) : null}
                        {s.label}
                      </Button>
                    ))}
                  </div>
                </MessageContent>
              </Message>
            ) : null}
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
              />
            ) : null}
            {m.blocks?.map((block, index) => {
              const key = `${m.id}-b${index}`
              const priorDrained = m.hydrated === true || m.proseDrainedAtMs != null
              const slot = block.kind === "video_storyboard"
                ? { kind: "storyboard" as const, key, message: m, block }
                : block.kind === "system_notice"
                  ? { kind: "systemNotice" as const, key, block, priorDrained, history: m.hydrated }
                  : block.kind === "audio_playback"
                    ? { kind: "audioPlayback" as const, key, block, priorDrained, history: m.hydrated }
                    : null
              return slot ? (
                <ComponentSlot
                  key={key}
                  slot={slot}
                  onRunStarted={onRunStarted}
                  pendingPlanMessageId={pendingPlanMessageId}
                  presentationRecovery={presentationRecovery}
                  structureId={m.serverMessageId}
                  structureTurnId={m.turnId}
                  onStructureVisible={onStructureVisible}
                />
              ) : null
            })}
          </>
        )}
      </MessageScrollerItem>
      {planVersions.map((version, index) =>
        version.messageId === m.id ? (
          <MessageScrollerItem key={`${m.id}-plan-v${index + 1}`}>
            {renderPlanVersion(version, index)}
          </MessageScrollerItem>
        ) : null
      )}
    </Fragment>
    )
  }

  /** One activity renderer for BOTH walks. The current open fold and the
   * bottom seat can never own the same segment; failure-separated earlier
   * fragments wait for the seal instead of prematurely saying "Worked". */
  const renderActivityUnit = (
    unit: Exclude<ConversationUnit, { kind: "message" }>,
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
    // An active-only host is a live seat, never an empty settled receipt.
    // Once that attempt is cancelled its visible row retires; a later retry
    // births its own host instead of leaving a struck-through failure row.
    if (unit.rows.length === 0 && !live) return null
    return (
      <MessageScrollerItem key={unit.rowKey}>
        <WorkSegmentRow
          rows={unit.rows}
          elapsedMs={unit.elapsedMs}
          liveLabel={live ? chatStatusLabel : null}
          failure={unit.failure}
        />
      </MessageScrollerItem>
    )
  }

  const conversationBlocks = buildConversationBlocks(conversationUnits, {
    attachedRunId: runId,
    pinAttachedRun: runId != null && !terminal,
  })
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

  const renderUnit = (unit: ConversationUnit) => unit.kind === "message"
    ? renderConversationMessage(unit.message) : renderActivityUnit(unit)

  const renderRun = (slot: RunResponseSlot) => {
    const opening = slot.opening.map(renderUnit)
    const deliveries = slot.deliveries.map(renderUnit)
    const sharedProps = {
      opening,
      renderAttemptCount: deliveryAttemptCounts.get(slot.runId) ?? 1,
    }
    return (
      <RunCard
        key={slot.key}
        {...sharedProps}
        runId={slot.runId}
        availableOutputs={chatOutputs}
        hasDelivery={(deliveryAttemptCounts.get(slot.runId) ?? 0) > 0}
        onOpen={openOutputViewer}
        attached={slot.runId === runId ? {
          steps,
          title: runTitle,
          runStartedAt: runCreatedAt,
          terminal,
          cancelled: status === "cancelled",
          failed: status === "failed",
          reviewPending,
          workEndedAtMs: runWorkEndedAtMs,
          hasUploads,
          outputs: runFallbackOutputs,
          onOpen: openOutputViewer,
          renderAttemptCount: sharedProps.renderAttemptCount,
          narrativeFallback: assets.some((asset) =>
            asset.processing_status === "pending" || asset.processing_status === "processing",
          ) ? t("results.stepper.transcribing") : t("results.stepper.queued"),
        } : undefined}
      >
        {deliveries}
      </RunCard>
    )
  }
  const renderSlot = (slot: AssistantResponseSlot) => slot.kind === "run" ? renderRun(slot) : renderUnit(slot)

  return (
    <MessageScrollerProvider
      // autoScroll: the assistant's streaming reply's live edge
      // follows the viewport as the bubble grows (independent of
      // scrollAnchor — which only fires on a NEW anchored row).
      // Explicit even though shadcn defaults to true: future-proofs
      // against upstream default drift, and makes the intent
      // auditable to the next reader. The provider owns the prop —
      // not MessageScroller.Root (which is a plain div).
      autoScroll
    >
      <ScrollerSendBridge apiRef={scrollerSendRef} />
      <MessageScroller className="h-full">
        <MessageScrollerViewport className="scroll-fade-y thin-scroll">
          {/* Full form: the stage's scroller starts below the
              transparent ProjectHeader (the wrapper's pt-14), so the
              content's own top rhythm is the dock's pt-4 — no extra
              headroom needed. The panel form fills the 480px column
              (no max-w centering). */}
          <MessageScrollerContent
            className={
              panel
                ? // Panel rails (2026-09-28 user ruling, two-step):
                  // the message column holds FLORA's px-6; the bottom
                  // register below runs one step tighter (px-4).
                  "w-full gap-0 px-6 pb-6 pt-3 [&>*+*]:mt-6 [&>*+[data-slot=run-response]]:mt-3"
                : "mx-auto w-full max-w-3xl gap-0 px-4 pb-8 pt-4 [&>*+*]:mt-8 [&>*+[data-slot=run-response]]:mt-3"
            }
          >
            {/* ONE row stream: transcript rows keep their array order;
                the run adapter pins bottom while live and anchors at the
                run end once terminal. */}
            {conversationBlocks.map((block) => {
              if (block.kind === "run") return renderRun(block)
              const slots = block.slots.map(renderSlot)
              if (block.kind === "standalone") {
                return <AssistantResponse key={block.key}>{slots}</AssistantResponse>
              }
              return (
                <TurnBlock key={block.key} user={block.user ? renderConversationMessage(block.user) : null}>
                  {slots}
                  {block.key === bottomSeatBlockKey && bottomStatusLabel !== null ? (
                    <MessageScrollerItem key={`now:${block.key}`}>
                      <WorkSegmentRow liveLabel={bottomStatusLabel} />
                    </MessageScrollerItem>
                  ) : null}
                </TurnBlock>
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
        <MessageScrollerButton direction="end" />
      </MessageScroller>
    </MessageScrollerProvider>
  )
}
