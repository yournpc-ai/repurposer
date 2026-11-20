"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  Check,
  ChevronDown,
  ChevronUp,
  History,
  Image,
  Loader2,
  Mic2,
  Plus,
  Undo2,
  Upload,
  Video,
  X,
} from "lucide-react"

import { apiFetch } from "@/lib/api"
import {
  chatAttachmentFromAsset,
  messageAssetsFromAttachments,
  type FirstMessageHandoff,
} from "@/lib/chatAttachments"
import { armAnswerWatchdog } from "@/lib/answerWatchdog"
import { inferAssetType } from "@/lib/asset-type"
import { streamAnswer, streamChat, StreamTurnError, questionSettledCode } from "@/lib/chat-stream"
import { StreamTransportError } from "@/lib/streamTransport"
import { sseProbe } from "@/lib/sse-probe" // TEMPORARY forensics — delete with the probe
import {
  fetchChatSkills,
  sameSkillReference,
  skillOptionForReference,
  type SkillOption,
} from "@/lib/skills"
import type { ActivityFramePayload } from "@/lib/chat-stream"
import {
  reduceCandidateFrame,
  releaseSettledCandidateRows,
  type ActivityRowFramePayload,
  type CandidateEventPayload,
  type RowAppendPayload,
} from "@/lib/chatStreamFrames"
import { buildConversationUnits, closeWorkSegment } from "./timeline/project"
import { foldActivityUnits } from "./timeline/activity"
import {
  nextRunWorkSeal,
  runStepEndMs,
  visibleProductionStages,
  sameRunAttempt,
  isHistoricalRunTerminal,
  type RunAttemptKey,
  type RunWorkSeal,
} from "@/lib/runWorkSegment"
import {
  asCreditsInsufficient,
  type CreditsInsufficientDetail,
} from "@/lib/credits"
import { createTypewriter } from "@/lib/typewriter"
import { downloadOutput } from "@/components/results/downloadOutput"
import { nextRunAttachment, useRunEvents } from "@/lib/use-run-events"
import { cn } from "@/lib/utils"
import { useSettingsDialog } from "@/components/settings/settings-dialog-context"
import {
  assetTypeKind,
  outputMentionLabel,
  outputMentionName,
  type ChatMention,
  type MentionContext,
} from "@/lib/mentions"
import type { MediaRegionSelection } from "@/lib/mediaRegionSelection"
import { isChatVideoOutput, zeroDeliveryVideoOutputs } from "@/lib/anchorCards"
import {
  MentionEditor,
  type MentionEditorHandle,
} from "@/components/mentions/MentionEditor"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Message, MessageContent } from "@/components/ui/message"
import {
  Attachment,
  AttachmentAction,
  AttachmentActions,
  AttachmentContent,
  AttachmentDescription,
  AttachmentGroup,
  AttachmentMedia,
  AttachmentTitle,
} from "@/components/ui/attachment"
import { ChatOutputViewer } from "@/components/chat/ChatOutputViewer"
import { createSpeechSegments, isSpeechSegmentRow } from "./timeline/speech"
import { ComposerIconButton } from "@/components/composer/ComposerIconButton"
import { ComposerSendButton } from "@/components/composer/ComposerSendButton"
import {
  mapHistoryRows,
  activityRowFrame,
  answeredQuestionText,
  answeredQuestionIdFromIntent,
  isNonRenderIntent,
  activityAssetKey,
  triggerDeliveryRef,
  triggerOutputRefs,
  triggerSuggestions,
  questionEcho,
  bareQuestion,
  groupAnswerDisplay,
  type HistoryRow,
} from "./timeline/history"
import type {
  BriefAnswerItem,
  DerivedRow,
  DecisionPlanRow,
  OverlayMessage,
  ProjectAsset,
  QuestionMessage,
  SuggestionPill,
} from "./timeline/types"
import type { VideoPresentationRecoveryFact } from "./timeline/reveal"
import {
  applyStoppedTurnFrontier,
  visibleFrontierForTurn,
  type ChatTurnVisibleFrontier,
} from "./timeline/visibility"
import type { RegisterStructureVisibility } from "./structureVisibility"
import {
  answerEnvelopeProse,
  planEnvelopePacing,
  spliceAnswerEnvelope,
} from "./answerSettlement"
import { shouldPaceStartEnvelopeProse } from "./startSettlement"
import {
  buildRecoveredActivityRow,
  buildRecoveredProseMessage,
  hasAnyRunDelivery,
  insertRecoveredMessage,
  isCurrentRunAttemptDelivery,
  isFreshPolledRow,
  isTurnOwner,
  observedMessageSeq,
  prependMissingHistory,
  reconcilePersistedFailure,
  releaseTurnOwner,
  runReviewerLanded,
  shouldAdmitPolledTrigger,
  stampServerMessageId,
  stampMessagePresentation,
} from "./liveMessageReconcile"
import { belongsToServerRow, chineseSceneNumber, continuationTurnId, mediaProgress, sceneOrder, preparationActivity, preparationTool, journeyMark, journeyTranscriptRow, latestJourneyMark, type JourneyMark } from "./mediaJourneyMessages"
import { matchOptionByText } from "./optionMatch"
import { loadQuestionGroupDrafts, saveQuestionGroupDrafts } from "./questionGroupDrafts"
import {
  resetActivities,
  sweepActivities,
  upsertActivityFrame,
} from "./activityReducer"
import {
  normalizeIntent,
  type InferredIntent,
  type TaskItem,
} from "./chatProtocol"
import {
  QuestionDock,
} from "@/components/chat/QuestionDock"
import { type NowRowPayload } from "@/components/chat/ActivityStream"
import { ChatConversation } from "./ChatConversation"
import { assetTypeIcon } from "./rows/UserMessage"
import type { ChatAttachment, ChatOutputEntry, LifecycleStamp, Output } from "@/lib/types"
import { isPlanReady } from "@/lib/lifecycleStamp"
import {
  acceptsStagedFile,
  fileIconFor,
  formatChipDuration,
  probeMediaDims,
  useStagedFileMeta,
} from "@/lib/stagedFiles"
import { putWithProgress } from "@/lib/stagingUploads"
import { useFileDrop } from "@/lib/useFileDrop"

/** Derived preview row (ADR-043): the server dry-run-compiles the chain at
 * dock time and projects what it will MAKE — the card's "you'll get"
 * section. `video` = production of an exact saved CompositionVersion. */

const TOOL_META: Record<string, {
  Icon: typeof Video
  labelKey: string
  langParam?: "language"
}> = {
  produce_video: { Icon: Video, labelKey: "chat.videoStoryboard.video" },
  prepare_narration: {
    Icon: Mic2,
    labelKey: "chat.productionStages.speech_media",
    langParam: "language",
  },
  prepare_visual_assets: {
    Icon: Image,
    labelKey: "chat.productionStages.visual_assets",
  },
}

/** The panel geometry's persistence key (float | docked) — 2026-09-06. */

/** Dead-stream detection (2026-10-15, 4427f90f 事故取证): the server
 * guarantees ONE frame at least every 15s (the bare-{} thinking keepalive),
 * so a turn with 45s of total frame silence is a dead pipe by construction
 * — never a slow model. The watchdog aborts the zombie stream; the
 * reconcile then pulls the turn's landed rows from the archive (the answer
 * commits server-side regardless — the archive replay proved it). The same
 * trigger fires on visibility-resume: a page frozen mid-turn (background
 * tab throttles/suspends the typewriter's timers) wakes to a stream that
 * will never finish processing, and the archive is again the truth. */
const STREAM_SILENCE_DEAD_MS = 45_000
const STREAM_WATCHDOG_TICK_MS = 10_000
const RECONCILE_POLL_MS = 5_000
const RECONCILE_CAP_MS = 5 * 60_000

/** The answer turn's dead-stream watchdog (the chat turn's machinery twin,
 * minimal form — the timing machine is the extracted pure seam
 * lib/answerWatchdog.ts): the answer endpoint shares the server's keepalive
 * guarantee (the pump's bare-{} thinking frame at least every 15s), so 45s
 * of total frame silence is a dead pipe by construction — never a slow
 * model. Answer turns have NO user stop and no reconcile (the
 * archive-pacing machinery stays the chat turn's own): the abort routes
 * into the caller's ordinary catch, which rolls the optimistic block back,
 * restores the dock's beat and releases the composer — a retry self-heals
 * (an answer that did land server-side settles the re-click quietly via the
 * settled-question codes). Without it a silently dead pipe left chatBusy
 * stuck forever: the now-line shimmered and the composer stayed dead until
 * a manual refresh. */

/** A file staged in the input group, mid-lifecycle: picked → uploading
 * (direct-to-storage, same 3-step flow as the composer — XHR-backed so the
 * chip shows the REAL %, 2026-09-24 composer/recipe parity) → done (a real
 * project asset) / error (retry or remove). Nothing enters the flow until
 * the user presses send — the chips ride the next user bubble. */
interface StagedUpload {
  localId: string
  file: File
  status: "uploading" | "done" | "error"
  /** 0..1 while uploading (XHR progress events; fetch has none). */
  progress: number
  asset?: ProjectAsset
  /** Restored chips keep the original byte size; their File is metadata-only. */
  size?: number
}

interface ActiveChatStop {
  controller: AbortController
  turnIdPromise: Promise<string | null>
  resolveTurnId: (turnId: string | null) => void
  draft: string
  mentions: ChatMention[]
  skill: SkillOption | null
  staged: StagedUpload[]
  stopOutcome: "cancelled" | "retracted" | null
  frontier: ChatTurnVisibleFrontier | null
  stopRequested: boolean
  /** Set while the control request is in flight; a quiet SSE close awaits it. */
  stopPromise: Promise<void> | null
}

function restoredStagedUploads(attachments: readonly ChatAttachment[]): StagedUpload[] {
  return messageAssetsFromAttachments(attachments).map((asset, index) => {
    const attachment = attachments[index]
    const mime =
      attachment.type === "file"
        ? "application/octet-stream"
        : `${attachment.type}/*`
    return {
      localId: `restored-${attachment.id}`,
      // A restored chip never uploads again: status=done + asset is the real
      // already-persisted Asset. The empty File supplies chip metadata only.
      file: new File([], attachment.name, { type: mime }),
      status: "done",
      progress: 1,
      asset,
      size: attachment.size,
    }
  })
}

/** One staged attachment in the dock's input band — THUMBNAIL FIRST (2026-
 * 09-06: dock chips learned the composer chip anatomy, one staged-file
 * language across every input surface): image = the file itself, video =
 * first frame, both via the shared useStagedFileMeta probe (object URLs
 * self-revoke); audio/docs keep the type icon. Upload lifecycle: uploading
 * = spinner + REAL % in the description slot (2026-09-24 composer/recipe
 * parity — the XHR-backed PUT feeds the ratio), error = retry, × removes
 * (and deletes the already-created asset). */
function StagedAttachmentChip({
  item,
  onRetry,
  onRemove,
}: {
  item: StagedUpload
  onRetry: () => void
  onRemove: () => void
}) {
  const { t } = useTranslation()
  const meta = useStagedFileMeta(item.file)
  const Icon = item.asset
    ? assetTypeIcon(item.asset.type)
    : fileIconFor(item.file)
  const isAv =
    item.file.type.startsWith("video/") || item.file.type.startsWith("audio/")
  const typeLabel = item.asset
    ? t(`generationOverlay.assetTypes.${item.asset.type}`, {
        defaultValue: item.asset.type,
      })
    : t("generationOverlay.assetTypes.file")
  const metaLine =
    item.status === "error"
      ? t("composer.uploadFailed")
      : isAv && meta.duration !== undefined
        ? `${typeLabel} · ${formatChipDuration(meta.duration)}`
        : typeLabel
  return (
    <Attachment
      size="sm"
      state={
        item.status === "uploading"
          ? "uploading"
          : item.status === "error"
            ? "error"
            : "done"
      }
    >
      <AttachmentMedia variant={meta.thumbUrl ? "image" : "icon"}>
        {meta.thumbUrl ? <img src={meta.thumbUrl} alt="" /> : <Icon />}
      </AttachmentMedia>
      <AttachmentContent>
        <AttachmentTitle>{item.file.name}</AttachmentTitle>
        {item.status === "uploading" ? (
          /* Composer/recipe parity (2026-09-24 用户拍板): the uploading
             chip speaks its REAL percent (XHR progress), spinner + numeral
             in the description slot — the bare shimmer was illegible. */
          <AttachmentDescription className="flex items-center gap-1">
            <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
            <span className="tabular-nums">
              {Math.round(item.progress * 100)}%
            </span>
          </AttachmentDescription>
        ) : (
          <AttachmentDescription>{metaLine}</AttachmentDescription>
        )}
      </AttachmentContent>
      <AttachmentActions
        // FLORA hover anatomy (2026-09-06): the chip chrome (× / retry)
        // reveals on hover — a clean tile at rest, chrome on demand. Error
        // state keeps its actions always visible (a hidden retry is a dead
        // end); focus-within covers keyboard users.
        className={
          item.status === "error"
            ? "opacity-100"
            : "opacity-0 transition-opacity group-hover/attachment:opacity-100 focus-within:opacity-100"
        }
      >
        {item.status === "error" && (
          <AttachmentAction
            aria-label={t("generationOverlay.retryUpload")}
            onClick={onRetry}
          >
            <Undo2 />
          </AttachmentAction>
        )}
        <AttachmentAction
          aria-label={t("generationOverlay.removeAttachment")}
          onClick={onRemove}
        >
          <X />
        </AttachmentAction>
      </AttachmentActions>
    </Attachment>
  )
}

/** 形态律 (ADR-053 R1): a TEXT question (options/items-empty) never docks —
 * it lives in the flow as a plain assistant message, so a refresh / revival
 * fetch keeps nothing for the pill. Task plans and questions with options or
 * grouped items dock as before. */
export function dockWorthyQuestion(q: QuestionMessage | null): QuestionMessage | null {
  return q &&
    (q.question?.kind !== "question" ||
      (q.question?.options?.length ?? 0) > 0 ||
      (q.question?.items?.length ?? 0) > 0)
    ? q
    : null
}

interface AgentThreadProps {
  projectId: string
  prompt: string
  /** The composer's draft, handed over via router state: sent as the first
   * /chat message on mount (mentions + persona choice ride along). Null on
   * restored sessions — the conversation is already on the server. */
  firstMessage?: FirstMessageHandoff | null
  initialIntent?: InferredIntent | null
  /** Attach to an already-running generation (returning visitor): skips the
   * confirm beat, lands straight on the step flow. */
  initialRunId?: string | null
  /** A zero-visible Stop retracted the handed-over first Turn. Clear the
   * router handoff so a refresh cannot auto-send the restored draft again. */
  onFirstMessageRetracted?: () => void
  onProjectChanged: (runId?: string | null) => void | Promise<void>
  /** The server-named lifecycle stamp (ADR-087 §2, Phase 1): the confirm
   * beat's derived gate (confirmActive) reads it — the dock never derives
   * lifecycle locally. Null on the
   * pre-first-fetch frame (the page's loading gate holds the mount, so this
   * is always settled before the confirm beat can show). */
  lifecycle?: LifecycleStamp | null

}

/** A superseded plan version in the flow: one slim chip row that expands
 * into a read-only snapshot with a restore action. The live plan is always
 * the bottom-most card; these chips are its history (2026-08-05 ruling —
 * chat edits the plan, nothing is locked, old versions stay visible). */
function PlanVersionChip({
  n,
  plan,
  summary,
  expanded,
  onToggle,
  onRestore,
  taskLabel,
}: {
  n: number
  plan: InferredIntent
  summary: string
  expanded: boolean
  onToggle: () => void
  onRestore: () => void
  taskLabel: (task: TaskItem) => string
}) {
  const { t } = useTranslation()
  return (
    <Message align="start">
      <MessageContent>
        <div className="w-full">
          <button
            type="button"
            onClick={onToggle}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <History className="h-3.5 w-3.5 shrink-0" />
            <span className="shrink-0 font-medium">
              {t("generationOverlay.planVersion", { n })}
            </span>
            <span className="min-w-0 truncate">{summary}</span>
            {expanded ? (
              <ChevronUp className="ml-auto h-3.5 w-3.5 shrink-0" />
            ) : (
              <ChevronDown className="ml-auto h-3.5 w-3.5 shrink-0" />
            )}
          </button>
          {expanded && (
            <div className="mt-1 flex flex-col gap-3 rounded-lg bg-muted p-4">
              <div className="flex flex-col gap-1.5">
                {plan.tasks.map((task, i) => {
                  const meta = TOOL_META[task.tool]
                  return (
                    <div key={i} className="flex items-center gap-1.5 text-xs">
                      {meta ? (
                        <meta.Icon className="h-3.5 w-3.5 text-muted-foreground" />
                      ) : null}
                      <span>{taskLabel(task)}</span>
                    </div>
                  )
                })}
                {plan.specific_instruction ? (
                  <p className="line-clamp-2 text-xs text-muted-foreground">
                    {plan.specific_instruction}
                  </p>
                ) : null}
              </div>
              <div>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 gap-1.5"
                  onClick={onRestore}
                >
                  <Undo2 className="h-3.5 w-3.5" />
                  {t("generationOverlay.versionRestore")}
                </Button>
              </div>
            </div>
          )}
        </div>
      </MessageContent>
    </Message>
  )
}

export function AgentThread({
  projectId,
  prompt,
  firstMessage,
  initialIntent,
  initialRunId,
  onFirstMessageRetracted,
  lifecycle,
  onProjectChanged,
}: AgentThreadProps) {
  const { openCreditTopup } = useSettingsDialog()
  const { t } = useTranslation()
  // Restore mount (Phase 1, acceptance #4; Phase 3 Batch B): the dock's only
  // view fork is "a run is attached" vs plain chat — a transport fact
  // (initialRunId), never a lifecycle judgment. The CONFIRM beat is derived
  // (confirmActive below); RUN lIVENESS reads the run's own SSE facts
  // (terminal/status). No phase machine lives here anymore.
  const [intent, setIntent] = useState<InferredIntent>(() =>
    initialIntent
      ? normalizeIntent(initialIntent)
      : {
          action: "draft",
          answer: null,
          tasks: [],
          specific_instruction: prompt,
        }
  )
  // (ADR-111 §3: the pending STATE machine stays the correctness floor
  // server-side — paid boundary / refresh rebuild / revision anchor; the
  // dock payload's brief/derived/reasons/plans mirrors retired with the
  // card that rendered them — nothing reads them here anymore.)
  // intentReady = a real inference has landed (a restored session hands one
  // over; a fresh navigation gets it from the first /chat turn's refetch) —
  // it gates the confirm beat (confirmActive) and the revision anchor
  // chips. Attach mode starts ready.
  const [intentReady, setIntentReady] = useState(!!initialIntent || !!initialRunId)
  const [runId, setRunId] = useState<string | null>(initialRunId ?? null)
  // Mirrored in a ref: async chat continuations capture stale closures, and
  // they must be able to tell a run went live while their turn was in flight.
  const runIdRef = useRef<string | null>(initialRunId ?? null)
  useEffect(() => {
    runIdRef.current = runId
  }, [runId])
  // Explicit same-run recovery gets a new attachment epoch without creating a
  // new domain Run or changing the RunBlock's runId-only key.
  const [runAttempt, setRunAttempt] = useState(0)
  const runAttemptRef = useRef(0)
  const [runAttemptUploadRetry, setRunAttemptUploadRetry] = useState(0)
  const [runStartedExplicitly, setRunStartedExplicitly] = useState(false)

  // ask_user 机器: the pending question docks above the input (task_book in
  // the confirm beat; plain questions from the chat loop afterwards); the
  // answered one collapses into the flow as an answered question.
  const [pendingQuestion, setPendingQuestion] = useState<QuestionMessage | null>(null)
  const [questionGroupDrafts, setQuestionGroupDrafts] = useState<Record<string, BriefAnswerItem[]>>({})
  const groupDraftsHydrationRef = useRef({ projectId: "", skipSave: true })
  const groupDraftKey = (question: QuestionMessage) =>
    `${question.id}:${question.question?.group_digest ?? ""}`
  const groupDraftAnswers = (question: QuestionMessage) =>
    (questionGroupDrafts[groupDraftKey(question)] ?? []).filter((answer) =>
      question.question?.items?.some((item) => item.slot === answer.slot))
  useEffect(() => {
    groupDraftsHydrationRef.current = { projectId, skipSave: true }
    setQuestionGroupDrafts(loadQuestionGroupDrafts(projectId))
  }, [projectId])
  useEffect(() => {
    const hydration = groupDraftsHydrationRef.current
    if (hydration.projectId !== projectId) return
    if (hydration.skipSave) {
      hydration.skipSave = false
      return
    }
    saveQuestionGroupDrafts(projectId, questionGroupDrafts)
  }, [projectId, questionGroupDrafts])
  useEffect(() => {
    const digest = pendingQuestion?.question?.group_digest
    if (!pendingQuestion || !digest || !(pendingQuestion.question?.items?.length)) return
    const targetKey = groupDraftKey(pendingQuestion)
    setQuestionGroupDrafts((previous) => {
      if (previous[targetKey]) return previous
      const sourceKey = Object.keys(previous).find((key) => key.endsWith(`:${digest}`) && key !== targetKey)
      if (!sourceKey) return previous
      const next = { ...previous, [targetKey]: previous[sourceKey] }
      delete next[sourceKey]
      return next
    })
  }, [pendingQuestion?.id, pendingQuestion?.question?.group_digest])
  // Read projection of pending_brief.video_presentation. It can only unlock
  // the exact server-authorized delayed-start ACK; it never creates intent.
  const [presentationRecovery, setPresentationRecovery] =
    useState<VideoPresentationRecoveryFact | null>(null)
  const presentationRecoveryGenRef = useRef(0)
  const [answering, setAnswering] = useState(false)
  // System Status label (三概念分家, ADR-087 §1; Phase 3 Batch B): set
  // from the server's labelled assistant.thinking frames — the surviving
  // labels are the film design span's (capturing / storyboarding /
  // storyboard_revision, emitted at real transitions and cleared at the
  // span's exit); every other LLM window wears the base chat.thinking
  // word — a plain black-box window needs no alias, however long it runs.
  // Bare keepalive frames never touch the label.
  // Lifecycle (I-PFA-06 清除协议, 2026-09-18): a label dies two ways — the
  // server's explicit clear frame {phase: null} ends it (every call's
  // name-known moment, and the film span's own exit), or the terminal
  // envelope closes the turn (终帧律 —
  // both stream paths reset at envelope AND failure, never leaving a stale
  // label in state).
  const [thinkingPhase, setThinkingPhase] = useState<string | null>(null)

  // The turn's Activity Stream (ADR-087 §3 Phase 2): the LIVE transient
  // channel — it feeds only the now-line (the active row's content). The
  // durable walk never reads this list: settled activity arrives as
  // persisted array rows (assistant.row.append/update → `messages`,
  // ADR-108), and draft/run spans are live-only by law (落定即退役).
  const [activities, setActivities] = useState<ActivityFramePayload[]>([])
  /** CURRENT-turn activity HOST ROW ids. This set is replaced at each turn
   * birth, so old segments cannot reopen or be sealed by a later turn. Each
   * turn keeps its own Set object for async terminal cleanup. */
  const currentActivityRowKeysRef = useRef<Set<string>>(new Set())
  /** Server structure ids whose actual open renderer committed for each Turn.
   * Written synchronously by layout effects, read synchronously by Stop. */
  const visibleStructureTurnsRef = useRef<Map<string, string>>(new Map())
  const registerStructureVisibility = useCallback<RegisterStructureVisibility>(
    (serverMessageId, turnId, visible) => {
      const registry = visibleStructureTurnsRef.current
      if (visible) {
        registry.set(serverMessageId, turnId)
      } else if (registry.get(serverMessageId) === turnId) {
        registry.delete(serverMessageId)
      }
    },
    [],
  )
  /** The live turn starts with its optimistic user/QA id and adopts the
   * server-stamped opening user id without changing any row/block key. */
  const currentTurnRef = useRef<{
    localId: string
    serverId: string | null
    adoptLocal: boolean
  } | null>(null)
  const adoptCurrentTurnId = useCallback((serverId?: string | null) => {
    const current = currentTurnRef.current
    if (current && serverId) current.serverId = serverId
    return current?.serverId ?? serverId ?? (current?.adoptLocal ? current.localId : undefined)
  }, [])
  const reconcileCurrentTurnRows = useCallback((rows: OverlayMessage[]) => {
    const current = currentTurnRef.current
    if (!current?.serverId || current.serverId === current.localId) return rows
    return rows.map((message) =>
      message.turnId === current.localId
        ? { ...message, turnId: current.serverId ?? message.turnId }
        : message
    )
  }, [])
  // The reducer pair is the extracted PURE seam (activityReducer.ts, Phase
  // 3 Batch A) — same upsert/sweep semantics, contract-tested.
  const handleActivityFrame = useCallback((frame: ActivityFramePayload) => {
    setActivities((prev) => upsertActivityFrame(prev, frame))
  }, [])

  // Conversation below the pinned regions (plan card / progress).
  const [messages, setMessages] = useState<OverlayMessage[]>([])
  const [journey, setJourney] = useState<JourneyMark | null>(null)
  const [journeyReadSeq, setJourneyReadSeq] = useState(-1)
  const journeyOpeningId = journey && (journey.state === "active" || journey.seq > journeyReadSeq)
    ? journey.openingId : null
  const observeJourney = useCallback((rows: Pick<QuestionMessage, "intent" | "seq">[]) => {
    setJourney((current) => latestJourneyMark(rows, current))
  }, [])
  const interimActivityGatesRef = useRef<Set<string>>(new Set())
  const [interimActivityGateCount, setInterimActivityGateCount] = useState(0)
  const releaseHeldActivityRows = useCallback(() => {
    setMessages((prev) => prev.map((message) =>
      message.activityDisplayHeld
        ? { ...message, activityDisplayHeld: undefined }
        : message
    ))
  }, [])
  const beginInterimActivityGate = useCallback((rowId: string) => {
    interimActivityGatesRef.current.add(rowId)
    setInterimActivityGateCount(interimActivityGatesRef.current.size)
  }, [])
  const settleInterimActivityGate = useCallback((rowId: string) => {
    interimActivityGatesRef.current.delete(rowId)
    const remaining = interimActivityGatesRef.current.size
    setInterimActivityGateCount(remaining)
    if (remaining === 0) releaseHeldActivityRows()
  }, [releaseHeldActivityRows])
  const resetInterimActivityGates = useCallback(() => {
    interimActivityGatesRef.current.clear()
    setInterimActivityGateCount(0)
    releaseHeldActivityRows()
  }, [releaseHeldActivityRows])
  /** Highest persisted transcript position observed from ANY server channel,
   * including non-render rows. Polling compares against the value from before
   * its response: a row merely unknown to this client is not automatically
   * new work for the live edge. */
  const observedSeqRef = useRef<number | null>(null)
  const noteObservedSeq = useCallback((seq?: number | null) => {
    if (seq != null && (observedSeqRef.current == null || seq > observedSeqRef.current)) {
      observedSeqRef.current = seq
    }
  }, [])
  // The defensive sweep (T16-B's client twin — the server sweeps before the
  // envelope, this catches whatever the stream lost): a settling turn never
  // leaves an activity spinning forever (假活跃禁令). Sweeps BOTH seats: the
  // transient now-line list and the array rows embedded in `messages`.
  const settleActivities = useCallback(
    (status: "completed" | "failed" | "cancelled") => {
      setActivities((prev) => sweepActivities(prev, status))
      setMessages((prev) =>
        prev.map((m) =>
          m.activity?.status === "active"
            ? { ...m, activity: { ...m.activity, status } }
            : m
        ),
      )
    },
    [],
  )
  // Transcript array mirror (ADR-108 §3): a persisted row appends at its
  // birth (append fixes the position — arrival order IS the array order)
  // and settles in place (update by row id, the position never moves).
  // Rows persist even on a failed turn (诚实 transcript) — never rolled
  // back client-side. Two row families ride the channel: activity rows
  // (intent carries {type:"activity", frame}) and PLAIN assistant rows —
  // the design beat's published storyboard (ADR-129) is code-composed
  // markdown, so it lands atomically (never through the typewriter — the
  // law's atomic-landing twin), after its design activity's settle row.
  const handleRowAppend = useCallback((wire: RowAppendPayload) => {
    const row = journeyTranscriptRow(wire)
    observeJourney([row])
    noteObservedSeq(row.seq)
    const turnId = row.turn_id ? adoptCurrentTurnId(row.turn_id) : undefined
    const frame = activityRowFrame(row.intent)
    if (!frame) {
      if (row.role !== "assistant" || (!row.content && !row.blocks?.length)) return
      setMessages((prev) => {
        const reconciled = reconcileCurrentTurnRows(prev)
        if (reconciled.some((m) => m.id === row.id)) return reconciled
        return [
          ...reconciled,
          {
            id: row.id,
            serverMessageId: row.id,
            role: "assistant" as const,
            content: row.content ?? "",
            outputRefs: triggerOutputRefs(row.intent),
            clientVisibleAtMs: row.content?.trim() ? Date.now() : undefined,
            proseDrainedAtMs: row.blocks?.some((block) => block.kind === "audio_playback" || block.kind === "image_preview") ? Date.now() : undefined,
            turnId,
            seq: row.seq ?? undefined,
            at: row.created_at ?? undefined,
            blocks: row.blocks?.length ? row.blocks : undefined,
          },
        ]
      })
      return
    }
    currentActivityRowKeysRef.current.add(row.id)
    setMessages((prev) => {
      const reconciled = reconcileCurrentTurnRows(prev)
      if (reconciled.some((m) => m.id === row.id)) return reconciled
      return [
        ...reconciled,
        {
          id: row.id,
          serverMessageId: row.id,
          role: "assistant" as const,
          content: "",
          turnId,
          seq: row.seq ?? undefined,
          at: row.created_at ?? undefined,
          activity: frame,
          activityDisplayHeld: interimActivityGatesRef.current.size > 0 || undefined,
        },
      ]
    })
  }, [adoptCurrentTurnId, noteObservedSeq, observeJourney, reconcileCurrentTurnRows])
  const handleRowUpdate = useCallback(
    (id: string, frame: ActivityRowFramePayload) => {
      currentActivityRowKeysRef.current.add(id)
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id && m.activity
            ? { ...m, activity: { ...m.activity, ...frame } }
            : m
        ),
      )
    },
    [],
  )

  /** Freeze the current segment without touching any tool's duration_ms.
   * The per-turn host-key Set is captured by the async turn that owns it. */
  const sealCurrentWorkSegment = useCallback(
    (rowKeys: ReadonlySet<string>, endedAtMs: number, startedAtMs?: number) => {
      setMessages((prev) => closeWorkSegment(prev, rowKeys, endedAtMs, startedAtMs))
    },
    [],
  )

  /** speechSegments' FIRST-VISIBLE callback. It runs BEFORE the fragment is
   * appended: the empty pinned row is still open, and `rowId` restricts the
   * seal to segments BEFORE this exact prose row. A preceding interim_prose can
   * therefore never seal a later activity segment; a server timestamp never
   * substitutes for this client display fact. */
  const noteSpeechVisible = useCallback(
    (rowId: string, atMs: number, rowKeys?: ReadonlySet<string>) => {
      setMessages((prev) => {
        const target = prev.find((m) => m.id === rowId)
        if (!target || target.clientVisibleAtMs != null) return prev
        const marked = prev.map((m) =>
          m.id === rowId ? { ...m, clientVisibleAtMs: atMs } : m,
        )
        return rowKeys
          ? closeWorkSegment(marked, rowKeys, atMs, undefined, rowId)
          : marked
      })
    },
    [],
  )
  // Candidate Surface (Workspace 合同 v4.2 C8-c): tool-time sets accumulate
  // outside the visible timeline. Only the final reply's actual prose drain
  // releases them, once, directly behind that reply; interim prose never
  // reveals a player. Idempotent set/selection frames still repaint an
  // existing card in place. Legacy frames without a turn keep their standalone
  // read tolerance. Live-born rows and pending sets roll back if their turn
  // fails; completed turns persist the same post-reply order in candidates_log.
  const liveCandidateRowsRef = useRef<Set<string>>(new Set())
  const pendingCandidateRowsRef = useRef<OverlayMessage[]>([])
  const candidateTurnSnapshotRef = useRef<Map<string, number[]>>(new Map())
  const handleCandidatesFrame = useCallback((event: CandidateEventPayload) => {
    const at = new Date().toISOString()
    if (event.kind === "set" || event.kind === "sfx_set" || event.kind === "music_set" || event.kind === "video_preset_set") {
      liveCandidateRowsRef.current.add(`live-cand-${event.candidate_set_id}`)
    }
    if (event.kind === "selection" || event.turn_id) {
      pendingCandidateRowsRef.current = reduceCandidateFrame(
        pendingCandidateRowsRef.current,
        event,
        at,
      )
    }
    setMessages((prev) => {
      const exists = prev.some(
        (message) => message.candidates?.candidateSetId === event.candidate_set_id,
      )
      if (!exists && (event.kind === "selection" || event.turn_id)) return prev
      return reduceCandidateFrame(prev, event, at)
    })
  }, [])
  // C8-c 失败回滚: drop the live candidate rows born by THIS turn (the
  // server rolled their door writes back with it; the committed earlier
  // turns' rows are immune — the ref clears at every turn's start).
  const rollbackCandidateRows = useCallback(() => {
    pendingCandidateRowsRef.current = []
    const doomed = liveCandidateRowsRef.current
    const selections = candidateTurnSnapshotRef.current
    setMessages((prev) => prev
      .filter((m) => !doomed.has(m.id))
      .map((m) => {
        if (!m.candidates) return m
        const selected = selections.get(m.candidates.candidateSetId)
        return selected && m.candidates.selected !== selected
          ? { ...m, candidates: { ...m.candidates, selected: [...selected] } }
          : m
      }))
    doomed.clear()
  }, [])
  const [input, setInput] = useState("")
  const [mentions, setMentions] = useState<ChatMention[]>([])
  const [selectedSkill, setSelectedSkill] = useState<SkillOption | null>(null)
  const [skillOptions, setSkillOptions] = useState<SkillOption[]>([])
  const rememberSkillOption = useCallback((option: SkillOption | null) => {
    if (!option) return
    setSkillOptions((current) =>
      current.some((item) => sameSkillReference(item.reference, option.reference))
        ? current
        : [...current, option],
    )
  }, [])
  const handleSkillChange = useCallback((option: SkillOption | null) => {
    setSelectedSkill(option)
    rememberSkillOption(option)
  }, [rememberSkillOption])
  const [chatBusy, setChatBusy] = useState(false)
  const [stopPending, setStopPending] = useState(false)
  const [runCancelPending, setRunCancelPending] = useState(false)
  // Typewriter busy/idle edge. The bottom now seat also requires an actually
  // released non-whitespace fragment: buffered envelope text is not visible
  // prose. An existing current fold owns the live label in place and seals
  // on speechSegments' first-visible signal, not on this flag alone.
  const [proseActive, setProseActive] = useState(false)
  // The editor is DOM-owned (MentionEditor): `input`/`mentions` are its
  // onChange mirrors, kept only as the send payload; the live-text ref backs
  // the failed-turn rollback's "don't clobber fresh typing" guard.
  const editorRef = useRef<MentionEditorHandle>(null)
  const inputMirrorRef = useRef("")
  const handleEditorChange = useCallback(
    (text: string, ms: ChatMention[]) => {
      inputMirrorRef.current = text
      setInput(text)
      setMentions(ms)
    },
    [],
  )
  // Plan versions (2026-08-05 refinement-flow rework; 2026-08-06 in-flight
  // rework): the LIVE plan renders as the bottom-most card while settled;
  // during an in-flight turn it UNPINS — anchored inline right after the
  // echo bubble that docked it (above the new user bubble + thinking row),
  // so the stale confirm dock can hide and the flow reads chronologically.
  // When the turn lands, the superseded plan collapses into a version chip
  // at that same anchor (expandable read-only snapshot, restorable — chat
  // edits the plan, nothing is locked) and the fresh card pins bottom.
  // livePlanMessageId = the echo bubble of the turn that docked the current
  // plan; null on restored sessions (no bubble exists → the card carries its
  // own echo line and stays pinned).
  const [livePlanMessageId, setLivePlanMessageId] = useState<string | null>(null)
  const [planVersions, setPlanVersions] = useState<
    { messageId: string; plan: InferredIntent }[]
  >([])
  const [expandedVersion, setExpandedVersion] = useState<number | null>(null)
  // The demotion snapshot must capture the plan as it stands AT DOCK TIME
  // (the panel stays editable while a refinement turn is in flight).
  const intentRef = useRef(intent)
  useEffect(() => {
    intentRef.current = intent
  }, [intent])
  // Mid-conversation uploads (the chat input's attach button) STAGE inside
  // the input group as lifecycle chips (uploading → done/error) and ride the
  // next send — picking a file never sends anything by itself.
  const [staged, setStaged] = useState<StagedUpload[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  // Source materials shown as attachments on the opening prompt.
  const [assets, setAssets] = useState<ProjectAsset[]>([])

  const firstMessageSentRef = useRef(false)
  const [openingHistory, setOpeningHistory] = useState<"loading" | "empty" | "occupied" | "failed">("loading")
  const [historyAttempt, setHistoryAttempt] = useState(0)
  const abortRef = useRef<AbortController | null>(null)
  const activeChatStopRef = useRef<ActiveChatStop | null>(null)
  /** The Turn owning the global pending flag; late old requests cannot clear
   * or retain a successor Turn's Stop control. */
  const stopPendingOwnerRef = useRef<ActiveChatStop | null>(null)
  /** Dead-stream machinery (see the module constants): the last frame's
   * receipt stamp (the watchdog's liveness read), the dead flag (set before
   * any machinery-triggered abort so the catch/continuation bail to the
   * reconcile), the reconcile's generation + running guards, and the server
   * row ids the reconcile already rendered (double-render guard vs a
   * hung continuation resuming late). */
  const lastFrameAtRef = useRef(0)
  const turnStartMsRef = useRef(0)
  const deadStreamRef = useRef(false)
  // 终帧落旗: set the moment the turn.completed envelope arrives — the pipe
  // is DONE then (no frame ever follows), so the dead-stream machinery's
  // whole domain ends there. The watchdog and the visibility trigger both
  // retire on this flag: post-terminal silence is expected, never death.
  const terminalReceivedRef = useRef(false)
  const reconcileGenRef = useRef(0)
  const reconcileRunningRef = useRef<number | null>(null)
  const reconciledIdsRef = useRef<Set<string>>(new Set())
  const projectChangedRef = useRef(onProjectChanged)
  projectChangedRef.current = onProjectChanged

  const {
    steps,
    status,
    terminal,
    terminalSource,
    createdAt: runCreatedAt,
    uploadRetryCount,
  } = useRunEvents(runId, undefined, runAttempt)
  const currentUploadRetryCount = Math.max(uploadRetryCount, runAttemptUploadRetry)
  const currentUploadRetryCountRef = useRef(currentUploadRetryCount)
  currentUploadRetryCountRef.current = currentUploadRetryCount
  const currentRunAttempt: RunAttemptKey | null = runId
    ? { runId, attempt: runAttempt }
    : null
  const currentRunAttemptRef = useRef<RunAttemptKey | null>(currentRunAttempt)
  currentRunAttemptRef.current = currentRunAttempt
  // The run-delivery segment has its own write-once clock per attachment
  // attempt. Old deliveries and old async continuations cannot seal recovery.
  const [runWorkSeal, setRunWorkSeal] = useState<RunWorkSeal | null>(null)
  const runWorkSealRef = useRef<RunWorkSeal | null>(null)
  const [reviewExpiredAttempt, setReviewExpiredAttempt] = useState<RunAttemptKey | null>(null)
  useEffect(() => {
    runWorkSealRef.current = null
    setRunWorkSeal(null)
    setReviewExpiredAttempt(null)
    setRunCancelPending(false)
  }, [runId, runAttempt])
  const sealRunWorkSegment = useCallback((targetRunId: string, endedAtMs: number) => {
    const attempt = runAttemptRef.current
    const next = nextRunWorkSeal(runWorkSealRef.current, currentRunAttemptRef.current, {
      runId: targetRunId,
      attempt,
      endedAtMs,
    })
    if (next === runWorkSealRef.current) return
    runWorkSealRef.current = next
    setRunWorkSeal(next)
  }, [])
  // Ref mirror: sendChat's async continuation must read the live terminal
  // state, not a stale closure.
  const terminalRef = useRef(terminal)
  useEffect(() => {
    terminalRef.current = terminal
    if (terminal) setRunCancelPending(false)
  }, [terminal])

  // Phase 3 Batch B (裁决 1, 2026-09-20): the confirm beat is a DERIVED
  // predicate, never a phase — readiness comes from the server-named stamp
  // alone (PLAN_READY), plus the dock's own facts: a plan actually landed
  // (intentReady) and no run is live (runAttached = runId ∧ ¬terminal — the
  // post-terminal refinement's new plan must be able to raise the beat
  // again, so the conjunct is run LIVENESS, not run existence). The
  // envelope→stamp window (a live dock's pill waits one refetch) is accepted
  // by the ruling: the conservative direction, and the birthplace 422 guards
  // for real. No lifecycle decision is ever re-derived locally.
  const runAttached = runId != null && !terminal
  const confirmActive = intentReady && isPlanReady(lifecycle) && !runAttached

  // The pending question is a plain DB row — fetching the project
  // conversation rebuilds the dock after refresh / on any device, whatever
  // the phase (task_book while confirming, question once the chat loop asks).
  const fetchPendingQuestion = useCallback(async (): Promise<QuestionMessage | null> => {
    try {
      const res = await apiFetch(`/api/v1/chat/conversation?project_id=${projectId}`, {
        toast: false,
      })
      if (!res.ok) return null
      const data = (await res.json()) as { pending_question?: QuestionMessage | null }
      return data.pending_question ?? null
    } catch {
      return null
    }
  }, [projectId])

  /** One server-born speech path for trigger arrival and disconnect recovery.
   * The first actually released non-whitespace fragment marks the message
   * and seals ONLY the matching run-delivery segment. Buffered text, empty
   * fragments and unrelated assistant rows never close it. */
  const pacePersistedMessage = useCallback(
    async (
      wire: {
        id: string
        content?: string | null
        created_at?: string
        workflow_run_id?: string | null
        turn_id?: string | null
        intent?: unknown
        blocks?: QuestionMessage["blocks"]
        seq?: number | null
      },
      {
        suggestions,
        sealRunId = null,
        workerOpeningId,
        fresh = true,
      }: {
        suggestions?: SuggestionPill[]
        sealRunId?: string | null
        workerOpeningId?: string | null
        fresh?: boolean
      } = {},
    ) => {
      const row = journeyTranscriptRow(wire)
      noteObservedSeq(row.seq)
      const runDelivery = triggerSuggestions(row.intent) !== undefined
      const runDeliveryRef = triggerDeliveryRef(row.intent)
      const message = buildRecoveredProseMessage({
        id: row.id,
        seq: row.seq,
        createdAt: row.created_at,
        turnId: row.turn_id,
        runId: row.workflow_run_id,
        blocks: row.blocks,
        runDelivery,
        runDeliveryRef,
        outputRefs: triggerOutputRefs(row.intent),
      })
      message.mediaProgress = mediaProgress(wire)
      message.mediaOpeningId = journeyMark(wire)?.openingId
      message.sceneOrder = sceneOrder(wire)
      message.activity = preparationActivity(wire)
      message.continuationTurnId = continuationTurnId(wire, workerOpeningId)
      setMessages((prev) => insertRecoveredMessage(prev, message, { fresh }))
      const text = (row.content ?? "").trim()
      let visibleLength = 0
      let sawVisible = false
      const tw = createTypewriter((fragment) => {
        if (!sawVisible && fragment.trim().length > 0) {
          sawVisible = true
          const atMs = Date.now()
          noteSpeechVisible(row.id, atMs)
          if (
            runDelivery && sealRunId &&
            terminalRef.current &&
            isCurrentRunAttemptDelivery(
              { runId: sealRunId, runDelivery: true, runDeliveryRef },
              runIdRef.current,
              currentUploadRetryCountRef.current,
            )
          ) {
            sealRunWorkSegment(sealRunId, atMs)
          }
        }
        // Two reads can observe this server row before React commits the first.
        visibleLength += fragment.length
        const visibleText = text.slice(0, visibleLength)
        setMessages((prev) => prev.map((m) =>
          m.id === row.id && m.streaming && m.content.length < visibleText.length
            ? { ...m, content: visibleText } : m,
        ))
      }, setProseActive)
      // Server-born prose still paces out; never flush the whole row.
      tw.push(text)
      await tw.drain()
      tw.flush()
      setMessages((prev) =>
        prev.map((m) =>
          m.id === row.id
            ? {
                ...m,
                streaming: false,
                proseDrainedAtMs: m.proseDrainedAtMs ?? Date.now(),
                ...(suggestions === undefined ? {} : { suggestions }),
              }
            : m,
        ),
      )
    },
    [noteObservedSeq, noteSpeechVisible, sealRunWorkSegment],
  )

  /** The panel's task plan + reasons live on the project (pending_brief) —
   * refetched after every plan-path turn (first inference, refinements).
   * `derived` is the server-compiled preview riding the same row. */
  const fetchPendingBrief = useCallback(async (): Promise<{
    intent: unknown
    brief?: unknown
    reasons?: string[]
    persona_id?: string | null
    derived?: DerivedRow[]
    plans?: DecisionPlanRow[]
    video_presentation?: VideoPresentationRecoveryFact | null
  } | null> => {
    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/results`, {
        toast: false,
      })
      if (!res.ok) return null
      const data = (await res.json()) as { pending_brief?: {
        intent: unknown
        brief?: unknown
        reasons?: string[]
        persona_id?: string | null
        derived?: DerivedRow[]
        plans?: DecisionPlanRow[]
        video_presentation?: VideoPresentationRecoveryFact | null
      } | null }
      return data.pending_brief ?? null
    } catch {
      return null
    }
  }, [projectId])

  const refreshPresentationRecovery = useCallback(async () => {
    const generation = ++presentationRecoveryGenRef.current
    const pending = await fetchPendingBrief()
    if (generation === presentationRecoveryGenRef.current) {
      setPresentationRecovery(pending?.video_presentation ?? null)
    }
    return pending
  }, [fetchPendingBrief])

  useEffect(() => {
    void refreshPresentationRecovery()
  }, [refreshPresentationRecovery])

  useEffect(() => {
    let cancelled = false
    fetchPendingQuestion().then((q) => {
      if (!cancelled) {
        setPendingQuestion(dockWorthyQuestion(q))
      }
    })
    return () => {
      cancelled = true
    }
  }, [fetchPendingQuestion])

  // Confirm-phase archive replay (B1): the conversation's message rows are
  // the durable record — on open, rebuild the flow from them so a refresh or
  // another device no longer loses capability answers / past refinements.
  // 归档单一源: every archived row renders, the opener included (no prop
  // lane, no skip predicate). 形态律 (ADR-053 R1): a still-pending
  // OPTIONS question docks above the input (the fetch effect holds it),
  // never in the flow; a TEXT question (options-empty) IS a plain flow
  // message, pending or answered. Best-effort: the live flow works without
  // it.
  const [historySettled, setHistorySettled] = useState(false)
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let watchingMedia = false
    setHistorySettled(false)
    const load = async () => {
      try {
        const convRes = await apiFetch(`/api/v1/chat/conversation?project_id=${projectId}`, {
          toast: false,
        })
        if (convRes.status === 404) {
          if (!cancelled) setOpeningHistory("empty")
          return
        }
        if (!convRes.ok) throw new Error("Conversation unavailable")
        const conv = (await convRes.json()) as { id?: string }
        if (!conv.id) throw new Error("Conversation unavailable")
        const res = await apiFetch(`/api/v1/chat/conversations/${conv.id}/messages`, {
          toast: false,
        })
        if (!res.ok) throw new Error("History unavailable")
        const data = (await res.json()) as { items?: HistoryRow[] }
        // The row→flow mapping is the extracted PURE seam (timeline/history.ts,
        // Phase 3 Batch A) — same branches, zero lifecycle derivation: a
        // refresh reads the archive, readiness comes from the stamp alone.
        if (!Array.isArray(data.items)) throw new Error("Invalid history")
        const rows = data.items
        if (!cancelled) setOpeningHistory(rows.some((row) => row.role === "user") ? "occupied" : "empty")
        const active = new Set(rows.filter((r) => r.turn_state === "in_flight").map((r) => r.id))
        watchingMedia = rows.some((r) => {
          const intent = r.intent as { media_status?: string; media_result?: unknown } | null
          return r.turn_id && active.has(r.turn_id) && (intent?.media_status === "accepted" || intent?.media_result)
        })
        const history = mapHistoryRows(rows, { t })
        // Fill missing archive rows at their persisted seq positions. Live
        // rows keep their identity and typing state; a recovered live tail
        // cannot pull the final archive reply ahead of its own activities.
        if (!cancelled) {
          const loaded = latestJourneyMark(data.items ?? [], null)
          if (loaded) setJourneyReadSeq((seq) => Math.max(seq, loaded.seq))
          observeJourney(data.items ?? [])
          for (const row of data.items ?? []) noteObservedSeq(row.seq)
          if (history.length > 0) {
            const settled = new Map(history.filter((m) => m.activity && m.activity.status !== "active")
              .map((m) => [m.id, m.activity]))
            setMessages((prev) => prependMissingHistory(prev.map((m) =>
              m.activity?.status === "active" && settled.has(m.id)
                ? { ...m, activity: settled.get(m.id) } : m), history))
          }
        }
      } catch {
        if (!cancelled) setOpeningHistory("failed")
      } finally {
        if (!cancelled) setHistorySettled(true)
        if (!cancelled && watchingMedia) timer = setTimeout(load, 2500)
      }
    }
    void load()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, historyAttempt])

  // Mid-run dock revival (期 4): the direction interrupt docks its question
  // while the run is already streaming — when a waiting interrupt step
  // appears in the SSE flow, re-fetch the pending question so it docks
  // above the input. A null fetch result keeps the dock empty (already
  // answered elsewhere), and the step leaving waiting ends the watch.
  useEffect(() => {
    if (pendingQuestion) return
    if (!steps.some((s) => s.kind === "interrupt" && s.status === "waiting")) return
    let cancelled = false
    fetchPendingQuestion().then((q) => {
      if (!cancelled) setPendingQuestion((prev) => prev ?? dockWorthyQuestion(q))
    })
    return () => {
      cancelled = true
    }
  }, [steps, pendingQuestion, fetchPendingQuestion])

  // Stale-dock clear: the server can settle the docked interrupt question
  // without a client action — the expiry sweep's auto-answer, or an answer
  // from another device. When this run's interrupt step leaves waiting,
  // re-fetch and drop the dock if nothing is pending anymore.
  useEffect(() => {
    if (!pendingQuestion || pendingQuestion.workflow_run_id !== runId) return
    if (steps.some((s) => s.kind === "interrupt" && s.status === "waiting")) return
    let cancelled = false
    fetchPendingQuestion().then((q) => {
      if (!cancelled && !dockWorthyQuestion(q)) setPendingQuestion(null)
    })
    return () => {
      cancelled = true
    }
  }, [steps, pendingQuestion, runId, fetchPendingQuestion])

  // ── 触发回合的到达通道 (T3, ADR-077 判词③) ─────────────────────────
  // Trigger turns land as assistant rows (intent.type === "trigger_review")
  // OUTSIDE any request the dock made: the understanding-warmed beat fires
  // while assets process (pre-first-run, journey 一②), the closing reviewer
  // lands seconds after the run's terminal frame (journey 一⑦). The dock
  // polls the conversation while either window is open; each unseen trigger
  // row types out through its own typewriter (打字机律 — server-born prose
  // never blobs in), and the question docks only after the prose drains
  // (散文在先、提问随后): NEW rows carry a real options question (ADR-081 —
  // the numbered OptionDock), LEGACY rows replay their intent-dump pills.
  // The settle rides the existing agent-speech recall funnel (a tucked-away
  // dock resurfaces on its own — 唤回复用, zero new machinery).
  const messagesRef = useRef<OverlayMessage[]>(messages)
  // Stop reads the latest committed render synchronously; an effect-deferred
  // mirror could miss the final visible typewriter frame.
  messagesRef.current = messages
  const triggerInFlight = useRef<Set<string>>(new Set())

  const pollTriggerMessages = useCallback(async ({
    includeActivityRows = true,
    reviewRunId = null,
    openingId = null,
    onJourneyRun,
    signal,
  }: {
    openingId?: string | null
    onJourneyRun?: (runId: string, rowSeq: number) => void
    signal?: AbortSignal
    includeActivityRows?: boolean
    reviewRunId?: string | null
  } = {}): Promise<void> => {
    try {
      const convRes = await apiFetch(`/api/v1/chat/conversation?project_id=${projectId}`, {
        toast: false, signal,
      })
      if (!convRes.ok) return
      const conv = (await convRes.json()) as { id?: string }
      if (!conv.id) return
      const res = await apiFetch(`/api/v1/chat/conversations/${conv.id}/messages`, {
        toast: false, signal,
      })
      if (!res.ok) return
      const data = (await res.json()) as {
        items?: (QuestionMessage & { role: "user" | "assistant" | "system" })[]
      }
      if (signal?.aborted) return
      const rows = data.items ?? []
      let latestStart: { runId: string; seq: number } | undefined
      const observedBefore = observedMessageSeq(
        observedSeqRef.current,
        messagesRef.current,
      )
      // The response advances the observation watermark immediately; each
      // admission decision below still compares with the PRE-response tail.
      for (const row of rows) noteObservedSeq(row.seq)
      for (const row of rows) {
        if (signal?.aborted) return
        if (row.role !== "assistant") continue
        const mark = journeyMark(row)
        const sameTurnActivity = row.turn_id === openingId &&
          (activityRowFrame(row.intent) !== undefined || (row.intent as { type?: string } | null)?.type === "interim_prose")
        if (openingId && !(mark ? mark.openingId === openingId : sameTurnActivity)) continue
        // 永不渲染行 (ADR-108): the rejection forensics ledger / legacy
        // aggregate logs never enter the flow.
        if (isNonRenderIntent(row.intent)) continue
        const fresh = isFreshPolledRow(row.seq, observedBefore)
        const beat = includeActivityRows ? activityRowFrame(row.intent) : undefined
        if (beat !== undefined) {
          const existing = messagesRef.current.find((m) => m.id === row.id)
          if (existing?.activity?.status === "active" && (
            beat.status !== "active" || existing.activity.key !== beat.key ||
            existing.activity.count !== beat.count || existing.activity.total !== beat.total
          )) {
            setMessages((previous) => previous.map((m) => m.id === row.id
              ? { ...m, activity: { ...m.activity, ...beat } } : m))
          }
          if (existing || !fresh) continue
          const recovered = buildRecoveredActivityRow({
            id: row.id,
            seq: row.seq,
            createdAt: row.created_at,
            turnId: row.turn_id,
            beat,
          })
          if (recovered.registerHost) currentActivityRowKeysRef.current.add(row.id)
          setMessages((prev) =>
            insertRecoveredMessage(prev, recovered.message, { fresh: true }),
          )
          continue
        }
        // Current server rows always carry seq. A null-seq row is legacy
        // archive, never a new live-tail arrival; mount replay still renders
        // it with read tolerance.
        if (row.seq == null) continue
        const suggestions = triggerSuggestions(row.intent)
        if (openingId && row.workflow_run_id && mark?.state === "active" && suggestions === undefined) {
          latestStart = { runId: row.workflow_run_id, seq: row.seq }
        }
        if (!openingId && suggestions === undefined) continue
        // A generic watch never backfills old speech. Run review admits only
        // its own delivery/failure row; an unrelated trigger is not this
        // window's to recover, even when it is new to this client.
        if (!openingId && !shouldAdmitPolledTrigger({
          fresh,
          reviewRunId,
          rowRunId: row.workflow_run_id,
        })) {
          continue
        }
        // Dedup by the SERVER row id — the archive replay and a previous
        // poll arrival land under the same id, so the row is known if it is
        // in the flow already or mid-typing. A PENDING options question
        // replays as its echo row (`${id}-echo`, 形态律 replay), so that
        // alias counts as known too — without it a refresh inside a watch
        // window re-types the review under the bare id.
        if (triggerInFlight.current.has(row.id)) continue
        const existing = messagesRef.current.find((message) => belongsToServerRow(message, row.id))
        if (existing) {
          // A restarted worker can settle the same receipt in place.
          const settled = journeyTranscriptRow(row)
          if (mark && mark.state !== "active" && !existing.streaming &&
              (existing.content !== (settled.content ?? "") || !!existing.mediaProgress !== mediaProgress(row) ||
               JSON.stringify(existing.blocks ?? []) !== JSON.stringify(settled.blocks ?? []))) {
            setMessages((previous) => previous.map((message) => message.id === existing.id
              ? { ...message, content: settled.content ?? "", blocks: settled.blocks,
                  mediaProgress: mediaProgress(row), continuationTurnId: continuationTurnId(row, openingId) }
              : message))
          }
          continue
        }
        triggerInFlight.current.add(row.id)
        try {
          await pacePersistedMessage(row, {
            suggestions,
            sealRunId: row.workflow_run_id,
            workerOpeningId: openingId,
            fresh,
          })
          // 选项语法统一律 (ADR-081): a NEW-shape trigger row carries its
          // suggestions as a real options question (question payload) —
          // dock it once the prose has drained (提问随后, same law the
          // legacy pills follow). Legacy rows skip this (their chips are
          // already attached above).
          if (!row.answer && (row.question?.options?.length ?? 0) > 0) {
            const q = await fetchPendingQuestion()
            setPendingQuestion((prev) => prev ?? dockWorthyQuestion(q))
          }
        } finally {
          triggerInFlight.current.delete(row.id)
        }
      }
      if (signal?.aborted) return
      const markedRows = openingId ? rows.filter((row) => journeyMark(row)?.openingId === openingId) : rows
      if (latestStart && latestJourneyMark(markedRows, null)?.state === "active") {
        onJourneyRun?.(latestStart.runId, latestStart.seq)
      }
      // A run-scoped poll may discover the first mark. Only a journey-scoped
      // read can finish the watch, after admitting all its rows through the terminal one.
      if (openingId) {
        const latest = latestJourneyMark(markedRows, null)
        if (latest) setJourneyReadSeq((seq) => Math.max(seq, latest.seq))
      }
      if (openingId || !journeyOpeningId) observeJourney(markedRows)
    } catch {
      /* server-born speech is best-effort — the replay rebuilds on refresh */
    }
  }, [projectId, fetchPendingQuestion, pacePersistedMessage, noteObservedSeq, journeyOpeningId, observeJourney])

  // Load the project's assets for the prompt attachments — once on mount,
  // and again after a chat turn when the project started empty: the plan
  // path promotes user-declared pasted text ("this is my transcript: …")
  // into a real transcript asset mid-turn, and it must show up. Declared
  // above the watch windows — their effects consume it in dependency arrays,
  // which evaluate at render (TDZ).
  const fetchAssets = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/assets`, {
        toast: false,
      })
      if (res.ok) setAssets((await res.json()) as ProjectAsset[])
    } catch {
      /* attachment refresh is best-effort */
    }
  }, [projectId])

  useEffect(() => {
    void fetchAssets()
  }, [fetchAssets])

  /** Dead-stream reconcile (see the module constants): the stream was
   * declared dead (watchdog silence / visibility-resume with a stale pipe)
   * and aborted — but the turn commits server-side regardless, so the
   * archive is the truth. Poll the conversation for the turn's landed
   * assistant rows and pace them in through the typewriter (the trigger
   * channel's same law — server-born prose never blobs), dock a pending ask
   * if the turn left one, and release the composer. InterimProse / activity
   * rows are skipped: the live flow already showed them (or they replay on
   * refresh) — the ANSWER is the substance. Generation-guarded: a new turn
   * kills a running reconcile. On the cap the honest grey row says the
   * connection died — the turn may still land; a refresh catches it. */
  const reconcileTurn = useCallback(
    async (turnStartMs: number, gen: number) => {
      if (reconcileRunningRef.current !== null) return
      reconcileRunningRef.current = gen
      sseProbe("reconcile.start", { turnStartMs })
      const deadline = Date.now() + RECONCILE_CAP_MS
      try {
        while (gen === reconcileGenRef.current && Date.now() < deadline) {
          await new Promise((r) => setTimeout(r, RECONCILE_POLL_MS))
          if (gen !== reconcileGenRef.current) return
          let rows: (QuestionMessage & {
            role: string
            intent?: unknown
            created_at?: string
          })[]
          try {
            const convRes = await apiFetch(
              `/api/v1/chat/conversation?project_id=${projectId}`,
              { toast: false },
            )
            if (!convRes.ok) continue
            const conv = (await convRes.json()) as { id?: string }
            if (!conv.id) continue
            const res = await apiFetch(
              `/api/v1/chat/conversations/${conv.id}/messages`,
              { toast: false },
            )
            if (!res.ok) continue
            rows = ((await res.json()) as { items?: typeof rows }).items ?? []
            for (const row of rows) noteObservedSeq(row.seq)
          } catch {
            continue
          }
          const fresh = rows.filter(
            (r) =>
              r.role === "assistant" &&
              Date.parse(r.created_at ?? "") > turnStartMs &&
              !isNonRenderIntent(r.intent) &&
              (r.intent as { type?: string } | undefined)?.type !==
                "interim_prose" &&
              activityRowFrame(r.intent) === undefined &&
              !reconciledIdsRef.current.has(r.id) &&
              !messagesRef.current.some((m) => m.id === r.id),
          )
          if (fresh.length === 0) continue
          sseProbe("reconcile.rows", { fresh: fresh.length })
          for (const row of fresh) {
            if (gen !== reconcileGenRef.current) return
            reconciledIdsRef.current.add(row.id)
            await pacePersistedMessage(row, {
              sealRunId:
                triggerSuggestions(row.intent) !== undefined
                  ? row.workflow_run_id
                  : null,
            })
          }
          // The turn's terminal artifacts are in — dock a pending ask if the
          // turn left one, refresh attachments, settle the line, release the
          // composer.
          sseProbe("reconcile.done")
          const q = await fetchPendingQuestion()
          await refreshPresentationRecovery()
          setPendingQuestion((prev) => prev ?? dockWorthyQuestion(q))
          void fetchAssets()
          settleActivities("completed")
          setThinkingPhase(null)
          abortRef.current = null
          setChatBusy(false)
          return
        }
        if (gen !== reconcileGenRef.current) return
        sseProbe("reconcile.cap")
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: t("chat.connectionLost"),
            turnId: adoptCurrentTurnId(),
            meta: "error",
            at: new Date().toISOString(),
          },
        ])
        // 假活跃禁令 (T16-B client twin — the cap's own seat): the turn is
        // declared lost and the composer releases, so no live label may keep
        // narrating work the client can no longer see. chatBusy gates the
        // label; this sweep also settles the durable active frames so a
        // later render cannot revive them. cancelled = the attempt was cut
        // off — the server may still land it; a refresh replays its truth.
        settleActivities("cancelled")
        setThinkingPhase(null)
        abortRef.current = null
        setChatBusy(false)
      } finally {
        if (reconcileRunningRef.current === gen) {
          reconcileRunningRef.current = null
        }
      }
    },
    [projectId, fetchPendingQuestion, refreshPresentationRecovery, fetchAssets, settleActivities, pacePersistedMessage, noteObservedSeq, t],
  )
  const reconcileTurnRef = useRef(reconcileTurn)
  useEffect(() => {
    reconcileTurnRef.current = reconcileTurn
  }, [reconcileTurn])

  // sse-probe: state flips (TEMPORARY forensics — delete with the probe)
  useEffect(() => {
    sseProbe("state.chatBusy", { value: chatBusy })
  }, [chatBusy])

  // Visibility trigger (same machinery): a page frozen mid-turn (background
  // tab / screen lock suspends the typewriter's timers — the SSE pipe itself
  // stays alive) wakes to a stream whose continuation may never run; a pipe
  // that died while hidden wakes to a fetch that will never error. Either
  // way the signature is identical: busy + no frame for longer than the
  // server's guaranteed cadence. Abandon the zombie and reconcile.
  useEffect(() => {
    const onVisible = () => {
      sseProbe("visibility", {
        state: document.visibilityState,
        busy: abortRef.current !== null,
        silenceMs: Date.now() - lastFrameAtRef.current,
      })
      if (document.visibilityState !== "visible") return
      if (abortRef.current === null) return
      // Post-terminal the pipe is DONE by definition: the wake's "no frame
      // for >45s" signature misfires on a healthy completed turn whose
      // typewriter is still pacing (hidden-tab throttle stretches the drain
      // past the silence gate) — reconcile here would only twin the row the
      // envelope is already rendering.
      if (terminalReceivedRef.current) return
      if (Date.now() - lastFrameAtRef.current <= STREAM_SILENCE_DEAD_MS) return
      sseProbe("visibility.dead")
      deadStreamRef.current = true
      abortRef.current?.abort()
      void reconcileTurnRef.current(turnStartMsRef.current, reconcileGenRef.current)
    }
    document.addEventListener("visibilitychange", onVisible)
    return () => document.removeEventListener("visibilitychange", onVisible)
  }, [])

  // Refresh the project lifecycle when a staged asset finishes processing.
  const assetsSigRef = useRef<string | null>(null)
  useEffect(() => {
    const sig = assets
      .map((a) => `${a.id}:${a.processing_status ?? ""}`)
      .join("|")
    const prev = assetsSigRef.current
    assetsSigRef.current = sig
    if (prev !== null && prev !== sig) void projectChangedRef.current()
  }, [assets])

  // Send gate (2026-09-28 user ruling — 暂存 ≠ 交付): the conversation's
  // material activity reads ONLY assets a message has carried. `assets`
  // itself is the project's full list — a staged-but-unsent upload is real
  // project material (processing starts at upload; the canvas may show its
  // card) but it is not the agent's to narrate until the user sends it.
  const sentAssetIds = useMemo(
    () => new Set(messages.flatMap((m) => (m.assets ?? []).map((a) => a.id))),
    [messages],
  )
  /** Honest preprocess copy (chat-flow-sequencing 验收 5): with zero file
   * uploads the preprocess node validates material / admits the writer
   * lift — "Analyzing your uploads…" would be a lie. */
  const hasUploads = assets.some((a) => a.file_url)

  // Processing watch: sent assets mid-processing — the tick refreshes the
  // asset rows (the chips' processing state and the now-line's reading rows
  // update on this cadence) and doubles as the trigger arrival channel while
  // the batch drains (ADR-102: the understanding beat/review is retired —
  // nothing proactive rides the settlement edge anymore).
  const assetsProcessing = assets.some(
    (a) =>
      sentAssetIds.has(a.id) &&
      (a.processing_status === "pending" ||
        a.processing_status === "processing"),
  )
  useEffect(() => {
    if (!assetsProcessing || journeyOpeningId) return
    // Open the observation baseline before the first tick; beats already in
    // this snapshot are archive, beats extending it afterwards are live.
    void pollTriggerMessages()
    const id = setInterval(() => {
      void fetchAssets()
      void pollTriggerMessages()
    }, 3000)
    return () => clearInterval(id)
  }, [assetsProcessing, journeyOpeningId, fetchAssets, pollTriggerMessages])

  // Watch window (run terminal → current-attempt delivery reply). Historical
  // hydration settles from real rows; only an explicit live attachment uses
  // the bounded 60s no-reply wait. Expiry stops the shimmer, not late polling.
  const reviewerLanded = runReviewerLanded(messages, runId, currentUploadRetryCount)
  const reviewExpired = sameRunAttempt(reviewExpiredAttempt, currentRunAttempt)
  const historicalTerminal = isHistoricalRunTerminal({
    terminal,
    terminalSource,
    runStartedExplicitly,
  })
  const historicalReviewSettled = historicalTerminal && historySettled
  const reviewPending =
    terminal &&
    status !== "cancelled" &&
    runId != null &&
    !reviewerLanded &&
    !reviewExpired &&
    !historicalTerminal
  const runWorkEndedAtMs = runWorkSeal && sameRunAttempt(runWorkSeal, currentRunAttempt)
    ? runWorkSeal.endedAtMs
    : null
  useEffect(() => {
    if (journeyOpeningId || !terminal || !runId || reviewerLanded || status === "cancelled" || !historySettled) return
    const attemptKey = { runId, attempt: runAttempt }
    if (historicalReviewSettled) {
      if (!reviewExpired) {
        setReviewExpiredAttempt(attemptKey)
        sealRunWorkSegment(runId, runStepEndMs(runCreatedAt, steps) ?? Date.now())
      }
      return
    }
    const startedAt = Date.now()
    const poll = () => {
      if (!sameRunAttempt(currentRunAttemptRef.current, attemptKey)) return
      void pollTriggerMessages({ includeActivityRows: false, reviewRunId: runId })
    }
    poll()
    const id = setInterval(() => {
      if (!sameRunAttempt(currentRunAttemptRef.current, attemptKey)) return
      if (!reviewExpired && Date.now() - startedAt > 60_000) {
        setReviewExpiredAttempt(attemptKey)
        sealRunWorkSegment(runId, runStepEndMs(runCreatedAt, steps) ?? startedAt)
      }
      // Keep admitting a genuinely late delivery after the visual seal. Its
      // arrival disables the zero-delivery fallback in the same render.
      poll()
    }, 3000)
    return () => clearInterval(id)
  }, [
    terminal,
    terminalSource,
    status,
    runId,
    runAttempt,
    reviewerLanded,
    reviewExpired,
    historicalReviewSettled,
    historySettled,
    journeyOpeningId,
    pollTriggerMessages,
    runCreatedAt,
    steps,
    sealRunWorkSegment,
  ])

  // The output mention's candidate feed (reference family, MENTIONS §2): a
  // pinned output id resolves the revision target deterministically
  // server-side. Refresh on mount and when a run lands terminal (new
  // outputs exist only then).
  const [outputs, setOutputs] = useState<Output[]>([])
  const [globalReferences, setGlobalReferences] = useState<{
    assets: { id: string; title: string; type: string }[]
    outputs: { id: string; name: string; type: string }[]
  }>({ assets: [], outputs: [] })
  const fetchOutputs = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/results`, {
        toast: false,
      })
      if (res.ok) {
        const data = (await res.json()) as { outputs?: Output[] }
        setOutputs(data.outputs ?? [])
      }
    } catch {
      /* mention feed refresh is best-effort */
    }
  }, [projectId])

  useEffect(() => {
    void fetchOutputs()
  }, [fetchOutputs, terminal])

  // Persistent delivery facts, including archived exact Outputs. The active
  // /results rows only fill the brief window before this projection refreshes.
  const [chatOutputEntries, setChatOutputEntries] = useState<ChatOutputEntry[] | null>(null)
  const [viewerOutputId, setViewerOutputId] = useState<string | null>(null)
  const deliveryMessageKey = messages
    .filter((message) => message.runId || message.outputRefs?.length)
    .map((message) => `${message.id}:${message.runId ?? ""}:${(message.outputRefs ?? []).join(",")}`)
    .join("|")
  useEffect(() => {
    let cancelled = false
    const refresh = () => apiFetch(`/api/v1/projects/${projectId}/chat/outputs`, { toast: false })
      .then(async (response) => {
        if (response.ok && !cancelled) {
          setChatOutputEntries((await response.json()) as ChatOutputEntry[])
        }
      })
      .catch(() => {})
    void refresh()
    // A delivery can finish in another tab while this viewer remains open.
    // Refresh its existing projection without changing the selected id.
    const interval = viewerOutputId ? setInterval(() => { void refresh() }, 5000) : null
    return () => {
      cancelled = true
      if (interval) clearInterval(interval)
    }
  }, [projectId, terminal, deliveryMessageKey, viewerOutputId])

  const chatOutputs = useMemo(() => {
    const byId = new Map(outputs.map((output) => [output.id, output]))
    for (const entry of chatOutputEntries ?? []) {
      if (entry.output) byId.set(entry.output_id, entry.output)
    }
    return [...byId.values()].filter(isChatVideoOutput)
  }, [outputs, chatOutputEntries])
  const runHasDelivery = hasAnyRunDelivery(messages, runId)
  const runFallbackOutputs = zeroDeliveryVideoOutputs({
    steps,
    outputs: chatOutputs,
    terminal,
    reviewSettled:
      reviewExpired ||
      historicalReviewSettled ||
      (status === "cancelled" && (runStartedExplicitly || historySettled)),
    hasDelivery: runHasDelivery,
  })

  // One Chat-hosted viewer: message rows supply only the exact Output id.
  const viewerTriggerRef = useRef<HTMLElement | null>(null)
  const chatContainerRef = useRef<HTMLDivElement>(null)
  const openOutputViewer = useCallback((outputId: string) => {
    viewerTriggerRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null
    setViewerOutputId(outputId)
  }, [])
  const closeOutputViewer = useCallback(() => {
    setViewerOutputId(null)
    requestAnimationFrame(() => {
      const trigger = viewerTriggerRef.current
      if (trigger?.isConnected) trigger.focus({ preventScroll: true })
      else chatContainerRef.current?.focus({ preventScroll: true })
    })
  }, [])
  const mentionViewerOutput = useCallback((output: Output, region?: MediaRegionSelection) => {
    editorRef.current?.insertMention({
      type: "output",
      id: output.id,
      label: outputMentionLabel(output, t(`chat.anchorCards.types.${output.type}`)),
      ...(region ? { region } : {}),
    })
    setViewerOutputId(null)
    requestAnimationFrame(() => editorRef.current?.focus())
  }, [t])

  useEffect(() => {
    let cancelled = false
    void apiFetch("/api/v1/chat/references", { toast: false }).then(async (res) => {
      if (res.ok) {
        const data = await res.json()
        if (!cancelled) setGlobalReferences(data)
      }
    }).catch(() => {})
    return () => { cancelled = true }
  }, [projectId, terminal])

  useEffect(() => {
    const controller = new AbortController()
    void fetchChatSkills(controller.signal)
      .then((response) => {
        setSkillOptions((current) => {
          const merged = [...current]
          for (const option of response.items) {
            const index = merged.findIndex((item) =>
              sameSkillReference(item.reference, option.reference),
            )
            if (index >= 0) merged[index] = option
            else merged.push(option)
          }
          return merged
        })
      })
      .catch(() => {})
    return () => controller.abort()
  }, [projectId])

  // Registry feeds handed to the editor's picker (memoized — the picker
  // reloads when the identity changes).
  const mentionContext = useMemo<MentionContext>(
    () => {
      // The owner-wide feed stays available for a future cross-project picker;
      // this project's @ surface admits only entities in its current results.
      const currentAssetIds = new Set(assets.map((asset) => asset.id))
      const currentOutputIds = new Set(outputs.map((output) => output.id))
      return {
        assets: [...new Map([...globalReferences.assets, ...assets].map((a) => [a.id, a])).values()]
          .filter((a) => currentAssetIds.has(a.id) && a.title)
          .map((a) => ({
            id: a.id,
            name: a.title as string,
            kind: assetTypeKind(a.type),
          })),
        outputs: [...new Map([
          ...globalReferences.outputs.map((o) => ({
            id: o.id,
            label: o.name || t("chat.videoStoryboard.title"),
            chipLabel: o.name || t("chat.videoStoryboard.title"),
            kind: o.type,
          })),
          ...outputs.map((o) => ({
            id: o.id,
            label: outputMentionName(o, t(`chat.anchorCards.types.${o.type}`)),
            chipLabel: outputMentionLabel(o, t(`chat.anchorCards.types.${o.type}`)),
            kind: o.type,
          })),
        ].map((o) => [o.id, o])).values()]
          .filter((o) => currentOutputIds.has(o.id) && ["clip", "film", "video"].includes(o.kind)),
      }
    },
    [assets, outputs, globalReferences, t],
  )

  // Terminal (ADR-051 — the dock is the sole shell): failure stays put —
  // the failed step rows carry the humanized error in-flow (provider 错误
  // 人话化梯), no toast on top; success hands off to the page (refetch →
  // the landed products show on the canvas) and the run's completion recalls
  // a tucked-away panel (the lastAgentKey mechanism below).
  useEffect(() => {
    if (!terminal) return
    // 收紧判定 (2026-09-13, ADR-074②): a PARTIAL failure is FAILED now but
    // still hands off — its landed products must reach the canvas. Only a
    // run that landed NOTHING (no done step with output_refs — prep steps
    // don't count) skips the refetch: nothing new to show, the failed rows
    // carry the error in-flow.
    if (
      status === "failed" &&
      !steps.some((s) => s.status === "done" && (s.output_refs?.length ?? 0) > 0)
    ) {
      return
    }
    void projectChangedRef.current()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [terminal])

  /** Shared landing for every path that starts a run (the dock's Start
   * button, a prose confirmation via /chat): the dock clears and the step
   * flow takes over. The page is told at the same beat — its refetch flips
   * runActive, attaches the page SSE, and the run 期活画布 renders from the
   * first beat. NO QA archive on any start path (2026-09-05 用户拍板): the
   * AnsweredQuestion block is the option-choice UI — a task_book start is a
   * gesture, not a Q&A; its record = echo 散文 + (chat 文本时) 用户原话 +
   * run 收据行. */
  const landOnStartedRun = useCallback((startedRunId: string) => {
    // A started run retires the old presentation receipt locally. Invalidate
    // any in-flight read so it cannot re-authorize a historical card later.
    presentationRecoveryGenRef.current += 1
    setPresentationRecovery(null)
    setPendingQuestion(null)
    const sameRun = runIdRef.current === startedRunId
    const newAttachment = !sameRun || terminalRef.current
    if (newAttachment) {
      const { attempt, uploadRetryCount: retryCount } = nextRunAttachment(
        runAttemptRef.current,
        sameRun,
      )
      // The server may already have pushed upload_retry_count=N before this
      // Chat envelope lands. The attachment epoch is the client's recovery
      // ordinal; incrementing that already-advanced server count again would
      // wait for upload-retry-(N+1) and never seal the real retry-N delivery.
      runAttemptRef.current = attempt
      runIdRef.current = startedRunId
      currentRunAttemptRef.current = { runId: startedRunId, attempt }
      currentUploadRetryCountRef.current = retryCount
      terminalRef.current = false
      setRunAttempt(attempt)
      setRunAttemptUploadRetry(retryCount)
    }
    setRunStartedExplicitly(true)
    setRunId(startedRunId)
    void projectChangedRef.current(startedRunId)
  }, [])

  // Worker continuations have no browser request or uploaded asset to keep
  // their message watch alive. Follow the original request through its final row.
  const lastJourneyStart = useRef(-1)
  useEffect(() => {
    if (!historySettled || !journeyOpeningId || chatBusy) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      await pollTriggerMessages({
        openingId: journeyOpeningId,
        signal: controller.signal,
        onJourneyRun: (nextRunId, seq) => {
          if (seq <= lastJourneyStart.current) return
          lastJourneyStart.current = seq
          if (runIdRef.current !== nextRunId) landOnStartedRun(nextRunId)
        },
      })
      if (!controller.signal.aborted) timer = setTimeout(() => { void poll() }, 3000)
    }
    void poll()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [journeyOpeningId, historySettled, chatBusy, pollTriggerMessages, landOnStartedRun])

  const taskLabel = useCallback(
    (task: TaskItem) => {
      const meta = TOOL_META[task.tool]
      let label = meta ? t(meta.labelKey) : task.tool
      const lang = meta?.langParam ? task.params[meta.langParam] : undefined
      if (typeof lang === "string" && lang) {
        label += ` (${t(`languages.${lang}`, { defaultValue: lang })})`
      }
      if (typeof task.params.count === "number") label += ` ×${task.params.count}`
      return label
    },
    [t]
  )

  const summarizePlan = useCallback(
    (plan: InferredIntent) => plan.tasks.map(taskLabel).join(", "),
    [taskLabel]
  )

  /** Display-copy law (ADR-058): the proposer's fresh LLM name leads; the
   * chain-derived label is the fallback for unnamed (legacy) intents. */
  const titleOf = useCallback(
    (plan: InferredIntent) => plan.name || summarizePlan(plan),
    [summarizePlan],
  )

  const planSummary = useMemo(() => titleOf(intent), [intent, titleOf])

  /** The receipt/recap title (ADR-058): stamped from the BIRTHING proposal
   * at run birth — the run's own truth, immune to later intent drift (a
   * chat-dispatch turn never touches the dock's plan state; the next
   * refinement plan must not retitle an archived receipt). Null = fall back
   * to the live plan's title (plan-confirm starts are fresh by construction). */
  const [runTitleOverride, setRunTitleOverride] = useState<string | null>(null)
  const runTitle = runTitleOverride ?? planSummary

  /** Land the user-level shortfall as the in-flow grey row (BILLING §7 — the
   * 422's typed form, never a toast): the meta:"error" seat turn.failed
   * already uses. The question stays docked (the server settled nothing and
   * committed nothing), so Start can be retried once the balance recovers. */
  const pushCreditsGreyRow = useCallback(
    (d: CreditsInsufficientDetail, turnId?: string | null) => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: t("credits.insufficient", {
            balance: d.balance,
            required: d.required,
          }),
          turnId: turnId === undefined ? adoptCurrentTurnId() : turnId ?? undefined,
          meta: "error",
          creditTopup: { balance: d.balance, required: d.required },
          at: new Date().toISOString(),
        },
      ])
      openCreditTopup({ balance: d.balance, required: d.required })

    },
    [t, openCreditTopup],
  )

  // 确认 = 纯口头 (ADR-111 §2 — dock 确认卡面整族退役): the Start button,
  // the estimate pill and the panel/mobile plan card are gone — the plan's
  // review face is the CANVAS (draft nodes born at dock carry the chain and
  // their per-node quotes) and the confirm gesture is the user's own words
  // (口头确认律 ADR-092: a natural yes rides sendChat to the router's
  // start_run — the same machine the retired pill used). No Cancel either
  // (non-blocking law unchanged): "don't start" is said by not starting —
  // keep chatting, walk away, or delete the project.

  /** Restore a superseded version as the current plan — the chip's snapshot
   * becomes the panel's plan (it rides the next refine as prior_intent, and
   * Start uses it directly). Nothing is locked; older versions stay in the
   * flow as chips. */
  const restoreVersion = (index: number) => {
    const version = planVersions[index]
    if (!version) return
    setIntent(version.plan)
    setExpandedVersion(null)
    toast.success(
      t("generationOverlay.versionRestored", { n: index + 1 })
    )
  }

  const pushMessage = (message: Omit<OverlayMessage, "id">) => {
    // Live pushes anchor at "now"; the QA archive anchors at the question's
    // own created_at when the server row carries one (chronology, #5).
    setMessages((prev) => [
      ...prev,
      { ...message, turnId: message.turnId ?? adoptCurrentTurnId(), at: message.at ?? new Date().toISOString(), id: crypto.randomUUID() },
    ])
  }

  /** The chat input's attach button: picked files stage as chips INSIDE the
   * input group (each uploads immediately, direct-to-storage — the same
   * 3-step flow as the composer) and are only consumed by the send button.
   * Nothing lands in the flow on pick — the chips are the lifecycle. */
  const uploadStaged = async (localId: string, material: File) => {
    try {
      const urlRes = await apiFetch(
        `/api/v1/projects/${projectId}/assets/upload-url`,
        {
          method: "POST",
          body: {
            filename: material.name,
            content_type: material.type || undefined,
          },
          toast: false,
        }
      )
      if (!urlRes.ok) throw new Error("Failed to get upload URL")
      const { key, upload_url } = (await urlRes.json()) as {
        key: string
        upload_url: string
      }
      // The progress-reporting PUT (the shared XHR seat — composer/recipe
      // parity, the chip reads the ratio) and the pixel probe ride the same
      // beat — the asset row is born with its real dims so the canvas frame
      // law shapes its node from birth (产物卡跟源比例, 2026-09-13).
      const [, dims] = await Promise.all([
        putWithProgress(upload_url, material, (ratio) =>
          setStaged((prev) =>
            prev.map((s) => (s.localId === localId ? { ...s, progress: ratio } : s)),
          ),
        ),
        probeMediaDims(material),
      ])
      const assetRes = await apiFetch(`/api/v1/projects/${projectId}/assets`, {
        method: "POST",
        body: {
          type: inferAssetType(material),
          key,
          title: material.name,
          ...(dims ?? {}),
        },
        toast: false,
      })
      if (!assetRes.ok) throw new Error("Failed to create asset")
      const asset = (await assetRes.json()) as ProjectAsset
      setStaged((prev) =>
        prev.map((s) =>
          s.localId === localId ? { ...s, status: "done", progress: 1, asset } : s
        )
      )
    } catch (err) {
      // Diagnosability (2026-09-27 代理吞响应取证): same law as the
      // composer's staging hook — the failure reason survives in the console.
      console.error("[staged-upload] failed:", err)
      setStaged((prev) =>
        prev.map((s) => (s.localId === localId ? { ...s, status: "error" } : s))
      )
    }
  }

  const handleFilesPicked = (picked: FileList | File[] | null) => {
    const files = Array.from(picked ?? [])
    if (fileInputRef.current) fileInputRef.current.value = ""
    if (files.length === 0) return
    const additions: StagedUpload[] = files.map((file) => ({
      localId: crypto.randomUUID(),
      file,
      status: "uploading",
      progress: 0,
    }))
    setStaged((prev) => [...prev, ...additions])
    for (const s of additions) void uploadStaged(s.localId, s.file)
  }

  // Drag-drop upload (2026-09-24, user ruling — composer parity): the input
  // container is the drop target in every form (full / panel);
  // dropping is a second entry into handleFilesPicked — the staged-chips
  // lifecycle rides unchanged. The gesture machinery (depth counting,
  // files-only arming, the browser-default guard) is the shared
  // useFileDrop. Types are gated by ASSETS_ACCEPT (a dragged File's MIME
  // is not trustworthy); the drop stays live while a turn runs — chips
  // stage for the NEXT message.
  const { dragging: fileDragging, dropProps: fileDropProps } = useFileDrop(
    (files) => {
      const accepted = files.filter(acceptsStagedFile)
      if (accepted.length === 0) {
        if (files.length > 0) toast.error(t("composer.dropInvalid"))
        return
      }
      handleFilesPicked(accepted)
    },
  )

  /** A staged chip's × : drop it from the input group; an already-created
   * asset is deleted server-side too (staged ≠ sent — it must not linger as
   * project material). */
  const removeStaged = (item: StagedUpload) => {
    setStaged((prev) => prev.filter((s) => s.localId !== item.localId))
    if (item.asset) {
      const assetId = item.asset.id
      // A fetch can already know the row (mount / post-turn / tick) — drop
      // it from `assets` too, or it lingers there until the next refetch.
      setAssets((prev) => prev.filter((a) => a.id !== assetId))
      void apiFetch(`/api/v1/projects/${projectId}/assets/${assetId}`, {
        method: "DELETE",
        toast: false,
      }).catch(() => {})
    }
  }

  const retryStaged = (item: StagedUpload) => {
    setStaged((prev) =>
      prev.map((s) =>
        s.localId === item.localId
          ? { ...s, status: "uploading", progress: 0 }
          : s
      )
    )
    void uploadStaged(item.localId, item.file)
  }

  /** An answered question collapses into the flow (ask_user machinery: the flow keeps
   * settled decisions, the dock holds the open one).
   * Reason keys (payload data) render localized as the block's detail line.
   * 形态律 (ADR-053 R1): the AnsweredQuestion block exists only for
   * options questions — an options-empty plain question's answered form is
   * the plain message pair (its question line already sits in the flow as
   * a plain assistant message).
   * QA 只归真问答（2026-09-05 用户拍板）：task_book 的 start 确认永不入
   * QA 块——QA 是「用户做 option 选择」的 UI，start（无论 chat 文本还是
   * pill 手势）不是问答；薄书的记录 = echo 散文 + 用户原话 + run 收据行。
   * Builder form (2026-09-06): the streamAnswer settle SPLICES the row at
   * the optimistic block's own index (the preview right after it must not
   * remount); pushAnsweredQuestion keeps the append-at-end ordering for
   * paths without a live preview. */
  /** QA 块一个 builder（2026-09-08 收口）: the optimistic block at option
   * click and the server archive row at the envelope build the SAME qa
   * payload through this one funnel — the Q line reads bareQuestion() in
   * both, so the envelope swap can never flip the block's wording (the
   * 2026-09-08 QA-flip bug class was a second hand-written construction
   * reading question.content). */
  const buildQaBlock = (
    message: QuestionMessage,
    answer: string,
    muted: boolean,
    group?: ReturnType<typeof groupAnswerDisplay>,
  ): NonNullable<OverlayMessage["qa"]> => ({
    question: bareQuestion(message),
    answer,
    muted,
    questionId: message.id,
    answerKind: message.answer?.kind ?? (group ? "group" : undefined),
    ...group,
  })

  const buildAnsweredQuestionRow = (
    message: QuestionMessage,
  ): Omit<OverlayMessage, "id"> | null => {
    if (!message.answer) return null
    const isPlan = message.question?.kind === "task_book"
    // task-book start confirmations never archive as QA (ruling above).
    if (isPlan) return null
    if (
      message.question?.kind === "question" &&
      (message.question?.options?.length ?? 0) === 0 &&
      (message.question?.items?.length ?? 0) === 0
    ) {
      return null
    }
    const display = answeredQuestionText(message.answer, t, !!message.workflow_run_id)
    return {
      role: "assistant",
      content: "",
      seq: message.seq ?? undefined,
      at: message.created_at,
      turnId: message.turn_id ?? undefined,
      independentKind: "qa",
      qa: buildQaBlock(
        message,
        display.text,
        display.muted,
        message.answer.answers?.length
          ? groupAnswerDisplay(message, message.answer.answers)
          : undefined,
      ),
    }
  }
  const pushAnsweredQuestion = (message: QuestionMessage) => {
    const row = buildAnsweredQuestionRow(message)
    if (row) pushMessage(row)
  }

  /** The chat loop's reply: a pending OPTIONS question docks (never enters
   * the flow, prohibited-behavior #2); a pending TEXT question (no options)
   * IS a plain conversation message (形态律 ADR-053 R1 — it stays in the
   * flow; the pending row lives server-side and later turns bring the
   * judged settlement / the reminder tail); anything else renders as prose
   * + an optional RunCard. A docked task plan also refetches the panel's
   * plan. Starting is ALWAYS the user's explicit Start press — no
   * auto-start.
   *
   * echo 实体化 (2026-09-04, chat-flow-sequencing A2): docking a task plan
   * first pushes the row's echo prose as a real flow message (its content
   * IS the echo since A1) — unless this turn's streamed bubble already
   * carries it (`echoCarried`, the sendChat streaming path) — so the
   * confirm beat reads chronologically in the flow and survives history
   * replay. The plan card's own echo line dedupes against the pushed
   * message by content. */
  const handleAssistantMessage = async (
    wire: QuestionMessage,
    opts?: { echoCarried?: boolean }
  ) => {
    const message = journeyTranscriptRow(wire)
    observeJourney([message])
    if (preparationTool(message)) {
      await pacePersistedMessage(message)
      return
    }
    if (message.question && !message.answer) {
      if (
        message.question.kind === "task_book" &&
        runIdRef.current &&
        !terminalRef.current
      ) {
        // A run is already LIVE (started from another surface while this
        // turn was in flight) — a late task plan must not pull the UI back
        // to confirm; the run flow owns the surface now. (A TERMINAL run
        // does not trigger this guard: the dock's refinement plans dock
        // normally — runId set ≠ run live.)
        return
      }
      if (
        message.question.kind === "question" &&
        (message.question.options?.length ?? 0) === 0 &&
        (message.question.items?.length ?? 0) === 0
      ) {
        // 形态律 (ADR-053 R1): a text question never docks — render it as a
        // plain assistant message and leave the input live. echoCarried:
        // the turn's finalized preview bubble already IS that message.
        if (!opts?.echoCarried) {
          pushMessage({
            role: "assistant",
            outputRefs: triggerOutputRefs(message.intent),
            proseDrainedAtMs: Date.now(),
            content: message.content ?? "",
            turnId: message.turn_id ?? undefined,
            runId: message.workflow_run_id,
            seq: message.seq ?? undefined,
            blocks: message.blocks?.length ? message.blocks : undefined,
          })
        }
        return
      }
      if (!opts?.echoCarried) {
        // The framing prose (ask 三分解剖 ① — a task plan's echo, or an
        // options question's framing speech) lands ABOVE the docked pill,
        // anchored at the question row's own birth time (#5 chronology).
        // Rows whose content IS the bare question (code-composed, legacy)
        // carry no echo — the pill's title already says it.
        const echo = questionEcho(message)
        if (echo || triggerOutputRefs(message.intent).length > 0) {
          pushMessage({
            role: "assistant",
            outputRefs: triggerOutputRefs(message.intent),
            proseDrainedAtMs: Date.now(),
            content: echo ?? "",
            turnId: message.turn_id ?? undefined,
            seq: message.seq ?? undefined,
            at: message.created_at,
          })
        }
      }
      setPendingQuestion(message)
      if (message.question.kind === "task_book") {
        // A plan docked — the server stamped the draft graph in the same
        // transaction: tell the page so its flip gate sees it (K5 图先展示
        // 后运行 — the world morphs on the draft graph, not just on runs).
        void projectChangedRef.current()
        // 计划行自完备 (2026-09-08, 方案 B): the docked row IS the whole
        // plan — the chain on the row's `intent` column. The live path
        // renders it straight off the envelope (one turn = one call);
        // the pending-brief fetch is the RECOVERY seat only, kept as the
        // fallback for rows docked before the seal (intent column null).
        // Phase 3 Batch B (裁决 1): docking NO LONGER raises a "confirm"
        // phase — the confirm beat derives from the stamp's PLAN_READY
        // (confirmActive), so a dock envelope alone never opens the beat
        // (task_book exists ≠ PLAN_READY). The intent state still lands
        // here; the stamp's refetch (project refresh above) flips the
        // surface.
        if (message.intent) {
          setIntent(normalizeIntent(message.intent))
          setIntentReady(true)
          void refreshPresentationRecovery()
        } else {
          const pending = await refreshPresentationRecovery()
          if (pending) {
            setIntent(normalizeIntent(pending.intent))
            setIntentReady(true)
            // No "plan updated" filler line on refinements — the turn's own
            // streamed echo bubble already says what changed.
          }
        }
      }
      return
    }
    // A plain prose reply. echoCarried: the turn's finalized preview bubble
    // already carries this prose (its runId was stamped at finalize time).
    if (!opts?.echoCarried) {
      pushMessage({
        role: "assistant",
        serverMessageId: message.id,
        seq: message.seq ?? undefined,
        turnId: message.turn_id ?? undefined,
        outputRefs: triggerOutputRefs(message.intent),
        proseDrainedAtMs: Date.now(),
        content: message.content ?? "",
        runId: message.workflow_run_id,
        blocks: message.blocks?.length ? message.blocks : undefined,
      })
    }
  }

  /** One endpoint for every turn (intent-surface-unification W2): the server
   * routes plan-path turns (task-book build / refine / confirm) and
   * chat-loop turns itself. The panel's current chain rides confirm-beat
   * turns as prior_intent (the intent router re-emits the full revised chain —
   * chat revisions always win); mentions / the persona choice ride only the
   * composer's first message.
   *
   * Transport is SSE (streamChat): prose deltas feed a typewriter-paced
   * preview bubble (reasoning models emit a short echo in one burst — pacing
   * keeps the "written live" feel); the terminal turn.completed envelope is
   * authoritative and FINALIZES THE PREVIEW IN PLACE — same React key, no
   * remount — so a docking task plan never makes the text flicker. */
  const sendChat = async (
    text: string,
    opts?: {
      firstMessage?: boolean
      mentions?: ChatMention[]
      skill?: SkillOption | null
      personaId?: string
      /** Files staged in the input group, sent with this turn — persisted on
       * the user message row so a refresh re-renders the chips. */
      attachments?: ChatAttachment[]
      /** Failure handling for a user-typed turn: roll the optimistic bubble
       * back out of the flow and restore the draft — ONLY when the message
       * never persisted (entry-cap rejections / pre-stream failures). A
       * persisted turn (交互完整性批 A) keeps the bubble; the grey error
       * row is its marker. */
      rollbackId?: string
      draft?: string
      /** The turn's mention chips return with the draft on failure. */
      rollbackMentions?: ChatMention[]
      /** Consumed attachment chips return to the input group on failure. */
      rollbackStaged?: StagedUpload[]
    }
  ) => {
    const ctrl = new AbortController()
    let resolveTurnId!: (turnId: string | null) => void
    const turnIdPromise = new Promise<string | null>((resolve) => {
      resolveTurnId = resolve
    })
    const stopContext: ActiveChatStop = {
      controller: ctrl,
      turnIdPromise,
      resolveTurnId,
      draft: opts?.draft ?? text,
      mentions: opts?.rollbackMentions ?? opts?.mentions ?? [],
      skill: opts?.skill ?? null,
      staged: opts?.rollbackStaged ?? restoredStagedUploads(opts?.attachments ?? []),
      stopOutcome: null,
      frontier: null,
      stopRequested: false,
      stopPromise: null,
    }
    activeChatStopRef.current = stopContext
    abortRef.current = ctrl
    setChatBusy(true)
    // Dead-stream machinery (module constants): a new turn owns the
    // reconcile generation (kills any running one), stamps the liveness
    // clock, and arms the watchdog — the server guarantees a frame ≤15s, so
    // 45s of silence declares the pipe dead and abandons the zombie stream.
    const reconcileGen = ++reconcileGenRef.current
    deadStreamRef.current = false
    terminalReceivedRef.current = false
    const turnStartMs = Date.now()
    turnStartMsRef.current = turnStartMs
    lastFrameAtRef.current = turnStartMs
    const poke = () => {
      lastFrameAtRef.current = Date.now()
    }
    sseProbe("turn.start", {})
    const watchdog = setInterval(() => {
      // Retired post-terminal (terminalReceivedRef): after turn.completed no
      // frame will ever arrive, so silence past the envelope is the drain's
      // own pacing (a hidden tab's throttled timers stretch it to minutes) —
      // never a dead pipe.
      if (terminalReceivedRef.current) return
      if (Date.now() - lastFrameAtRef.current > STREAM_SILENCE_DEAD_MS) {
        sseProbe("watchdog.dead", {
          silenceMs: Date.now() - lastFrameAtRef.current,
        })
        // One-shot: death is declared once (deadStreamRef sticks, the abort
        // is issued) — re-firing only re-aborts a corpse, and if the turn's
        // promise never settles the interval would leak-fire forever.
        clearInterval(watchdog)
        deadStreamRef.current = true
        ctrl.abort()
      }
    }, STREAM_WATCHDOG_TICK_MS)
    setProseActive(false)
    setThinkingPhase(null)
    resetInterimActivityGates()
    setActivities(resetActivities()) // the new turn's own now-line stream starts empty
    currentActivityRowKeysRef.current = new Set()
    const workRowKeys = currentActivityRowKeysRef.current
    let terminalAtMs: number | null = null
    let speechStarted = false
    // C8-c: a new turn owns the candidate-rollback scope — rows committed
    // by earlier turns are no longer this turn's to roll back.
    liveCandidateRowsRef.current.clear()
    pendingCandidateRowsRef.current = []
    candidateTurnSnapshotRef.current = new Map(messagesRef.current.flatMap((message) =>
      message.candidates
        ? [[message.candidates.candidateSetId, [...message.candidates.selected]] as [string, number[]]]
        : [],
    ))
    const streamId = crypto.randomUUID()
    const localTurnId = opts?.rollbackId ?? streamId
    const turnOwner = { localId: localTurnId, serverId: null, adoptLocal: true }
    currentTurnRef.current = turnOwner
    const ownsTurn = () => isTurnOwner(currentTurnRef.current, turnOwner)
    const adoptTurnId = (serverId?: string | null) =>
      ownsTurn() ? adoptCurrentTurnId(serverId) : undefined
    const reconcileTurnRows = (rows: OverlayMessage[]) =>
      ownsTurn() ? reconcileCurrentTurnRows(rows) : rows
    const ownFrame = <Args extends unknown[]>(handler: (...args: Args) => void) =>
      (...args: Args) => {
        if (!ownsTurn()) return
        poke()
        handler(...args)
      }
    setMessages((prev) =>
      prev.map((message) =>
        message.id === localTurnId ? { ...message, turnId: localTurnId } : message
      )
    )
    // InterimProse segments (ADR-085 判词 5 — 一键一段): the ONE machine lives
    // in timeline/speech.ts (P1 — segment ownership pins at the input
    // event boundary; the typewriter's display progress never decides
    // which segment a fragment belongs to). The answer stream's
    // settleAnswerTurn rides the same module — one semantics, one seat.
    const segments = createSpeechSegments({
      baseId: streamId,
      apply: (update) => setMessages((prev) => (ownsTurn() ? update(prev) : prev)),
      setProseActive: (active) => {
        if (ownsTurn()) setProseActive(active)
      },
      onVisible: (rowId, atMs) => {
        if (ownsTurn()) noteSpeechVisible(rowId, atMs, workRowKeys)
      },
      onInterimStart: (rowId) => {
        if (ownsTurn()) beginInterimActivityGate(rowId)
      },
      onInterimSettled: (rowId) => {
        if (ownsTurn()) settleInterimActivityGate(rowId)
      },
      turnId: () => adoptTurnId(),
    })
    /** In-place finalize: the preview bubble becomes the settled message
     * under the SAME key (the envelope's content wins); never a remount.
     * 数组位置律 (ADR-108): the row's POSITION is its array index — the
     * envelope's created_at is never re-anchored (ordering never reads at). */
    const finalizePreview = (
      content?: string,
      runId?: string | null,
      seq?: number | null,
      serverMessageId?: string,
    ) => {
      if (!ownsTurn()) return
      // Ownership is a scheduling guard: React may execute this updater after
      // the turn's finally releases currentTurnRef. The id-scoped settlement
      // remains valid then; re-checking ownership here would discard it.
      const pendingCandidates = pendingCandidateRowsRef.current
      pendingCandidateRowsRef.current = []
      setMessages((prev) => {
        const aliased = serverMessageId
          ? stampServerMessageId(prev, streamId, serverMessageId)
          : prev
        return releaseSettledCandidateRows(aliased.map((m) =>
          m.id === streamId
            ? {
                ...m,
                content: content ?? m.content,
                runId: runId === undefined ? m.runId : runId,
                turnId: turnOwner.serverId ?? turnOwner.localId ?? m.turnId,
                seq: seq == null ? m.seq : seq,
                streaming: false,
                proseDrainedAtMs: m.proseDrainedAtMs ?? Date.now(),
              }
            : m
        ), pendingCandidates, streamId)
      })
    }
    /** 打字机律最后闸门 (2026-09-08 用户拍板): a turn that streamed NO deltas
     * (the funnel's schema-repair round never streams; any non-streaming
     * fallback) must still never pop its prose in as one blob — the settled
     * content rides the typewriter under the SAME stream key, and any dock
     * waits for the release to drain, so the prose visibly LEADS and the
     * question follows, exactly like a streamed turn. */
    const paceSettledProse = async (
      content: string,
      runId?: string | null,
      seq?: number | null,
      serverMessageId?: string,
    ) => {
      if (!ownsTurn()) return
      // The machine pins the main row at push (出生钉位) and paces the
      // content in — same key, no blob, no erase.
      segments.push(content)
      if (serverMessageId) {
        setMessages((prev) => stampServerMessageId(prev, streamId, serverMessageId))
      }
      await segments.drain()
      finalizePreview(content, runId, seq, serverMessageId)
    }
    /** 打字机律·工具线重述牙③ (T2b 感知族): the loop's accumulated speech may
     * EXTEND the streamed preview — words spoken before a kept read call are
     * the envelope's prefix, the quiet terminal speech its tail. When the
     * settled content continues what's on screen, only the unseen tail rides
     * the typewriter (same key, no blob, no erase). A non-prefix settled text
     * is replaced speech (a rejected call's flip) and settles as before. Call
     * AFTER the typewriter drains so previewText is the full streamed prefix. */
    const paceUnstreamedTail = async (content: string): Promise<void> => {
      if (!ownsTurn()) return
      if (
        segments.streamedAny &&
        segments.previewText &&
        content.length > segments.previewText.length &&
        content.startsWith(segments.previewText)
      ) {
        segments.push(content.slice(segments.previewText.length))
        await segments.drain()
      }
    }
    /** The presenting row's blocks and message-owned upload results: the
     * completed envelope's assistant_message carries the server-stamped
     * references; the VISIBLE row is the finalized preview bubble (same
     * key, streamId) — a pushed echo row instead carries them via
     * handleAssistantMessage's own threading. Stamps only after the prose
     * landed (散文永远在先 — the card follows the speech). */
    const stampEnvelopeBlocks = (message: QuestionMessage) => {
      if (!ownsTurn()) return
      setMessages((prev) => stampMessagePresentation(prev, streamId, message))
    }
    try {
      const data = await streamChat<{
        user_message: QuestionMessage
        assistant_message: QuestionMessage | null
        run_id: string | null
        answered_question?: QuestionMessage | null
      }>(
        {
          project_id: projectId,
          message: text,
          first_message: opts?.firstMessage,
          mentions: opts?.mentions ?? [],
          skill: opts?.skill?.reference,
          attachments: opts?.attachments ?? [],
          persona_id: opts?.personaId,
          // The sender's surface (2026-09-25 canvas↔chat 联动): panel form
          // = the plan's canvas lives beside this conversation — the reply
          // may name it; every other form stays surface-neutral.
          surface: "chat",
          // 环境能力位 (ADR-118 §6): the raw can-host-canvas read rides
          // every send — pre-reveal desktop is surface="chat" yet CAN host
          // the canvas; the server's canvas_visible = this ∧ world-liveness.
          canvas_available: false,
          prior_intent:
            // The panel's current chain rides while the confirm beat is
            // live (裁决 1 derived predicate — never a phase read).
            confirmActive
              ? intent
              : undefined,
        },
        {
          signal: ctrl.signal,
          onTurnStarted: ownFrame((turnId) => {
            adoptTurnId(turnId)
            stopContext.resolveTurnId(turnId)
            setMessages((prev) => reconcileTurnRows(stampServerMessageId(prev, localTurnId, turnId)))
          }),
          onDelta: ownFrame((delta, messageId) => {
            if (delta) speechStarted = true
            // 出生钉位 + 归属钉位 (P1): the machine pins the row at the
            // delta's RECEIPT and the segment at the same boundary — never
            // at the typewriter's released fragment (a hidden tab throttles
            // its timer while a read's activity row-append lands
            // synchronously and would claim the position first).
            segments.onDelta(delta, messageId)
          }),
          onThinking: ownFrame((payload) => {
            // System Status labels and the explicit clear (I-PFA-06 清除
            // 协议, 2026-09-18; Phase 3 Batch B): `"phase" in payload`
            // separates both from bare keepalives, which leave the label
            // as-is. A string phase hands the row over (the film design
            // span's labels are the sole survivors); `phase: null`
            // is the server's clear frame (every call's name-known
            // moment) — reset to the base label. Work evidence never rides
            // this channel (Activity owns it); a phase-only frame drops
            // the row back.
            if ("phase" in payload) {
              setThinkingPhase(payload.phase ?? null)
            }
          }),
          onInterimProse: ownFrame((text, at, turnId, messageId, seq) => {
            if (text.trim()) speechStarted = true
            segments.onInterimProse(text, at, turnId, messageId, seq)
          }),
          onActivity: ownFrame((frame) => {
            handleActivityFrame(frame)
          }),
          onCandidates: ownFrame((event) => {
            handleCandidatesFrame(event)
          }),
          onRowAppend: ownFrame((row) => {
            handleRowAppend(row)
          }),
          onRowUpdate: ownFrame((id, frame) => {
            handleRowUpdate(id, frame)
          }),
        }
      )
      if (!ownsTurn()) return
      // Slow initial history may already contain this Turn. Register real ids
      // before any pacing await so archive merge keeps the optimistic rows.
      setMessages((prev) => {
        let next = stampServerMessageId(prev, localTurnId, data.user_message.id)
        if (data.assistant_message) {
          next = stampServerMessageId(next, streamId, data.assistant_message.id)
        }
        return next
      })
      sseProbe("turn.envelope", { dead: deadStreamRef.current })
      terminalAtMs = Date.now()
      // 终帧缴械: the pipe is DONE — no frame ever follows turn.completed,
      // so the dead-stream machinery's domain ends here. Post-envelope the
      // only work left is the typewriter pacing data already in hand, and a
      // hidden tab's throttled timers must never again read as pipe death.
      terminalReceivedRef.current = true
      clearInterval(watchdog)
      // Dead-stream bail (watchdog / visibility fired): the reconcile owns
      // the turn now — the envelope's whole completion path is superseded,
      // never double-rendered.
      if (deadStreamRef.current) {
        sseProbe("turn.bail.pre-drain")
        return
      }
      // Envelope wins: any in-flight interim_prose delivery finishes FIRST
      // (its final writes ride the same release queue), then the buffered
      // prose PACES OUT before the turn lands.
      // 打字机律·G2 修律 (2026-10-04): the speech-commit protocol holds the
      // whole reply's deltas until adjudication, so they burst into this
      // queue right before the envelope — a flush() here would dump them
      // whole (整段瞬移, the exact shape the law bans). drain() paces the
      // burst at the typewriter's cadence (catch-up included) — prose
      // visibly LEADS, docks/receipts follow. flush() stays on the
      // failure/abort paths (rollback must not linger).
      await segments.drain()
      if (!ownsTurn()) return
      // Second dead-stream bail: a continuation that hung INSIDE the drains
      // (a frozen page's timers) resumes here — if the reconcile already
      // owned the turn meanwhile, everything below is superseded.
      if (deadStreamRef.current) {
        sseProbe("turn.bail.post-drain")
        return
      }
      // 收编即登记: the envelope owns these rows from here — but the live
      // bubble keeps its LOCAL streamId forever, so reconcile's id-dedup is
      // blind to what we are rendering unless the real row ids are
      // registered at the ownership handoff (symmetric to reconcile's own
      // registration). Any reconcile that still fires later skips them.
      noteObservedSeq(data.user_message.seq)
      noteObservedSeq(data.assistant_message?.seq)
      noteObservedSeq(data.answered_question?.seq)
      adoptTurnId(data.user_message.turn_id ?? data.user_message.id)
      setMessages((prev) => (ownsTurn() ? reconcileTurnRows(prev) : prev))
      const answeredQuestionId = answeredQuestionIdFromIntent(data.user_message.intent)
      setMessages((prev) =>
        prev.map((m) =>
          m.id === localTurnId
            ? {
                ...m,
                seq: data.user_message.seq ?? m.seq,
                at: data.user_message.created_at ?? m.at,
                skill: data.user_message.skill ?? m.skill,
                answeredQuestionId: answeredQuestionId ?? m.answeredQuestionId,
              }
            : m,
        ),
      )
      if (data.assistant_message != null) {
        observeJourney([data.assistant_message])
        reconciledIdsRef.current.add(data.assistant_message.id)
      }
      if (data.answered_question != null) {
        reconciledIdsRef.current.add(data.answered_question.id)
      }
      // 终帧律 (I-PFA-06 相位清除协议, 2026-09-18): the envelope closes every
      // phase — the landing awaits below (prose pacing drains, then the
      // docks/receipts land) run with chatBusy still true, so a stale label
      // would resurface in that tail window without this reset. (The answer
      // stream already cleared at the same seat; this is the parity gap.)
      setThinkingPhase(null)
      // Defensive sweep (T16-B): the server's terminal sweep already closed
      // every activity; this catches whatever the stream dropped — the
      // envelope leaves nothing spinning.
      settleActivities("completed")
      // A turn can create assets server-side (declared-material promotion —
      // reachable in ANY project, not just an empty one) — always refresh
      // the prompt attachments after a turn.
      void fetchAssets()
      if (data.run_id && data.assistant_message != null) {
        if (preparationTool(data.assistant_message)) {
          setMessages((prev) => prev.filter((m) => m.id !== streamId))
          await pacePersistedMessage(data.assistant_message)
          if (ownsTurn()) landOnStartedRun(data.run_id)
          return
        }
        // G-1: the prose confirmation answered the docked task plan
        // server-side (kind=start) and the run is live. NO QA archive on
        // ANY start path (2026-09-05 用户拍板): the AnsweredQuestion block
        // is the option-choice UI — a task_book start (chat text or pill)
        // is a gesture, not a Q&A. The record = echo 散文 + this user
        // message + the run receipt line.
        //
        // The runId stamp is the run↔message association (ADR-058): the
        // birthing echo carries it so the detached-run archive (inline
        // RunCard) and the replay's association stay truthful — the
        // receipt's anchor no longer reads it (2026-09-13 时序拍板: the
        // receipt tombstones at the run's END, which postdates every
        // birthing row by construction).
        if (segments.streamedAny) {
          // A read-tool turn's echo may EXTEND the streamed prefix (the
          // loop's accumulated speech): pace the unseen tail BEFORE the run
          // lands — the same law as the zero-delta start's paceSettledProse.
          await paceUnstreamedTail(data.assistant_message.content ?? "")
          // 信封永远赢 (ADR-093 §1): the content truth replaces the preview
          // too — the start path is no exception (same-value on the happy
          // path, the envelope's prose wins after a rejected iteration).
          finalizePreview(
            data.assistant_message.content ?? undefined,
            data.run_id,
            data.assistant_message.seq,
            data.assistant_message.id,
          )
        } else {
          // Zero-delta start: the settled speech still paces BEFORE the run
          // lands. An answered plan row suppresses that pacing ONLY when its
          // exact echo is already visible — the ordinary start of an earlier
          // dock. A plan born and auto-started in THIS turn has no such echo
          // yet; its first presentation must not be mistaken for a duplicate.
          if (
            shouldPaceStartEnvelopeProse({
              content: data.assistant_message.content ?? "",
              assistantMessageId: data.assistant_message.id,
              answeredQuestionId: data.answered_question?.id,
              messages: messagesRef.current,
            })
          ) {
            await paceSettledProse(
              data.assistant_message.content ?? "",
              data.run_id,
              data.assistant_message.seq,
              data.assistant_message.id,
            )
          } else {
            setMessages((prev) => prev.filter((m) => m.id !== streamId))
          }
        }
        if (!ownsTurn()) return
        // The receipt titles the RUN by its birthing proposal (ADR-058):
        // the answered plan row carries the fresh intent server-side — its
        // LLM name leads, the chain label falls back. The dock's own intent
        // state is NOT touched (a chat-dispatch turn is not a plan edit).
        const birthIntent =
          data.answered_question?.intent ?? data.assistant_message.intent
        if (birthIntent) {
          const birthTitle = titleOf(normalizeIntent(birthIntent))
          if (birthTitle) setRunTitleOverride(birthTitle)
        }
        landOnStartedRun(data.run_id)
        return
      }
      // This very text settled a pending question server-side — the
      // deterministic autoResume option hit, or the judged settlement
      // (插话支持 ADR-053 R2: the slot handshake / pending_disposition) —
      // archive its answered block before the assistant's continuation.
      if (data.answered_question) {
        setPendingQuestion(null)
        pushAnsweredQuestion(data.answered_question)
      }
      if (data.assistant_message == null) {
        // 素材待命承诺·落地压制: the understanding beat landed mid-turn, so
        // the server closed the turn silent (zero assistant row) — the
        // world-fired review turn is the answer and arrives on its own
        // channel. Drop the preview bubble (nothing was ever streamed into
        // it) and wait for the review.
        setMessages((prev) => prev.filter((m) => m.id !== streamId))
        return
      }
      const message = data.assistant_message
      if (message.question && !message.answer && dockWorthyQuestion(message)) {
        // An OPTIONS question / task plan docks (a TEXT question IS the
        // prose reply and lands below like one — 形态律 ADR-053 R1). The
        // streamed echo bubble
        // STAYS in place (same key — never a remount); the superseded plan
        // collapses into a version chip anchored after the echo bubble that
        // produced it — the same anchor the inline card occupied while the
        // turn was in flight — and the fresh card pins bottom-most.
        if (segments.streamedAny) {
          // The echo may extend the streamed prefix (read-tool turn) — pace
          // the tail, then the bubble carries the whole speech into the dock.
          // A non-prefix settled echo is REPLACED speech (a rejected
          // iteration streamed first): the envelope wins here exactly like
          // the prose path below — the rejected iteration's words never
          // survive as the settled bubble (2026-09-17 交互完整性批 ③: the
          // dock branch used to keep the streamed orphan AND suppress the
          // real echo via echoCarried — the live view diverged from the DB).
          await paceUnstreamedTail(message.content ?? "")
          if (!ownsTurn()) return
          finalizePreview(message.content || undefined, undefined, message.seq, message.id)
          stampEnvelopeBlocks(message)
          if (message.question.kind === "task_book") {
            if (intentReady && livePlanMessageId) {
              setPlanVersions((prev) => [
                ...prev,
                { messageId: livePlanMessageId, plan: intentRef.current },
              ])
            }
            setLivePlanMessageId(streamId)
          }
        } else {
          // Zero-delta turn (the funnel's repair round never streams): the
          // echo rides the typewriter anyway — the dock waits for it to
          // drain, so the prose leads and the question follows (打字机律).
          const settledEcho = questionEcho(message)
          if (settledEcho) {
            await paceSettledProse(settledEcho, undefined, message.seq, message.id)
            if (!ownsTurn()) return
            stampEnvelopeBlocks(message)
          } else {
            setMessages((prev) => prev.filter((m) => m.id !== streamId))
          }
        }
        // The streamed (or last-gate-paced) bubble already carries the echo —
        // the dock handler must not duplicate it as a second message.
        // echoCarried ≡ streamedAny (2026-09-09 单派生): every prose path —
        // model deltas AND paceSettledProse — rides the same typewriter
        // funnel whose append flips streamedAny, so at this point the var IS
        // the flag ("the preview bubble carries the echo"). The old
        // `streamedAny || !!questionEcho(message)` recomputed the same fact.
        await handleAssistantMessage(message, {
          echoCarried: segments.streamedAny,
        })
        if (!ownsTurn()) return
      } else if (segments.streamedAny) {
        // Prose reply: the preview bubble IS the settled message (same key;
        // the envelope content + run id are authoritative). A read-tool
        // turn's unstreamed tail paces out first (打字机律·工具线重述).
        await paceUnstreamedTail(message.content ?? "")
        if (!ownsTurn()) return
        finalizePreview(
          message.content ?? "",
          message.workflow_run_id,
          message.seq,
          message.id,
        )
        stampEnvelopeBlocks(message)
      } else {
        // Zero-delta prose reply: same last-gate pacing as the dock branch.
        const settled = (message.content ?? "").trim()
        if (settled) {
          await paceSettledProse(
            message.content ?? "",
            message.workflow_run_id,
            message.seq,
            message.id,
          )
          if (!ownsTurn()) return
          stampEnvelopeBlocks(message)
          await handleAssistantMessage(message, { echoCarried: segments.streamedAny })
        } else {
          setMessages((prev) => prev.filter((m) => m.id !== streamId))
          await handleAssistantMessage(message)
        }
      }
    } catch (e) {
      terminalAtMs ??= Date.now()
      const transportError = e instanceof StreamTransportError
      // Reuse dead-stream recovery only before any speech preview exists.
      // Once prose/interim prose rows are live, their settlement stays unchanged.
      const recoverTransport = transportError && !speechStarted
      const aborted = e instanceof DOMException && e.name === "AbortError"
      sseProbe("turn.error", {
        name: e instanceof Error ? e.name : "?",
        message: e instanceof Error ? e.message : String(e),
        dead: deadStreamRef.current,
        transport: transportError,
        recover: recoverTransport,
      })
      // If the server's quiet close arrives while Stop is still in flight,
      // wait for the control result before choosing drain/failure vs halt.
      // Resolving a missing turn id first avoids waiting on each other forever.
      stopContext.resolveTurnId(null)
      if (stopContext.stopPromise) await stopContext.stopPromise
      // The Stop control response is authoritative even if the server's quiet
      // close wins the race with our AbortError; neither is a grey failure.
      const stopped = stopContext.stopOutcome !== null && stopContext.frontier !== null
      if (stopped) segments.halt()
      else await segments.drain()
      if (!ownsTurn()) return
      rollbackCandidateRows()
      // 终帧律 (同上): a failed/aborted turn closes every phase too.
      setThinkingPhase(null)
      settleActivities(aborted || recoverTransport ? "cancelled" : "failed")
      if (stopped) {
        const outcome = stopContext.stopOutcome!
        const frontier = stopContext.frontier!
        const turnIds = new Set(
          [localTurnId, turnOwner.serverId].filter((id): id is string => Boolean(id)),
        )
        setMessages((prev) => applyStoppedTurnFrontier(prev, turnIds, outcome, frontier))
        for (const [serverMessageId, ownerTurnId] of visibleStructureTurnsRef.current) {
          if (turnIds.has(ownerTurnId)) visibleStructureTurnsRef.current.delete(serverMessageId)
        }
        if (outcome === "retracted") {
          if (!inputMirrorRef.current.trim()) {
            const editor = editorRef.current
            if (stopContext.draft) editor?.insertText(stopContext.draft)
            for (const mention of stopContext.mentions) editor?.insertMention(mention)
          }
          setSelectedSkill((current) => current ?? stopContext.skill)
          if (stopContext.staged.length > 0) {
            const chips = stopContext.staged
            setStaged((prev) => {
              const kept = new Set(prev.map((s) => s.localId))
              return [...prev, ...chips.filter((chip) => !kept.has(chip.localId))]
            })
          }
          onFirstMessageRetracted?.()
        }
        return
      }
      if (aborted || recoverTransport) {
        setMessages((prev) =>
          prev.map((m) =>
            isSpeechSegmentRow(m.id, streamId)
              ? { ...m, streaming: false }
              : m
          )
        )
        if (deadStreamRef.current || recoverTransport) {
          // Read the existing archive recovery; never repeat the user action.
          void reconcileTurn(turnStartMs, reconcileGen)
        }
        return
      }
      // Turn durability (交互完整性批 A): a persisted turn's user message
      // committed server-side BEFORE the failure — the bubble STAYS (a
      // refresh re-renders it from the DB), and the grey row below is its
      // in-flow marker. Only a pre-persistence rejection (entry caps) or a
      // pre-stream failure rolls the optimistic bubble back out and
      // restores the draft (nothing exists server-side to diverge from).
      if (opts?.firstMessage && e instanceof StreamTurnError &&
          (e.detail as { code?: string } | null)?.code === "chat.already_opened") {
        setMessages((rows) => rows.filter((row) => row.id !== opts.rollbackId && row.id !== streamId))
        setHistoryAttempt((attempt) => attempt + 1)
        return
      }
      const persisted = e instanceof StreamTurnError && e.persisted
      const persistedTurnId = persisted && e instanceof StreamTurnError ? e.turnId : null
      if (opts?.rollbackId && persistedTurnId) {
        const rollbackId = opts.rollbackId
        setMessages((prev) =>
          reconcilePersistedFailure(prev, rollbackId, persistedTurnId)
        )
      }
      // Interim prose rows and the emitted trailing partial are durable. Keep their
      // live rows static after the typewriter drains instead of deleting the
      // only visible speech when the main Turn transaction rolls back.
      setMessages((prev) =>
        prev.map((m) =>
          isSpeechSegmentRow(m.id, streamId) ? { ...m, streaming: false } : m
        )
      )
      if (opts?.rollbackId && !persisted) {
        const rollbackId = opts.rollbackId
        setMessages((prev) => prev.filter((m) => m.id !== rollbackId))
        // The editor is DOM-owned: restore imperatively, and only when the
        // user hasn't typed something new meanwhile (chips re-land at the
        // end — positions aren't kept).
        if (!inputMirrorRef.current.trim()) {
          const editor = editorRef.current
          if (opts.draft) editor?.insertText(opts.draft)
          for (const m of opts.rollbackMentions ?? []) editor?.insertMention(m)
        }
        setSelectedSkill((current) => current ?? opts.skill ?? null)
      }
      if (opts?.rollbackStaged?.length && !persisted) {
        const chips = opts.rollbackStaged
        setStaged((prev) => {
          const kept = new Set(prev.map((s) => s.localId))
          return [...prev, ...chips.filter((c) => !kept.has(c.localId))]
        })
      }
      // The failure itself lands in the flow as a gray system row (never a
      // toast — turn.failed is a fact of the conversation). The row is
      // local-only; on a persisted turn the user bubble it answers IS
      // durable, so a refresh keeps the question and drops only this row —
      // the honest shape of "asked, not answered".
      // A structured credits shortfall (the judged-start 422 riding the
      // turn.failed frame) takes the shared grey-row seat — 双路同语义
      // with the typed Start.
      const credits =
        e instanceof StreamTurnError ? asCreditsInsufficient(e.detail) : null
      if (credits) {
        pushCreditsGreyRow(
          credits,
          e instanceof StreamTurnError ? e.turnId : undefined,
        )
      } else {
        const detail = e instanceof Error ? e.message : t("chat.failed")
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: detail,
            turnId:
              e instanceof StreamTurnError
                ? e.turnId ?? undefined
                : adoptCurrentTurnId(),
            meta: "error",
            at: new Date().toISOString(),
          },
        ])
      }
    } finally {
      sseProbe("turn.finally", { release: abortRef.current === ctrl })
      clearInterval(watchdog)
      stopContext.resolveTurnId(null)
      if (activeChatStopRef.current === stopContext) activeChatStopRef.current = null
      if (stopPendingOwnerRef.current === stopContext) {
        stopPendingOwnerRef.current = null
        setStopPending(false)
      }
      if (ownsTurn()) {
        sealCurrentWorkSegment(workRowKeys, terminalAtMs ?? Date.now())
        if (abortRef.current === ctrl) {
          abortRef.current = null
          setChatBusy(false)
        }
        currentTurnRef.current = releaseTurnOwner(currentTurnRef.current, turnOwner)
      }
    }
  }

  useEffect(() => {
    if (!firstMessage || initialRunId || openingHistory !== "empty" || firstMessageSentRef.current) return
    firstMessageSentRef.current = true
    void (async () => {
      const rollbackId = crypto.randomUUID()
      const handoffSkill = firstMessage.skill
        ? (firstMessage.skillOption ?? skillOptionForReference(firstMessage.skill))
        : null
      rememberSkillOption(handoffSkill)
      setMessages((prev) => [
        ...prev,
        {
          id: rollbackId,
          role: "user" as const,
          content: firstMessage.text,
          skill: firstMessage.skill,
          assets: messageAssetsFromAttachments(firstMessage.attachments ?? []),
          at: new Date().toISOString(),
        },
      ])
      await sendChat(firstMessage.text, {
        firstMessage: true,
        draft: firstMessage.text,
        mentions: firstMessage.mentions,
        skill: handoffSkill,
        personaId: firstMessage.personaId,
        attachments: firstMessage.attachments ?? [],
        rollbackId,
      })
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openingHistory, firstMessage, initialRunId])

  const handleGroupSubmit = async (
    answers: BriefAnswerItem[],
  ) => {
    const question = pendingQuestion
    const digest = question?.question?.group_digest
    if (!question || !digest || !(question.question?.items?.length)) return
    const group = groupAnswerDisplay(question, answers)
    const displayText = group.items.map((item) => item.answer).filter(Boolean).join(" · ")
    if (answering) return
    await settleAnswerTurn(
      question,
      { kind: "group", group_digest: digest, answers },
      displayText,
      group,
    )
  }

  /** Docked question answered by an option click — the answer endpoint
   * records it and continues the conversation (answer = resume).
   * Optimistic posture (chat-flow-sequencing B): the clicked option
   * collapses into the flow INSTANTLY (question + label) — the card never
   * sits waiting on a full answer round-trip — and the continuation STREAMS
   * below it (answer SSE, 2026-09-04 验收批: the slot-answer continuation
   * is an LLM turn, so an option click gets the same typing animation as a
   * typed turn — deltas render into a streaming preview message, the
   * terminal frame's envelope replaces it 真值裁决). The pencil row's
   * freeform text lands on the SAME machine via handleFreeformAnswer /
   * settleAnswerTurn. Failure rolls the optimistic block back and re-docks
   * the question (the server settled nothing). */
  const handleOptionAnswer = async (
    optionId: string,
  ) => {
    const question = pendingQuestion
    if (!question) return
    const option = question.question?.options?.find((o) => o.id === optionId)
    if (answering || !option) return
    await settleAnswerTurn(question, { kind: "option", option_id: optionId }, option.label)
  }

  /** The shared answer settlement machine: an option click and a pencil-row
   * freeform text ride the SAME stream (W7 — the freeform pencil used to
   * ride sendChat, where an options question's non-hit text settled as
   * NOTHING: no answered_at, a stuck dock, and the next turn's agent
   * re-asking). Optimistic archive → answer SSE → envelope splice →
   * follow-up dock, one anatomy for both payloads. `displayText` is the QA
   * block's answer line (the option's label / the freeform text verbatim —
   * the envelope's archived row resolves to the same wording, so the
   * optimistic block and the archive never flip). */
  const settleAnswerTurn = async (
    question: QuestionMessage,
    body:
      | { kind: "option"; option_id: string }
      | { kind: "freeform"; text: string }
      | { kind: "group"; group_digest: string; answers: BriefAnswerItem[] },
    displayText: string,
    group?: ReturnType<typeof groupAnswerDisplay>,
  ) => {
    // C8-c: same rollback-scope handover as sendChat's turn start.
    liveCandidateRowsRef.current.clear()
    pendingCandidateRowsRef.current = []
    candidateTurnSnapshotRef.current = new Map(messagesRef.current.flatMap((message) =>
      message.candidates
        ? [[message.candidates.candidateSetId, [...message.candidates.selected]] as [string, number[]]]
        : [],
    ))
    const optimisticId = crypto.randomUUID()
    const previewId = `answer-preview-${optimisticId}`
    const turnOwner = {
      localId: optimisticId,
      serverId: question.turn_id ?? null,
      adoptLocal: false,
    }
    currentTurnRef.current = turnOwner
    const ownsTurn = () => isTurnOwner(currentTurnRef.current, turnOwner)
    const adoptTurnId = (serverId?: string | null) =>
      ownsTurn() ? adoptCurrentTurnId(serverId) : undefined
    const reconcileTurnRows = (rows: OverlayMessage[]) =>
      ownsTurn() ? reconcileCurrentTurnRows(rows) : rows
    setAnswering(true)
    setChatBusy(true)
    setProseActive(false)
    setThinkingPhase(null)
    resetInterimActivityGates()
    setActivities(resetActivities()) // the answer continuation is its own turn — new stream
    currentActivityRowKeysRef.current = new Set()
    const workRowKeys = currentActivityRowKeysRef.current
    let terminalAtMs: number | null = null
    setPendingQuestion(null)
    setMessages((prev) => [...prev, {
      id: optimisticId,
      role: "assistant",
      content: "",
      turnId: question.turn_id ?? undefined,
      independentKind: "qa",
      qa: buildQaBlock(question, displayText, false, group),
      at: new Date().toISOString(),
      clientVisibleAtMs: Date.now(),
    }])

    scrollerSendRef.current?.() // an option click is the same live-edge intent
    // Typewriter pacing (same reason as sendChat — 2026-08-05 fix): the
    // reasoning model tends to deliver the echo in one coarse chunk right
    // before the terminal frame; raw appends read as "popped in at once",
    // which is the exact symptom this stream exists to kill. The interim_prose
    // segmentation machine is the extracted shared seat (speechSegments.ts)
    // — the answer continuation's pre-read speech and follow-up reply are
    // SEPARATE bubbles with the design beat's activity rows between them,
    // matching the persisted order (sendChat's inline law, one semantics).
    const segments = createSpeechSegments({
      baseId: previewId,
      apply: (update) => setMessages((prev) => (ownsTurn() ? update(prev) : prev)),
      setProseActive: (active) => {
        if (ownsTurn()) setProseActive(active)
      },
      onVisible: (rowId, atMs) => {
        if (ownsTurn()) noteSpeechVisible(rowId, atMs, workRowKeys)
      },
      onInterimStart: (rowId) => {
        if (ownsTurn()) beginInterimActivityGate(rowId)
      },
      onInterimSettled: (rowId) => {
        if (ownsTurn()) settleInterimActivityGate(rowId)
      },
      turnId: () => adoptTurnId(),
    })
    // Dead-stream watchdog (the chat turn's machinery twin): answer turns
    // have no user stop and no reconcile — a silently dead pipe would
    // otherwise leave chatBusy stuck forever (the now-line shimmering, the
    // composer dead until refresh). The abort lands in the catch below.
    const answerWatchdog = armAnswerWatchdog(
      STREAM_SILENCE_DEAD_MS,
      STREAM_WATCHDOG_TICK_MS,
    )
    const ownFrame = <Args extends unknown[]>(handler: (...args: Args) => void) =>
      (...args: Args) => {
        if (!ownsTurn()) return
        answerWatchdog.poke()
        handler(...args)
      }
    try {
      const data = await streamAnswer<{
        answered_question: QuestionMessage
        follow_up: QuestionMessage | null
      }>(question.id, body, {
        signal: answerWatchdog.signal,
        onDelta: ownFrame((text) => {
          // 出生钉位 lives inside the segments machine: the preview row is
          // born at the delta's RECEIPT — a hidden tab throttles the
          // typewriter's timer while a read's row-append lands
          // synchronously and would otherwise claim the array position
          // ahead of the speech.
          segments.onDelta(text)
        }),
        onThinking: ownFrame((payload) => {
          // Same protocol as the sendChat handler above: `"phase" in
          // payload` = a labelled hand-over or the explicit clear
          // (phase: null); bare keepalives leave the label untouched.
          if ("phase" in payload) {
            setThinkingPhase(payload.phase ?? null)
          }
        }),
        // The answer continuation's interim_prose channel (the design beat
        // rides this path): without it the pre-read speech merged into the
        // follow-up bubble and the live order contradicted the persisted
        // one (interim_prose → activity rows → reply).
        onInterimProse: ownFrame((text, at, turnId, messageId, seq) => {
          segments.onInterimProse(text, at, turnId, messageId, seq)
        }),
        onActivity: ownFrame((frame) => {
          handleActivityFrame(frame)
        }),
        onCandidates: ownFrame((event) => {
          handleCandidatesFrame(event)
        }),
        onRowAppend: ownFrame((row) => {
          handleRowAppend(row)
        }),
        onRowUpdate: ownFrame((id, frame) => {
          handleRowUpdate(id, frame)
        }),
      })
      if (!ownsTurn()) return
      terminalAtMs = Date.now()
      if (body.kind === "group") {
        setQuestionGroupDrafts((previous) => Object.fromEntries(
          Object.entries(previous).filter(([key]) => !key.endsWith(`:${body.group_digest}`)),
        ))
      }
      // Envelope wins (2026-09-06 原地落定，与 sendChat 的 finalizePreview
      // 同一纪律): the optimistic block becomes the real answered row AT
      // ITS OWN INDEX and the streaming preview settles static under the
      // SAME key — never a remount. The old delete-then-repush remounted
      // the settled echo and replayed its entrance animation (a visible
      // flicker right after the last character). The follow-up's prose is
      // already IN the preview → handleAssistantMessage rides echoCarried.
      // 打字机律·G2 修律 (sendChat 同款): the speech-commit protocol's flush
      // burst lands in this queue right before the envelope — flush() would
      // teleport it whole; drain() paces it out at cadence before the
      // archive splice (prose visibly leads, the settled rows follow). The
      // interim_prose chain drains FIRST (an in-flight interim_prose delivery
      // finishes before the envelope's prose paces).
      await segments.drain()
      if (!ownsTurn()) return
      setThinkingPhase(null)
      settleActivities("completed") // defensive twin of the server sweep
      noteObservedSeq(data.answered_question.seq)
      noteObservedSeq(data.follow_up?.seq)
      adoptTurnId(data.follow_up?.turn_id ?? data.answered_question.turn_id)
      setMessages((prev) => (ownsTurn() ? reconcileTurnRows(prev) : prev))
      const answeredRow = buildAnsweredQuestionRow(data.answered_question)
      const followUp = data.follow_up ? journeyTranscriptRow(data.follow_up) : null
      // 打字机律最后闸门 (sendChat 同款): a zero-delta follow-up (the
      // funnel's repair round never streams) paces its prose through the
      // preview bubble BEFORE the archive splice — the echo visibly leads,
      // the settled rows follow. T2b: a read-tool turn's follow-up EXTENDS
      // the streamed prefix — the unseen tail paces through the same
      // typewriter (never a blob, never an erase). The pacing decision and
      // the splice are the extracted pure seam (answerSettlement.ts,
      // ADR-093 §1 信封对账补全): the paced prose IS the stamped prose —
      // the preview never settles on a text the archive would not replay.
      if (followUp) {
        const pacing = planEnvelopePacing({
          envelopeProse: answerEnvelopeProse(followUp),
          previewStreamed: segments.streamedAny,
          previewText: segments.previewText,
        })
        if (pacing) {
          segments.push(pacing.paceText)
          await segments.drain()
          if (!ownsTurn()) return
        }
      }
      const pendingCandidates = pendingCandidateRowsRef.current
      pendingCandidateRowsRef.current = []
      setMessages((prev) =>
        ownsTurn()
          ? spliceAnswerEnvelope(prev, {
              optimisticId,
              previewId,
              answeredRow,
              followUp,
              pendingCandidates,
            })
          : prev,
      )
      if (followUp) {
        if (preparationTool(followUp)) setMessages((prev) => prev.filter((m) => m.id !== previewId))
        // echoCarried ≡ the settled bubble carries streamed prose
        // (2026-09-09 单派生): a paced zero-delta follow-up rides the same
        // typewriter, whose callback flips the flag — `streamedAny ||
        // followUpPaced` was the same fact said twice.
        await handleAssistantMessage(followUp, {
          echoCarried: segments.streamedAny,
        })
        if (!ownsTurn()) return
        // Run-landing parity with sendChat's `data.run_id` seat: a
        // run-bearing follow-up (the answered question's continuation
        // started a run server-side) must land the dock on the run surface
        // too — setRunId attaches the live run channel (RunTaskList's
        // dynamic row), onRunStarted makes the page refetch the graph so
        // hasRuns flips and the canvas actually reveals + grows. Without
        // this the run only appears after a manual refresh and the page
        // stays stuck in the full (centered-chat) form.
        if (followUp.workflow_run_id) landOnStartedRun(followUp.workflow_run_id)
      }
    } catch (e) {
      terminalAtMs ??= Date.now()
      // A machinery abort (the answer watchdog — this path has NO user
      // stop): the pipe went silently dead past the server's keepalive
      // guarantee. The answer may still have landed server-side — the
      // rollback + the restored dock below are the recovery, and a retry
      // settles quietly if so (the settled-question codes).
      const aborted = e instanceof DOMException && e.name === "AbortError"
      // The stream helper rejects with the server's detail (the JSON path's
      // toast semantics — manual here, apiFetch is not in the loop). flush
      // stops the pacing clock — a lingering tick would re-create the
      // preview right after the rollback removed it. A structured credits
      // shortfall skips the toast and lands as the in-flow grey row instead
      // (双路同语义 with the typed Start).
      segments.flush()
      if (!ownsTurn()) return
      setThinkingPhase(null)
      settleActivities(aborted ? "cancelled" : "failed") // T16-B: the failed answer leaves nothing spinning
      rollbackCandidateRows()
      setMessages((prev) =>
        prev.filter(
          (m) => m.id !== optimisticId && !isSpeechSegmentRow(m.id, previewId),
        ),
      )
      const settledCode =
        e instanceof StreamTurnError ? questionSettledCode(e.detail) : null
      if (settledCode) {
        // A settled question never re-docks (2026-09-28 — the「点击回答
        // 仍然报错」loop): the click raced the question's own settlement
        // (a newer question superseded it / it was answered already), so
        // the server recorded nothing — the pill stays GONE and a quiet
        // localized line replaces the raw English error toast.
        setPendingQuestion(null)
        toast.info(
          t(
            settledCode === "question.superseded"
              ? "chat.questionOutdated"
              : "chat.questionAnswered",
          ),
        )
      } else {
        setPendingQuestion(question)
        const credits =
          e instanceof StreamTurnError ? asCreditsInsufficient(e.detail) : null
        if (credits) {
          pushCreditsGreyRow(
            credits,
            e instanceof StreamTurnError ? e.turnId : undefined,
          )
        } else {
          // An aborted pipe never toasts the raw DOMException — the
          // localized failure word + the restored dock say it (retry).
          toast.error(
            aborted
              ? t("chat.failed")
              : e instanceof Error
                ? e.message
                : t("chat.failed"),
          )
        }
      }
    } finally {
      answerWatchdog.disarm()
      if (ownsTurn()) {
        sealCurrentWorkSegment(workRowKeys, terminalAtMs ?? Date.now())
        setAnswering(false)
        setChatBusy(false)
        currentTurnRef.current = releaseTurnOwner(currentTurnRef.current, turnOwner)
      }
    }
  }

  /** Question bail — the question line's × (ADR-051): a graceful exit, never
   * an error toast (#5). For an interrupt (a run parked on the answer) the
   * endpoint settles the node, skips the downstream and completes the run
   * synchronously — the dock keeps watching in place (the terminal snapshot
   * arrives over its own SSE); for a plain chat question it just records the
   * skip. */
  const handleBailQuestion = async () => {
    if (!pendingQuestion || answering) return
    setAnswering(true)
    const wasPlan = pendingQuestion.question?.kind === "task_book"
    const groupDigest = pendingQuestion.question?.group_digest ?? null
    const isGroup = (pendingQuestion.question?.items?.length ?? 0) > 0 && groupDigest !== null
    const body = isGroup
      ? {
          kind: "bail" as const,
          group_digest: groupDigest,
          answers: groupDraftAnswers(pendingQuestion),
        }
      : { kind: "bail" as const }
    try {
      const res = await apiFetch(
        `/api/v1/chat/messages/${pendingQuestion.id}/answer`,
        // toast:false — a settled-question 409 is a quiet local settle
        // (the option path's same grace), not the global error toast.
        { method: "POST", body, toast: false },
      )
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as {
          detail?: unknown
        }
        const settledCode = questionSettledCode(data.detail)
        if (settledCode) {
          setPendingQuestion(null)
          toast.info(
            t(
              settledCode === "question.superseded"
                ? "chat.questionOutdated"
                : "chat.questionAnswered",
            ),
          )
        } else {
          toast.error(t("chat.failed"))
        }
        return
      }
      const data = (await res.json()) as { answered_question: QuestionMessage }
      const hadRun = !!pendingQuestion.workflow_run_id
      setPendingQuestion(null)
      if (groupDigest) {
        setQuestionGroupDrafts((previous) => Object.fromEntries(
          Object.entries(previous).filter(([key]) => !key.endsWith(`:${groupDigest}`)),
        ))
      }
      // A task_book bail tears the draft graph down server-side — the page
      // morphs back to the chat world (K5 条款: bail 拆图).
      if (wasPlan) void projectChangedRef.current()
      pushAnsweredQuestion(data.answered_question)
      if (hadRun) toast.info(t("generationOverlay.stopped"))
    } finally {
      setAnswering(false)
    }
  }

  /** The options dock's pencil row (ADR-053 R1 阻塞形态): with the input
   * row morphed away, a freeform answer rides the ANSWER ENDPOINT — the
   * same settlement machine as an option click (W7: it used to ride
   * sendChat, where an options question's non-hit text settled as NOTHING —
   * no answered_at, a stuck dock, and the next turn's agent re-asking).
   * A typed letter/number/label hit converts PRE-POST to the option pick
   * (matchOptionByText, the client mirror of the server's autoResume
   * `_match_option` — a hit settles kind="option" exactly like the chat
   * input's typed hit); anything else settles kind="freeform" with the
   * text verbatim. The flow record is the optimistic QA block (the point's
   * same anatomy), never a user bubble — the archive's answered row
   * replays byte-identical. */
  const handleFreeformAnswer = async (
    text: string,
  ) => {
    const question = pendingQuestion
    if (!question) return
    if (question.question?.kind !== "question" || answering) return
    const matched = matchOptionByText(text, question.question.options ?? [])
    if (matched) {
      await handleOptionAnswer(matched.id)
      return
    }
    await settleAnswerTurn(question, { kind: "freeform", text }, text)
  }

  /** Stop either the attached active Run or the current assistant Turn. A
   * failed control request leaves the real work running and never fakes a stop. */
  const latestUser = messages.slice().reverse().find((m) => m.role === "user")
  const journeyActive = journey?.state === "active" && !pendingQuestion && (!latestUser ||
    latestUser.id === journey.openingId || latestUser.serverMessageId === journey.openingId ||
    latestUser.turnId === journey.openingId)

  const handleStop = async () => {
    if (stopPending || runCancelPending) return
    const controller = abortRef.current
    if (!chatBusy && journeyActive && journey) {
      setStopPending(true)
      try {
        const res = await apiFetch(`/api/v1/chat/turns/${journey.openingId}/stop`, {
          method: "POST", body: { scope: "media_preparation" },
        })
        if (res.ok) {
          const { journey_message } = await res.json() as { journey_message?: Pick<QuestionMessage, "seq" | "intent"> }
          if (journey_message) observeJourney([journey_message])
        }
      } catch {
        // apiFetch reports the error. Keep following the worker until it settles.
      } finally {
        setStopPending(false)
      }
      return
    }
    if (runAttached && runId) {
      setRunCancelPending(true)
      let requested = false
      try {
        const res = await apiFetch(`/api/v1/runs/${runId}/cancel`, {
          method: "POST",
          body: {},
        })
        if (!res.ok) return
        requested = true
        // The Run cancel is authoritative; an associated assistant stream may
        // only be finishing its already-committed typewriter drain.
        controller?.abort()
        requestAnimationFrame(() => editorRef.current?.focus())
      } catch {
        // apiFetch already reported the failure; the Run remains active.
      } finally {
        if (!requested) setRunCancelPending(false)
      }
      return
    }
    if (!controller) return
    const context = activeChatStopRef.current
    if (!context || context.controller !== controller) {
      // Answer streams keep their existing abort/answer settlement; the Chat
      // Stop control protocol must not turn an OPTIONS answer into a prompt.
      controller.abort()
      if (abortRef.current === controller) {
        abortRef.current = null
        setChatBusy(false)
      }
      requestAnimationFrame(() => editorRef.current?.focus())
      return
    }
    if (context.stopRequested) return
    let settleStop!: () => void
    context.stopPromise = new Promise<void>((resolve) => {
      settleStop = resolve
    })
    stopPendingOwnerRef.current = context
    setStopPending(true)
    try {
      const turnId = await context.turnIdPromise
      if (!turnId) return
      const structureIds = new Set<string>()
      for (const [serverMessageId, ownerTurnId] of visibleStructureTurnsRef.current) {
        if (ownerTurnId === turnId) structureIds.add(serverMessageId)
      }
      const frontier = visibleFrontierForTurn(messagesRef.current, turnId, structureIds)
      const res = await apiFetch(`/api/v1/chat/turns/${turnId}/stop`, {
        method: "POST",
        body: frontier,
      })
      if (!res.ok) return
      const outcome = (await res.json()) as { turn_state?: string | null }
      // A terminal Turn wins the race; Stop otherwise returns the one durable
      // outcome already committed by the server, never a second client guess.
      if (outcome.turn_state !== "cancelled" && outcome.turn_state !== "retracted") return
      context.stopOutcome = outcome.turn_state
      context.frontier = frontier
      context.stopRequested = true
      controller.abort()
      requestAnimationFrame(() => editorRef.current?.focus())
    } catch {
      // apiFetch already reported the failure; keep the assistant stream alive.
    } finally {
      settleStop()
      if (stopPendingOwnerRef.current === context) {
        stopPendingOwnerRef.current = null
        setStopPending(false)
      }
    }
  }

  // Send-time follow re-arm (see ScrollerSendBridge): filled by the bridge
  // inside the scroller Provider.
  const scrollerSendRef = useRef<(() => void) | null>(null)

  const handleSend = () => {
    const text = input.trim()
    const ready = staged.filter(
      (s): s is StagedUpload & { asset: ProjectAsset } =>
        s.status === "done" && !!s.asset
    )
    // An in-flight upload blocks send — the chips must settle first
    // (× removes one). answering: an option answer is mid-flight — its
    // optimistic archive + the follow-up LLM turn own the flow until they
    // land.
    if ((!text && ready.length === 0) || chatBusy || answering || runAttached) return
    if (staged.some((s) => s.status === "uploading")) return
    const sentAssets = ready.map((s) => s.asset)
    // The assets state learns the upload at SEND, never at stage (the send
    // gate — 暂存 ≠ 交付, 2026-09-28). The merge arms the processing watch
    // from this beat instead of waiting for the post-turn refetch: a long
    // read shows its "Watching…" line right after the turn's prose. The
    // message below carries the ids, so the gate's sentAssetIds covers them
    // in the same batch.
    setAssets((prev) => {
      const known = new Set(prev.map((a) => a.id))
      const additions = sentAssets.filter((a) => !known.has(a.id))
      return additions.length > 0 ? [...prev, ...additions] : prev
    })
    const rollbackId = crypto.randomUUID()
    const sentSkill = selectedSkill
    setMessages((prev) => [
      ...prev,
      {
        id: rollbackId,
        role: "user",
        content: text,
        skill: sentSkill?.reference,
        assets: sentAssets,
        at: new Date().toISOString(),
      },
    ])
    // Consumed on send (chip law ②): the editor's clear funnels the emptied
    // {text, mentions} back through onChange; an error chip stays staged for
    // retry/removal — it never rides a message.
    editorRef.current?.clear()
    setStaged((prev) => prev.filter((s) => s.status !== "done"))
    // Your own send opens the flow — the reply lands there.

    // Sending = explicit "take me to the live edge" intent (2026-09-24):
    // re-arm the scroller's following-bottom mode AND jump — the library's
    // 8px stickiness (plus content-visibility's height estimates) otherwise
    // leaves the viewport stranded mid-flow with the ↓ pill showing.
    scrollerSendRef.current?.()
    void sendChat(text, {
      rollbackId,
      draft: text,
      mentions,
      skill: sentSkill,
      rollbackMentions: mentions,
      attachments: ready.map((s) =>
        chatAttachmentFromAsset(s.asset, {
          name: s.file.name,
          size: s.size ?? s.file.size,
        }),
      ),
      rollbackStaged: ready,
    })
  }

  // The dock's live form outside the confirm beat: a pending OPTIONS
  // question from the chat loop (task_book docks only while confirming; an
  // options-empty text question never docks — 形态律 ADR-053 R1).
  // ask_user 不变量 (2026-09-13): the flow's QA archive is the record of a
  // DECIDED question; the dock is the one PENDING decision — the pair never
  // coexists. Every settle path already lands the QA (option click's
  // optimistic block, typed autoResume / judged settlement's envelope,
  // bail, a refresh's replay) — so if the docked row's QA is in the flow,
  // the dock is settled no matter which side failed to retire it (a stale
  // re-dock once sat under its own QA archive mid-stream, dimmed options
  // and all). Heal the state AND gate the render on the same fact.
  const dockSettled = pendingQuestion
    ? messages.some((m) => m.qa?.questionId === pendingQuestion.id)
    : false
  useEffect(() => {
    if (dockSettled) setPendingQuestion(null)
  }, [dockSettled])

  const pillQuestion =
    pendingQuestion &&
    !dockSettled &&
    pendingQuestion.question?.kind === "question" &&
    !pendingQuestion.answer &&
    ((pendingQuestion.question?.options?.length ?? 0) > 0 || (pendingQuestion.question?.items?.length ?? 0) > 0)
      ? pendingQuestion
      : null

  // 确认 pill (ADR-117 §4 — 画板 C): the ONLY chrome the confirm beat keeps.
  // Render predicate = the dock's presentation-time stamp
  // (`requires_confirmation` — the client NEVER derives the need itself):
  // auto without an independent confirmation debt hides it; the first Film
  // draft's review wait adds no extra pill. Ask, awaiting-production,
  // guardrail and unquotable stamps still show it. Legacy rows predate the
  // stamp → read as owed (读容忍 in the conservative direction: a waiting
  // dock keeps its affordance). A persisted first_draft_review stamp came
  // only from the retired auto-only override, never from ask or a stronger
  // debt; read it as no independent confirmation debt as well.
  // The beat gate (confirmActive) still rules — the pill never opens on a
  // frame the server hasn't named ready, and never over a live run.
  const planPill =
    pendingQuestion &&
    !dockSettled &&
    pendingQuestion.question?.kind === "task_book" &&
    !pendingQuestion.answer &&
    (pendingQuestion.question?.requires_confirmation ?? true) &&
    pendingQuestion.question?.confirm_reason !== "first_draft_review"
      ? pendingQuestion
      : null
  const confirmPillActive = confirmActive && planPill != null
  // The label family keys on the stamped reason: money reasons carry the
  // price (quote_high is the server fold's high end — never a client
  // computation); the NULL family announces the deferred quote; a bare
  // execution-ask rides the plain verb. (D1: 执行=ask → 不带价; 费用=ask /
  // 守卫线 → 带价.)
  const planPillLabel = (() => {
    const q = planPill?.question
    if (!q) return ""
    if (q.unquotable) return t("generationOverlay.confirmPillStartDeferred")
    const priced =
      q.confirm_reason === "credits_pref" ||
      q.confirm_reason === "above_guardrail"
    return priced && q.quote_high != null
      ? t("generationOverlay.confirmPillStartPriced", { n: q.quote_high })
      : t("generationOverlay.confirmPillStart")
  })()

  // Start is an ordinary user message. The existing sendChat turn carries
  // the panel's current intent; only the next LLM turn may call start_run.
  const handleConfirmPill = () => {
    const text = planPillLabel.trim()
    if (!confirmPillActive || chatBusy || answering || !text) return
    const rollbackId = crypto.randomUUID()
    setMessages((prev) => [
      ...prev,
      {
        id: rollbackId,
        role: "user",
        content: text,
        at: new Date().toISOString(),
      },
    ])

    scrollerSendRef.current?.()
    void sendChat(text, { rollbackId })
  }

  // The NON-run timeline (ADR-108): every transcript row renders at its array
  // position. Run anchors join this same unit stream in ChatConversation's
  // block projection; no timestamp-based insertion lives here.
  const conversationUnits = useMemo(
    () => foldActivityUnits(buildConversationUnits(messages)),
    [messages],
  )

  const openFold = conversationUnits.slice().reverse().find((unit) =>
    unit.kind === "activityFold" && unit.openTail,
  )
  const workFold = openFold?.kind === "activityFold" ? openFold : undefined
  const preparationRunId = workFold?.workRunIds?.at(-1)
  const preparationStart = preparationRunId
    ? messages.find((m) => m.runId === preparationRunId && m.activity?.kind === "run")
    : undefined
  const followingJourney = journeyActive && workFold?.turnId === journey?.openingId
  const attachedPreparation = !!preparationRunId && runId === preparationRunId
  const livePreparation = !!preparationStart && preparationStart.activity?.status !== "cancelled" &&
    !(journey?.openingId === workFold?.turnId && journey?.state === "stopped") && (attachedPreparation
    ? status !== "cancelled" && (!terminal || reviewPending || followingJourney)
    : followingJourney)
  // Worker continuations have no browser Chat request. Their persisted tool
  // callbacks still update the same open activity fold during the journey poll.
  const workerContinuing = !chatBusy && followingJourney && !preparationRunId && !pendingQuestion

  // The now label is shared by the bottom seat (no current activity host
  // yet) and the current open fold (from its FIRST active host onward).
  // Thus previous-prose typing can hide the bottom Thinking seat, but it can
  // never erase a newly-born activity's own timeline row. Buffered text
  // alone does NOT hide the bottom seat: only a streaming row with actually-
  // released non-whitespace content counts as visible prose. An unseen
  // envelope tail cannot seal the segment or leave a blank status seat.
  const visibleProseTyping =
    proseActive &&
    messages.some((m) => m.streaming && m.content.trim().length > 0)
  const activeActivity = activities.find((a) => a.status === "active")
  const processingAssets = assets.filter(
    (a) =>
      sentAssetIds.has(a.id) &&
      (a.processing_status === "pending" ||
        a.processing_status === "processing"),
  )
  const nowRow: NowRowPayload | null = (() => {
    // Concrete film phases refine the generic plan activity. A terminal
    // sweep normally removes active frames; the chatBusy gate is the second
    // guarantee that a dead / recovered turn cannot keep shimmering.
    if (chatBusy && activeActivity && !(activeActivity.kind === "draft" &&
      ["capturing", "storyboarding", "storyboard_revision"].includes(thinkingPhase ?? ""))) {
      return activeActivity
    }
    const think = (
      key: string | null,
      name?: string,
      count?: number,
    ): NowRowPayload => ({
      activity_id: "__now__",
      seq: 0,
      kind: "think",
      status: "active",
      key,
      name,
      count,
    })
    if (livePreparation && preparationStart) {
      if (messages.some((m) => m.mediaProgress && m.runId === preparationRunId)) {
        return workFold?.liveActivity ?? think(null)
      }
      if (attachedPreparation && terminal) return think("chat.closingReview")
      const step = attachedPreparation ? steps.find((item) => item.status === "running") : undefined
      const stage = step && visibleProductionStages(step).reverse().find((item) => item.status === "running")
      const index = stage?.scene_id && preparationStart.sceneOrder
        ? preparationStart.sceneOrder.indexOf(stage.scene_id) + 1 : step?.scene_index
      if (index && (stage?.kind === "visual_assets" || stage?.kind === "speech_media")) {
        const key = stage.kind === "visual_assets" ? "pictureScene" : "voiceScene"
        return think(`chat.preparationProgress.${key}`, chineseSceneNumber(index), index)
      }
      if (stage && stage.kind !== "validate") {
        if (stage.kind === "visual_assets" && stage.item_count) {
          return think("chat.preparationProgress.imagesProcessed", undefined, stage.item_count)
        }
        return think(`chat.preparationProgress.${stage.kind}`)
      }
      return think(preparationStart.activity?.key ?? null)
    }
    if (workerContinuing) return workFold?.liveActivity ?? think(null)
    if (chatBusy) {
      return think(thinkingPhase ? `chat.thinkingPhases.${thinkingPhase}` : null)
    }
    // 带计数 (2026-09-24 用户拍板): several files draining together read as
    // "processing N files" (中性词 — 混合批次不知动谁), a lone one names
    // itself with the verb fork (批「动词」2026-09-27: video=看 / audio=听).
    if (processingAssets.length > 1) {
      return think("chat.material.readingMany", undefined, processingAssets.length)
    }
    if (processingAssets.length === 1) {
      const lone = processingAssets[0]
      // 工序化 (ADR-095 §2): the chain's live stage speaks the user-language
      // process truth — asr → transcribing, speaker_map/prosody →
      // understanding (the same 转写/理解 vocabulary the run stepper
      // shares). Unknown/absent stages (hash, extract, legacy rows without
      // the key) fall back to the type-verb line below.
      if (lone.processing_stage === "asr") {
        return think("chat.material.transcribing", lone.title ?? undefined)
      }
      if (
        lone.processing_stage === "speaker_map" ||
        lone.processing_stage === "prosody"
      ) {
        return think("chat.material.understandingAsset", lone.title ?? undefined)
      }
      return think(
        activityAssetKey("chat.material.reading", lone.type),
        lone.title ?? undefined,
      )
    }
    return null
  })()

  /** The last open fold born on THIS turn owns the live segment in the
   * timeline. Host-row identity prevents a historical segment from reopening.
   * A contiguous failure has already settled its own fold;
   * only a later open fold can own the live seat. The single owner and the
   * bottom seat are mutually exclusive. conversation/runStream read this
   * SAME owner key. */
  let liveWorkFoldKey: string | null = null
  if (chatBusy) {
    for (const unit of conversationUnits) {
      if (
        unit.kind === "activityFold" &&
        unit.openTail &&
        currentActivityRowKeysRef.current.has(unit.rowKey)
      ) {
        liveWorkFoldKey = unit.rowKey
      }
    }
  }
  if (workFold && (livePreparation || workerContinuing)) liveWorkFoldKey = workFold.rowKey
  const bottomNowRow =
    liveWorkFoldKey == null && !visibleProseTyping && interimActivityGateCount === 0
      ? nowRow
      : null

  /** 点值改 (B3): an inferred slot's inline-edit commit IS a normal chat
   * send — the composed statement (「受众：X」 / "Audience: X") rides the one
   * and only revision channel; the router merges it user-stated and the
   * re-docked plan carries the fresh brief. No slot-update endpoint —
   * prohibited-behavior: 禁第二修订通道. */
  /** Suggestion-pill clicks (T3 触发回合): "send" fires the pill's text as
   * the user's next message — verbatim, through the same sendChat every
   * typed turn takes (the chat surface stays the single intent door);
   * "download" one-taps the landed output via the cards' own channel. The
   * pills never carry a turn of their own. */
  const handleSuggestionClick = (s: SuggestionPill) => {
    if (s.action === "download") {
      const output = outputs.find((o) => o.id === s.output_id)
      if (output) downloadOutput(output)
      return
    }
    const text = (s.text ?? "").trim()
    if (!text || chatBusy) return
    void sendChat(text)
  }

  /* The message flow — one JSX block, one host: the stage region (the
      fullscreen chat stage in full, the panel body in panel). The message
      machine itself is untouched — only the shell changes. */
  /** Step marker label — RunTaskList owns live summary → friendly stage copy →
   * kind fallback. */
  /** One conversation message with its anchors: superseded plan-version
   * chips sit right after the echo bubble whose turn produced them; an
   * in-flight live plan card anchors after its own echo bubble. */
  const canStop = (chatBusy && abortRef.current !== null) || runAttached || journeyActive
  const chatScroller = (
    <ChatConversation
      messages={messages}
      planVersions={planVersions}
      renderPlanVersion={(version, index) => (
        <PlanVersionChip
          n={index + 1}
          plan={version.plan}
          summary={titleOf(version.plan)}
          expanded={expandedVersion === index}
          onToggle={() =>
            setExpandedVersion(
              expandedVersion === index ? null : index
            )
          }
          onRestore={() => restoreVersion(index)}
          taskLabel={taskLabel}
        />
      )}
      conversationUnits={conversationUnits}
      chatOutputs={chatOutputs}
      skillOptions={skillOptions}
      openOutputViewer={openOutputViewer}
      runId={historySettled || runStartedExplicitly ? runId : null}
      chatBusy={chatBusy}
      onSuggestionClick={handleSuggestionClick}
      onRunStarted={landOnStartedRun}
      onStructureVisible={registerStructureVisibility}
      pendingPlanMessageId={
        pendingQuestion?.question?.kind === "task_book" && !pendingQuestion.answer
          ? pendingQuestion.id
          : null
      }
      presentationRecovery={presentationRecovery}
      currentActivityRowKeysRef={currentActivityRowKeysRef}
      liveWorkFoldKey={liveWorkFoldKey}
      nowRow={nowRow}
      bottomNowRow={bottomNowRow}
      activeTurnId={adoptCurrentTurnId() ?? null}
      steps={steps}
      runTitle={runTitle}
      runCreatedAt={runCreatedAt}
      terminal={terminal}
      status={status}
      reviewPending={reviewPending}
      runWorkEndedAtMs={runWorkEndedAtMs}
      runFallbackOutputs={runFallbackOutputs}
      hasUploads={hasUploads}
      assets={assets}
      scrollerSendRef={scrollerSendRef}
    />
  )

  // The question docks render as chromeless content (plain) — the floating
  // question pill in the bottom row owns the frost and rounding (2026-09-02
  // 拆粘: they used to be square children of the ONE frosted container).
  // 形态律 (ADR-053 R1, 阻塞形态 2026-09-04 翻回): while an OPTIONS question
  // is pending the dock MORPHS — the input row and the disclaimer hide, and
  // the pill (its options + the pencil freeform row) owns the bottom row
  // (FLORA/Opus 同款). A text question never docks (plain flow speech,
  // input live); the task-book pill stays non-blocking.
  // Phase 3 Batch B: the retired `phase !== "confirm"` conjunct was
  // defensive-only — an options question never coexists with a parked
  // task_book server-side (判词⑦ 扩座: an ask while a question is pending
  // is an interjection, never a new dock), and pillQuestion's kind filter
  // already excludes task_book rows. No replacement guard.
  const pillDock =
    pillQuestion ? (
      <QuestionDock
        kind="question"
        plain
        question={bareQuestion(pillQuestion)}
        options={pillQuestion.question?.options ?? []}
        items={pillQuestion.question?.items ?? []}
        groupDigest={pillQuestion.question?.group_digest ?? null}
        groupAnswers={groupDraftAnswers(pillQuestion)}
        onGroupAnswersChange={(answers) => {
          const key = groupDraftKey(pillQuestion)
          setQuestionGroupDrafts((previous) => ({ ...previous, [key]: answers }))
        }}
        onGroupSubmit={handleGroupSubmit}
        recommendedId={pillQuestion.question?.recommended_id ?? null}
        onAnswer={handleOptionAnswer}
        answering={answering}
        onBail={handleBailQuestion}
        bailLabel={
          pillQuestion.workflow_run_id
            ? t("questionDock.bail")
            : t("questionDock.skip")
        }
        onFreeform={handleFreeformAnswer}
        freeformDisabled={chatBusy}
      />
    ) : null
  // (canvas↔chat 联动 onPlanConfirmVisible retired 2026-09-26 — Workspace
  // 合同 v4.2 C5 封板翻案: the 2026-09-25「确认 pill 首现 = 整链 fitNow」
  // beat was reversed in favor of the sealed camera law — the camera never
  // auto-fits; the dock fires no camera beat at the confirm moment. The
  // confirm pill stays the confirm beat's ONLY seat, ADR-070 unchanged.)
  // (RunStatusRow retired 2026-09-08, user ruling: the message flow's
  // RunTaskList is always on screen — the stage's scroller is resident in
  // both forms — so the folded shimmer line docked above the input was a
  // pure duplicate of the narrative row. ONE progress surface: the in-flow
  // checklist.)
  const inputBody = (
    <>
      {/* Staged attachments — the upload lifecycle lives here (never
          auto-sent): uploading chips shimmer, done chips wait for the
          send button, error chips offer retry; × removes (and deletes
          the already-created asset). */}
      {staged.length > 0 && (
        <AttachmentGroup className="px-1 pb-2">
          {staged.map((s) => (
            <StagedAttachmentChip
              key={s.localId}
              item={s}
              onRetry={() => retryStaged(s)}
              onRemove={() => removeStaged(s)}
            />
          ))}
        </AttachmentGroup>
      )}
      {/* Two-band anatomy (2026-09-06 user ruling, ElevenLabs parity —
          FINAL): text band on top (FULL width, top-aligned) + control strip
          in-flow at the bottom — two stacked regions even at rest, exactly
          ElevenLabs' composer ([text zone][+ · permissions · autonomy ·
          send]). Journey: side-lane flex (text clamped to ~73%) → floating
          strip + reserved pb-10 band (rest read half-empty) → an adaptive
          width-flip (oscillated every frame, same-hour revert — width-
          changing flips are structurally unstable) → THIS. In-flow strip:
          no overlay, no measurement, oscillation-proof by construction.
          Strip members: + (attach — ElevenLabs/FLORA's plus; the paperclip
          RETIRED, composer included), the flex-1 spacer, stop/send anchored
          right. Stadium corollary: the
          rest box is genuinely two bands now, and a capsule on multi-row
          content is broken geometry — the input is rounded-xl in every
          form (the stadium exception belonged to the retired one-row
          rest; the law survives for truly one-row boxes). */}
      <div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          accept="video/*,audio/*,image/*,.pdf,.txt,.md,.markdown,.pptx,.ppt"
          onChange={(e) => handleFilesPicked(e.target.files)}
        />
        {/* The composer family's editor (one input component across
            composer / overlay chat / output chat): @-chips inline —
            asset = context enrichment, output = the pinned revision
            target — Enter sends, IME guarded inside the component. */}
        <MentionEditor
          ref={editorRef}
          // ONE fixed placeholder per mention world (2026-09-11 user
          // ruling): a phase-aware swap (confirm → "Ask me to adjust the
          // plan…") costs more mental load than it guides — the confirm pill
          // right above already says what the next step is. The world split:
          // before any products exist there are no nodes to @mention, so
          // the copy names assets; the nodes version appears the moment the
          // mention registry carries outputs (世界自证 — the registry's own
          // content, never a form/viewport read).
          placeholder={
            (mentionContext.outputs?.length ?? 0) > 0
              ? t("generationOverlay.chatPlaceholder")
              : t("generationOverlay.chatPlaceholderAssets")
          }
          mentionContext={mentionContext}
          mentionChipClassName="bg-card"
          selectedSkill={selectedSkill}
          onSkillChange={handleSkillChange}
          onChange={handleEditorChange}
          onSubmit={handleSend}
          // Long-content headroom (2026-09-06, FLORA-measured): ~10 lines
          // visible before scrolling (was max-h-32 ≈ 6). Full-width px-3
          // text band; the vertical padding is SYMMETRIC (2026-09-23 user
          // ruling — py-2.5 both sides; the old pb-1 read lopsided against
          // the pt-2.5 head). Rest height (2026-10-15 user ruling): the box
          // hugs its content (the min-h-20 three-line floor retired — it was
          // 64px of dead air under a one-line draft), with ONE floor left:
          // min-h-15 = exactly TWO lines — the teaching placeholder is a
          // composed two-line read (2026-09-24 ruling), so the empty box is
          // two lines tall; the two-line floor makes a one-line draft the
          // same height, and the empty→typing transition never jumps.
          className="block max-h-56 min-h-15 w-full px-3 py-2.5 text-sm thin-scroll"
        />
        {/* The control strip — in-flow under the text band (ElevenLabs'
            bottom row): + opens the file picker (their + opens an upload
            menu; ours has one destination — the picker — so no menu),
            send/stop anchor the right end (the flex-1 spacer). Gaps: mt-1 + the text band's
            pb-2.5 = 14px between the input text and the strip (2026-09-23
            user ruling — 10px read cramped), and pb-1.5 → card bottom
            reads 14px (6+8), MiniMax-measured parity (same day, second
            pass: on a THIN one-line card the 18px symmetric bottom read
            too heavy — the same-day py-2.5/pb-2.5 symmetry ruling was
            superseded; the text band keeps py-2.5, the bottom zone
            tightens). Interior rhythm: 18 top / 14 middle / 14 bottom.
            GLYPH-RAIL alignment (2026-09-06
            user ruling, FLORA-measured — the dock twin of the composer's
            glyph-left-edge law): the strip carries NO container padding;
            the + glyph's LEFT edge and the ↑ glyph's RIGHT edge sit on the
            text band's 12px rails (px-3 / pr-3) via 3px button margins
            (36px button − 18px glyph = 9px inset; 12 − 9 = 3). Ghost
            buttons show no chrome at rest, so only the glyphs read —
            aligning containers leaves the glyphs visibly adrift when not
            hovering. Both glyphs are 18px for optical parity. */}
        <div className="mt-1 flex items-center gap-0.5 pb-1.5">
          <ComposerIconButton
            icon={Plus}
            label={t("generationOverlay.attachFiles")}
            className="ml-[3px]"
            onClick={() => fileInputRef.current?.click()}
          />
          <span className="min-w-0 flex-1" />
          {/* The same 36px seat switches between send and the current
              abortable stream's Stop action. */}
          <ComposerSendButton
            className="mr-[3px]"
            stop={canStop}
            disabled={
              canStop
                ? stopPending || runCancelPending
                : (!input.trim() &&
                    !staged.some((s) => s.status === "done")) ||
                  staged.some((s) => s.status === "uploading")
            }
            onClick={canStop ? handleStop : handleSend}
            label={t(canStop ? "chat.stop" : "chat.send")}
          />
        </div>
      </div>
    </>
  )

  // Radius: the input container is rounded-xl in EVERY form (2026-09-06,
  // two-band ElevenLabs anatomy — the rest box is genuinely two bands:
  // full-width text + the in-flow control strip, and the 2026-09-02 law
  // says a capsule on multi-row content is broken geometry). The dock's
  // stadium exception retired with the one-row rest it belonged to; the
  // law itself survives for truly one-row boxes. Radius still transitions
  // with the box for any future shape change.
  const inputRadius = "rounded-xl"

  return (
    <>
    <div ref={chatContainerRef} tabIndex={-1} className="ui-th-body" data-slot="agent-thread">
      <div className="min-h-0 flex-1">
            {openingHistory === "failed" && <button className="p-3 text-sm underline" onClick={() => setHistoryAttempt((n) => n + 1)}>{t("common.retryHistory")}</button>}
        {chatScroller}
      </div>
      <div className="mx-auto w-full max-w-3xl shrink-0 px-4 pb-4 pt-2">
          {/* The question pill — its own floating layer (拆粘): detached from
              the input container with a small-but-clear gap (mb-2.5 = 10px,
              user两轮裁定: 6px 太近、原型 12px 太大). rounded-xl both kinds
              (user-ruled 2026-09-02: the STADIUM belongs to the collapsed
              input group below, not to the question pill — a tall option
              list in a capsule is broken geometry anyway). Same dock-surface
              frost + subtle border recipe. */}
          {pillDock && (
            <div className="dock-surface mb-2.5 overflow-hidden rounded-xl border border-subtle">
              {pillDock}
            </div>
          )}
          {/* 确认 pill (ADR-117 §4 — 画板 C): the confirm beat's only chrome,
              shown exactly when the dock's stamp says a beat is owed
              (requires_confirmation — never client-derived). NON-blocking
              like every task_book pill before it: the input stays live
              below (a chat message revises the plan; "don't start" is said
              by not starting). Same floating-layer family as the question
              pill (dock-surface frost + subtle border, mb-2.5 gap). The text
              slot carries the plan's title (LLM-named, ADR-058's lawful
              source) — never a restated question: the echo's closing beat
              above already asked it. The click IS the user saying
              「确认生成」 through the one sendChat channel. */}
          {confirmPillActive && (
            <div className="dock-surface mb-2.5 overflow-hidden rounded-xl border border-subtle">
              <div className="flex items-center gap-2.5 px-4 py-2.5">
                <Check className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate text-sm">
                  {planSummary}
                </span>
                <Button
                  size="sm"
                  disabled={chatBusy || answering}
                  onClick={handleConfirmPill}
                >
                  {planPillLabel}
                </Button>
              </div>
            </div>
          )}
          {/* The input container — 输入框独立层律 (2026-09-02, user-ruled):
              the container owns ONLY the resident input row (+ the staged
              chips band when present) — the question floats as its own pill
              above. dock-surface:
              translucent enough that the canvas's dot grid reads through
              the frost; the subtle border is the separator — NO shadow in
              either mode (2026-10-14 user ruling: the light-mode shadow-xl
              measured invisible bottom-center on the white canvas and read
              as a gray smudge at the corners — dirt, not elevation; dark
              already cast nothing). 形态律 (ADR-053 R1 阻塞形态, 2026-09-04
              翻回): while an OPTIONS question is pending the input row
              morphs away — with no second band the container is empty, so
              the whole box hides rather than leaving a frost sliver (the
              editor stays mounted inside, DOM-owned draft intact). */}
          <div
            className={cn(
              "dock-surface relative overflow-hidden border border-subtle transition-[border-radius] duration-300 ease-out motion-reduce:transition-none",
              fileDragging &&
                "border-2 border-dashed border-foreground/30 ",
              inputRadius,
              pillDock && "hidden"
            )}
            {...fileDropProps}
          >
            {/* Drop affordance — composer parity (2026-09-24): the floating
                pill centered over the input container, pointer-events-none
                so the drop always lands on the container. Frosted floating
                layer + subtle border; icon + plain-weight label. */}
            {fileDragging && (
              <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
                <div className="overlay-surface flex items-center gap-2.5 rounded-2xl px-5 py-3 border border-subtle">
                  <Upload className="size-4.5" />
                  <span className="text-base">{t("composer.dropHint")}</span>
                </div>
              </div>
            )}
            {/* The input row morphs away while an options question is
                pending (ADR-053 R1 阻塞形态) — CSS-hidden, NOT unmounted:
                the editor keeps its DOM-owned draft across the morph. The
                condition follows the RENDERED pill (pillDock), not the raw
                pending state: while a task_book is docked the options pill
                is absent (pillQuestion's kind filter), so there the input
                must stay live (a typed answer settles via the slot
                handshake). */}
            <div className={cn("p-2", pillDock && "hidden")}>{inputBody}</div>
          </div>
      </div>
    </div>
      <ChatOutputViewer
        outputId={viewerOutputId}
        entries={chatOutputEntries}
        onOpenChange={(open) => { if (!open) closeOutputViewer() }}
        onMention={mentionViewerOutput}
      />
    </>
  )
}
