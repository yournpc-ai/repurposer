"use client"

/** GenerationOverlay — the post-composer conversation surface.
 *
 * Full-screen chat (Opus-style): the composer draft opens the conversation
 * (sent as the first /chat message on mount), the inferred task book arrives
 * as an editable plan card pinned in the flow, and confirming starts the run
 * — whose steps light up below. The bottom input is always live and every
 * turn goes through the same /chat endpoint (intent-surface-unification W2):
 * the server routes plan-path turns (task-book build / refine / confirm) and
 * chat-loop turns itself.
 */

import { useCallback, useEffect, useMemo, useRef, useState, Fragment, forwardRef, useImperativeHandle } from "react"
import { useTranslation } from "react-i18next"
import {
  ArrowLeft,
  ArrowUp,
  Check,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  Crosshair,
  FileText,
  History,
  Image as ImageIcon,
  Images,
  Loader2,
  Mic2,
  Minus,
  Newspaper,
  Paperclip,
  Plus,
  Quote,
  Square,
  Undo2,
  Video,
  X,
} from "lucide-react"

import { apiFetch } from "@/lib/api"
import { inferAssetType } from "@/lib/asset-type"
import { streamChat } from "@/lib/chat-stream"
import { createTypewriter } from "@/lib/typewriter"
import { useReducedMotion } from "@/lib/use-reduced-motion"
import { useRunEvents } from "@/lib/use-run-events"
import { cn } from "@/lib/utils"
import {
  assetTypeKind,
  outputMentionLabel,
  type ChatMention,
  type MentionContext,
} from "@/lib/mentions"
import {
  MentionEditor,
  type MentionEditorHandle,
} from "@/components/mentions/MentionEditor"
import { Streamdown } from "streamdown"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Bubble, BubbleContent, BubbleGroup } from "@/components/ui/bubble"
import { Message, MessageContent } from "@/components/ui/message"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
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
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { RunCard } from "@/components/chat/RunCard"
import { QaPair, qaAnswerText, type QaAnswer } from "@/components/chat/QaPair"
import { QuestionDock, type Autonomy } from "@/components/chat/QuestionDock"
import type { IntentSlot, Output } from "@/lib/types"

const OUTPUT_OPTIONS = [
  { key: "clips", labelKey: "results.tabs.clips", Icon: Video },
  { key: "post", labelKey: "results.tabs.post", Icon: FileText },
  { key: "quotes", labelKey: "results.tabs.quotes", Icon: Quote },
  { key: "article", labelKey: "results.tabs.article", Icon: Newspaper },
  { key: "carousel", labelKey: "results.tabs.carousel", Icon: Images },
] as const

const LANGUAGE_OPTIONS = [
  { code: "en", labelKey: "languages.en" },
  { code: "zh", labelKey: "languages.zh" },
  { code: "fr", labelKey: "languages.fr" },
  { code: "de", labelKey: "languages.de" },
  { code: "es", labelKey: "languages.es" },
  { code: "it", labelKey: "languages.it" },
] as const

/** Per-type count bounds (mirrors the retired flat-field limits) and the
 * task-book defaults for `count: null` slots. */
const SLOT_COUNT_LIMITS: Record<string, [number, number]> = {
  clips: [1, 10],
  quotes: [1, 20],
  carousel: [2, 15],
}
const SLOT_COUNT_DEFAULT: Record<string, number> = {
  clips: 5,
  quotes: 3,
  carousel: 6,
}

type OutputKey = (typeof OUTPUT_OPTIONS)[number]["key"]
type Phase = "confirm" | "running" | "chat"

export interface InferredIntent {
  action: "generate" | "answer"
  answer: string | null
  outputs: IntentSlot[]
  /** 配音语言集 (dub_languages, RECIPES §4.1): task-book-level voice-dub
   * languages for the run's clips; empty = no dubbing. */
  dub_languages: string[]
  specific_instruction: string | null
}

function bareSlot(type: string, count: number | null = null): IntentSlot {
  return {
    type: type as IntentSlot["type"],
    count,
    focus: null,
    language: null,
    tone_override: null,
    explicit: false,
  }
}

/** Tolerate both task-book shapes: new slot objects pass through; legacy flat
 * run.context / pending_intent rows (string outputs + flat counts) upgrade to
 * bare slots — read tolerance only, never written back. */
export function normalizeSlots(
  raw: unknown,
  legacyClipCount?: number | null
): IntentSlot[] {
  if (!Array.isArray(raw)) return []
  const slots: IntentSlot[] = []
  for (const item of raw) {
    if (typeof item === "string") {
      if (OUTPUT_OPTIONS.some((o) => o.key === item)) {
        slots.push(bareSlot(item, item === "clips" ? (legacyClipCount ?? null) : null))
      }
    } else if (item && typeof item === "object" && typeof item.type === "string") {
      if (OUTPUT_OPTIONS.some((o) => o.key === item.type)) {
        slots.push({
          ...bareSlot(item.type),
          count: item.count ?? null,
          focus: item.focus ?? null,
          language: item.language ?? null,
          tone_override: item.tone_override ?? null,
          explicit: item.explicit ?? false,
        })
      }
    }
  }
  return slots
}

/** Normalize an intent payload of either shape (legacy flat or slot) into the
 * slot-shaped InferredIntent the panel edits. Language is a per-slot
 * property (2026-08-05 restructure — the book-level field is retired): slot
 * languages are MATERIALIZED here (null slot → the legacy book language, or
 * "en"), so every row's dropdown shows a concrete language — no sentinel. */
export function normalizeIntent(raw: unknown): InferredIntent {
  const data = (raw ?? {}) as Record<string, unknown>
  const fallbackLanguage =
    typeof data.language === "string" && data.language ? data.language : "en"
  return {
    action: data.action === "answer" ? "answer" : "generate",
    answer: (data.answer as string | null) ?? null,
    outputs: normalizeSlots(data.outputs, data.clip_count as number | null).map(
      (slot) => ({ ...slot, language: slot.language ?? fallbackLanguage })
    ),
    dub_languages: Array.isArray(data.dub_languages)
      ? data.dub_languages.filter((l): l is string => typeof l === "string" && !!l)
      : [],
    specific_instruction: (data.specific_instruction as string | null) ?? null,
  }
}

interface OverlayMessage {
  id: string
  role: "user" | "assistant"
  content: string
  runId?: string | null
  /** Files uploaded mid-conversation (the chat's attach button) — rendered
   * as attachment chips on the user bubble. */
  assets?: ProjectAsset[]
  /** Live SSE preview bubble: deltas append until the turn.completed
   * envelope replaces it (the envelope always wins). */
  streaming?: boolean
  /** QA archive item (answered question collapsing into the flow). */
  qa?: { question: string; answer: string; muted: boolean; detail?: string }
}

/** The typed question payload mirrored from the API (messages.question). */
interface QuestionPayload {
  kind: "task_book" | "choice" | "confirm"
  options?: { id: string; label: string }[]
  allow_freeform?: boolean
  estimate?: string | null
  /** task_book: needs-clarification reason KEYS (data — localize at render,
   * never baked into the question's prose). */
  reasons?: string[]
}

/** A question-carrying chat message (ask primitive): the dock's pending
 * question and, once answered, the QA archive of the decision. */
interface QuestionMessage {
  id: string
  content: string | null
  question: QuestionPayload | null
  answer: QaAnswer | null
  workflow_run_id: string | null
}

interface ProjectAsset {
  id: string
  type: string
  file_url: string | null
  title: string | null
  processing_status: "pending" | "processing" | "completed" | "failed"
}

/** A file staged in the input group, mid-lifecycle: picked → uploading
 * (direct-to-storage, same 3-step flow as the composer) → done (a real
 * project asset) / error (retry or remove). Nothing enters the flow until
 * the user presses send — the chips ride the next user bubble. */
interface StagedUpload {
  localId: string
  file: File
  status: "uploading" | "done" | "error"
  asset?: ProjectAsset
}

/** ChatAttachment wire type is narrower than asset types — slides and
 * transcripts travel as "file". */
function chatAttachmentType(assetType: string): "file" | "image" | "video" | "audio" {
  return assetType === "image" || assetType === "video" || assetType === "audio"
    ? assetType
    : "file"
}

function assetTypeIcon(type: string) {
  switch (type) {
    case "video":
      return Video
    case "audio":
      return Mic2
    case "image":
    case "slides":
      return ImageIcon
    default:
      return FileText
  }
}

function assetFilename(fileUrl: string | null): string {
  if (!fileUrl) return ""
  return fileUrl.split("/").pop() || fileUrl
}

/** Localize a task_book question's reason keys for the QA archive's detail
 * line (payload data → display; the keys themselves are the agent's
 * vocabulary, never user-facing). */
function qaReasonsDetail(
  question: QuestionPayload | null | undefined,
  t: (key: string, opts?: Record<string, unknown>) => string
): string | undefined {
  const reasons = question?.reasons ?? []
  if (reasons.length === 0) return undefined
  const items = reasons.map((r) =>
    t(`questionDock.reasons.${r}`, { defaultValue: r })
  )
  return `${t("questionDock.reasons.title")} ${items.join(" · ")}`
}

interface GenerationOverlayProps {
  projectId: string
  prompt: string
  /** The composer's draft, handed over via router state: sent as the first
   * /chat message on mount (mentions + persona choice ride along). Null on
   * restored sessions — the conversation is already on the server. */
  firstMessage?: {
    text: string
    mentions: { type: string; id: string; label: string }[]
    personaId?: string
  } | null
  initialIntent?: InferredIntent | null
  initialNeedsClarification?: boolean
  /** needs_clarification reason keys from the last inference — the dock
   * shows them as the "needs your check" line (回显). */
  initialReasons?: string[]
  /** Attach to an already-running generation (returning visitor): skips the
   * confirm phase, lands straight on the step flow. */
  initialRunId?: string | null
  /** The shell at mount (ADR-041 D4): "fullscreen" = the planning/progress
   * surface; "dock" = the results-phase bottom dock over the canvas. The
   * SAME message machine — only the outer shell differs. */
  initialShell?: "fullscreen" | "dock"
  /** The canvas's focused product (ADR-041 D8 焦点注入): shown as a chip
   * above the input and carried on each turn as `focus_output_id` — one
   * context line server-side, never a second intent entry. */
  focusOutput?: { id: string; label: string } | null
  onClearFocus?: () => void
  /** Where a witnessed completion lands (ADR-041 D3): "dock" = the desktop
   * 收官转场 (fullscreen → dock); "navigate" = the mobile legacy hand-off
   * (the page navigates back to the results list). */
  completionMode?: "dock" | "navigate"
  onClose: () => void
  /** The run reached a terminal-success state while this overlay was
   * watching. Awaited on the dock-capable path: the page refetches and
   * mounts the (choreographed) canvas BEFORE the collapse starts. */
  onComplete: (runId: string | null) => void | Promise<void>
}

/** Dock controls the page can trigger (D4: 点画布收回 — a canvas pointer
 * down collapses the history drawer back to the summary card). */
export interface GenerationOverlayHandle {
  collapseDrawer: () => void
  /** Insert an @-mention chip into the input (results canvas node clicks —
   * the @workflow_step 本面限定候选源, ADR-041 D8). No-op when the editor
   * isn't mounted. */
  insertMention: (mention: ChatMention) => void
}

function StepMarker({
  status,
  label,
  error,
}: {
  status: string
  label: string
  error?: string | null
}) {
  const icon =
    status === "running" ? (
      <Loader2 className="animate-spin text-primary" />
    ) : status === "done" ? (
      <Check className="text-green-600 dark:text-green-400" />
    ) : status === "failed" ? (
      <X className="text-destructive" />
    ) : status === "waiting" ? (
      // Checkpoint parked for a human answer (期 4) — a question, not work.
      <CircleHelp className="text-primary" />
    ) : (
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50" />
    )

  return (
    <Marker>
      <MarkerIcon>{icon}</MarkerIcon>
      <MarkerContent className={status === "running" ? "shimmer" : undefined}>
        {label}
        {status === "failed" && error ? ` — ${error}` : ""}
      </MarkerContent>
    </Marker>
  )
}

/** User message — the only bubbled element in the flow (rounded, muted).
 * The opening prompt carries the project's source materials as attachments;
 * an attachment-only message (files dropped into the chat) skips the text
 * bubble and shows just the chips. */
function UserBubble({ text, assets }: { text: string; assets?: ProjectAsset[] }) {
  const { t } = useTranslation()
  return (
    <Message align="end">
      <MessageContent>
        {text ? (
          <BubbleGroup>
            <Bubble variant="muted" align="end">
              <BubbleContent className="rounded-2xl px-4 py-2.5 text-sm">
                <p className="whitespace-pre-wrap">{text}</p>
              </BubbleContent>
            </Bubble>
          </BubbleGroup>
        ) : null}
        {assets && assets.length > 0 ? (
          <AttachmentGroup className="justify-end">
            {assets.map((asset) => {
              const Icon = assetTypeIcon(asset.type)
              const typeLabel = t(`generationOverlay.assetTypes.${asset.type}`, {
                defaultValue: asset.type,
              })
              return (
                <Attachment
                  key={asset.id}
                  size="sm"
                  // An archived message is a historical record — it never
                  // animates. Live processing/uploading states (which make
                  // AttachmentTitle shimmer) belong to the composer, not the
                  // flow; only a genuine failure stays visible, statically.
                  state={asset.processing_status === "failed" ? "error" : "done"}
                >
                  <AttachmentMedia>
                    <Icon />
                  </AttachmentMedia>
                  <AttachmentContent>
                    <AttachmentTitle>
                      {asset.title || assetFilename(asset.file_url) || typeLabel}
                    </AttachmentTitle>
                    <AttachmentDescription>{typeLabel}</AttachmentDescription>
                  </AttachmentContent>
                </Attachment>
              )
            })}
          </AttachmentGroup>
        ) : null}
      </MessageContent>
    </Message>
  )
}

/** Assistant prose — markdown, no bubble (Opus pattern). Streamdown parses
 * incomplete markdown safely mid-stream, so the live preview and the settled
 * message share one renderer. */
function AssistantText({ text, streaming }: { text: string; streaming?: boolean }) {
  return (
    <Message align="start">
      <MessageContent>
        <Streamdown
          mode={streaming ? "streaming" : "static"}
          isAnimating={streaming}
          className="text-sm leading-relaxed motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-300"
        >
          {text}
        </Streamdown>
      </MessageContent>
    </Message>
  )
}

function ThinkingRow({ label }: { label: string }) {
  return (
    <Message align="start">
      <MessageContent>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          {/* Same text shimmer the running step markers use. */}
          <span className="shimmer">{label}</span>
        </div>
      </MessageContent>
    </Message>
  )
}

/** A superseded plan version in the flow: one slim chip row that expands
 * into a read-only snapshot with a restore action. The live book is always
 * the bottom-most card; these chips are its history (2026-08-05 ruling —
 * chat edits the plan, nothing is locked, old versions stay visible). */
function PlanVersionChip({
  n,
  book,
  summary,
  expanded,
  onToggle,
  onRestore,
  slotLabel,
}: {
  n: number
  book: InferredIntent
  summary: string
  expanded: boolean
  onToggle: () => void
  onRestore: () => void
  slotLabel: (slot: IntentSlot) => string
}) {
  const { t } = useTranslation()
  return (
    <Message align="start">
      <MessageContent>
        <div className="w-full">
          <button
            type="button"
            onClick={onToggle}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
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
                {book.outputs.map((slot, i) => {
                  const meta = OUTPUT_OPTIONS.find((o) => o.key === slot.type)
                  if (!meta) return null
                  return (
                    <div key={i} className="flex items-center gap-1.5 text-xs">
                      <meta.Icon className="h-3.5 w-3.5 text-muted-foreground" />
                      <span>{slotLabel(slot)}</span>
                    </div>
                  )
                })}
                {book.dub_languages.length > 0 && (
                  <div className="flex items-center gap-1.5 text-xs">
                    <Mic2 className="h-3.5 w-3.5 text-muted-foreground" />
                    <span>
                      {t("generationOverlay.planSummaryDub", {
                        langs: book.dub_languages
                          .map((l) => t(`languages.${l}`, { defaultValue: l }))
                          .join(", "),
                      })}
                    </span>
                  </div>
                )}
                {book.specific_instruction ? (
                  <p className="line-clamp-2 text-xs text-muted-foreground">
                    {book.specific_instruction}
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

export const GenerationOverlay = forwardRef<GenerationOverlayHandle, GenerationOverlayProps>(function GenerationOverlay({
  projectId,
  prompt,
  firstMessage,
  initialIntent,
  initialNeedsClarification = true,
  initialReasons,
  initialRunId,
  initialShell = "fullscreen",
  focusOutput = null,
  onClearFocus,
  completionMode = "navigate",
  onClose,
  onComplete,
}, ref) {
  const { t } = useTranslation()

  // Shell state machine (ADR-041 D3/D4): fullscreen (planning / progress) →
  // collapsing (收官转场: backdrop fades + the message area retracts upward,
  // the input group never moves) → dock (results-phase bottom dock over the
  // canvas). Mount-time shell comes from the page's run data; the only
  // post-mount transition is the witnessed completion below.
  type Shell = "fullscreen" | "collapsing" | "dock"
  const [shell, setShell] = useState<Shell>(
    initialShell === "dock" ? "dock" : "fullscreen"
  )
  /** Dock view: summary = input group + latest agent message card (default);
   * drawer = full history展开; collapsed = slim history pill only. Agent
   * speech always forces the summary back up (prohibition #6). */
  const [dockView, setDockView] = useState<"summary" | "drawer" | "collapsed">(
    "summary"
  )
  const reducedMotion = useReducedMotion()
  useImperativeHandle(ref, () => ({
    collapseDrawer: () =>
      setDockView((v) => (v === "drawer" ? "summary" : v)),
    insertMention: (mention: ChatMention) =>
      editorRef.current?.insertMention(mention),
  }))

  const [phase, setPhase] = useState<Phase>(
    initialRunId ? "running" : initialIntent ? "confirm" : "chat"
  )
  const [intent, setIntent] = useState<InferredIntent>(() =>
    initialIntent
      ? normalizeIntent(initialIntent)
      : {
          action: "generate",
          answer: null,
          outputs: ["post", "quotes", "article"].map((type) => ({
            ...bareSlot(type),
            language: "en",
          })),
          dub_languages: [],
          specific_instruction: prompt,
        }
  )
  // The plan card renders only once a real inference has landed (a restored
  // session hands one over; a fresh navigation gets it from the first /chat
  // turn's refetch). Attach mode never shows the card, so it starts ready.
  const [intentReady, setIntentReady] = useState(!!initialIntent || !!initialRunId)
  const [runId, setRunId] = useState<string | null>(initialRunId ?? null)
  // Mirrored in a ref: async chat continuations capture stale closures, and
  // they must be able to tell a run went live while their turn was in flight.
  const runIdRef = useRef<string | null>(initialRunId ?? null)
  useEffect(() => {
    runIdRef.current = runId
  }, [runId])
  const [isStarting, setIsStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  // Ask primitive: the pending question docks above the input (task_book in
  // the confirm phase; choice questions from the chat loop afterwards); the
  // answered one archives as a QA pair in the flow.
  const [pendingQuestion, setPendingQuestion] = useState<QuestionMessage | null>(null)
  const [questionLoaded, setQuestionLoaded] = useState(false)
  const [answeredQuestion, setAnsweredQuestion] = useState<QuestionMessage | null>(null)
  // Autonomy tier: the picker is hidden (QuestionDock.SHOW_AUTONOMY_PICKER),
  // so every run goes out at the review tier — the direction checkpoint
  // parks mid-run for the user's pick. The state stays so re-exposing the
  // picker is a one-flag flip.
  const [autonomy, setAutonomy] = useState<Autonomy>("review")
  const [answering, setAnswering] = useState(false)
  const [reasons, setReasons] = useState<string[]>(initialReasons ?? [])

  // Conversation below the pinned regions (plan card / progress).
  const [messages, setMessages] = useState<OverlayMessage[]>([])
  const [input, setInput] = useState("")
  const [mentions, setMentions] = useState<ChatMention[]>([])
  const [chatBusy, setChatBusy] = useState(false)
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
  // rework): the LIVE book renders as the bottom-most card while settled;
  // during an in-flight turn it UNPINS — anchored inline right after the
  // echo bubble that docked it (above the new user bubble + thinking row),
  // so the stale confirm dock can hide and the flow reads chronologically.
  // When the turn lands, the superseded book collapses into a version chip
  // at that same anchor (expandable read-only snapshot, restorable — chat
  // edits the plan, nothing is locked) and the fresh card pins bottom.
  // liveBookMessageId = the echo bubble of the turn that docked the current
  // book; null on restored sessions (no bubble exists → the card carries its
  // own echo line and stays pinned).
  const [liveBookMessageId, setLiveBookMessageId] = useState<string | null>(null)
  const [planVersions, setPlanVersions] = useState<
    { messageId: string; book: InferredIntent }[]
  >([])
  const [expandedVersion, setExpandedVersion] = useState<number | null>(null)
  // The demotion snapshot must capture the book as it stands AT DOCK TIME
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
  // Identity echo line (the persona's name — style + skin ride it, ADR-038)
  // — resolved once.
  const [identityPersona, setIdentityPersona] = useState<string | null>(null)

  const autoStartedRef = useRef(false)
  const autoStartArmedRef = useRef(false)
  const firstMessageSentRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  const { steps, status, terminal, summary } = useRunEvents(runId)
  // Ref mirror: sendChat's async continuation must read the live terminal
  // state, not a stale closure.
  const terminalRef = useRef(terminal)
  useEffect(() => {
    terminalRef.current = terminal
  }, [terminal])
  // Dock-summary priority: the run's terminal aggregate is the收官摘要
  // until a chat turn lands AFTER it (set in sendChat, reset on each fresh
  // terminal) — the newer agent line always wins.
  const postTerminalReplyRef = useRef(false)

  // The pending question is a plain DB row — fetching the project
  // conversation rebuilds the dock after refresh / on any device, whatever
  // the phase (task_book while confirming, choice once the chat loop asks).
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

  /** The panel's task book + reasons live on the project (pending_intent) —
   * refetched after every plan-path turn (first inference, refinements). */
  const fetchPendingIntent = useCallback(async (): Promise<{
    intent: unknown
    reasons?: string[]
    persona_id?: string | null
  } | null> => {
    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/results`, {
        toast: false,
      })
      if (!res.ok) return null
      const data = (await res.json()) as { pending_intent?: {
        intent: unknown
        reasons?: string[]
        persona_id?: string | null
      } | null }
      return data.pending_intent ?? null
    } catch {
      return null
    }
  }, [projectId])

  useEffect(() => {
    let cancelled = false
    fetchPendingQuestion().then((q) => {
      if (!cancelled) {
        setPendingQuestion(q)
        setQuestionLoaded(true)
      }
    })
    return () => {
      cancelled = true
    }
  }, [fetchPendingQuestion])

  // Confirm-phase archive replay (B1): the conversation's message rows are
  // the durable record — on open, rebuild the flow from them so a refresh or
  // another device no longer loses capability answers / past refinements.
  // The opening prompt renders from the prop (it carries the attachments),
  // so its seeded row is skipped; a still-pending question docks above the
  // input, never in the flow. Best-effort: the live flow works without it.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const convRes = await apiFetch(`/api/v1/chat/conversation?project_id=${projectId}`, {
          toast: false,
        })
        if (!convRes.ok) return
        const conv = (await convRes.json()) as { id?: string }
        if (!conv.id) return
        const res = await apiFetch(`/api/v1/chat/conversations/${conv.id}/messages`, {
          toast: false,
        })
        if (!res.ok) return
        const data = (await res.json()) as {
          items?: (QuestionMessage & {
            role: "user" | "assistant"
            attachments?: {
              id: string
              name: string
              type: string
              url?: string | null
            }[]
          })[]
        }
        const history: OverlayMessage[] = []
        for (const m of data.items ?? []) {
          if (m.role === "user") {
            if ((m.content ?? "") === prompt) continue
            history.push({
              id: m.id,
              role: "user",
              content: m.content ?? "",
              // Sent attachments persist on the message row — re-render the
              // chips so a refresh / another device keeps the record.
              assets: (m.attachments ?? []).map((a) => ({
                id: a.id,
                type: a.type,
                file_url: a.url ?? null,
                title: a.name,
                processing_status: "completed" as const,
              })),
            })
          } else if (m.question) {
            if (m.answer) {
              const display = qaAnswerText(m.answer, t, !!m.workflow_run_id)
              history.push({
                id: m.id,
                role: "assistant",
                content: "",
                qa: {
                  question: m.content ?? "",
                  answer: display.text,
                  muted: display.muted,
                  detail: qaReasonsDetail(m.question, t),
                },
              })
            }
          } else {
            history.push({
              id: m.id,
              role: "assistant",
              content: m.content ?? "",
              runId: m.workflow_run_id,
            })
          }
        }
        // Prepend — anything pushed locally since mount is newer.
        if (!cancelled && history.length > 0) {
          setMessages((prev) => [...history, ...prev])
        }
      } catch {
        /* the archive replay is best-effort */
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  // Mid-run dock revival (期 4): the direction checkpoint docks its question
  // while the run is already streaming — when a waiting checkpoint step
  // appears in the SSE flow, re-fetch the pending question so it docks
  // above the input. A null fetch result keeps the dock empty (already
  // answered elsewhere), and the step leaving waiting ends the watch.
  useEffect(() => {
    if (pendingQuestion) return
    if (!steps.some((s) => s.kind === "checkpoint" && s.status === "waiting")) return
    let cancelled = false
    fetchPendingQuestion().then((q) => {
      if (!cancelled && q) setPendingQuestion(q)
    })
    return () => {
      cancelled = true
    }
  }, [steps, pendingQuestion, fetchPendingQuestion])

  // Stale-dock clear: the server can settle the docked checkpoint question
  // without a client action — the expiry sweep's auto-answer, or an answer
  // from another device. When this run's checkpoint step leaves waiting,
  // re-fetch and drop the dock if nothing is pending anymore.
  useEffect(() => {
    if (!pendingQuestion || pendingQuestion.workflow_run_id !== runId) return
    if (steps.some((s) => s.kind === "checkpoint" && s.status === "waiting")) return
    let cancelled = false
    fetchPendingQuestion().then((q) => {
      if (!cancelled && !q) setPendingQuestion(null)
    })
    return () => {
      cancelled = true
    }
  }, [steps, pendingQuestion, runId, fetchPendingQuestion])

  // Load the project's assets for the prompt attachments — once on mount,
  // and again after a chat turn when the project started empty: the plan
  // path promotes user-declared pasted text ("this is my transcript: …")
  // into a real transcript asset mid-turn, and it must show up.
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

  // The output mention's candidate feed (reference family, MENTIONS §2): a
  // pinned output id resolves the revision target deterministically
  // server-side. Refresh on mount and when a run lands terminal (new
  // outputs exist only then).
  const [outputs, setOutputs] = useState<Output[]>([])
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

  // Registry feeds handed to the editor's picker (memoized — the picker
  // reloads when the identity changes).
  const mentionContext = useMemo<MentionContext>(
    () => ({
      assets: assets
        .filter((a) => a.title)
        .map((a) => ({
          name: a.title as string,
          kind: assetTypeKind(a.type),
        })),
      outputs: outputs.map((o) => ({
        id: o.id,
        label: outputMentionLabel(o, t(`chat.derivativeTypes.${o.type}`)),
        kind: o.type,
      })),
    }),
    [assets, outputs, t],
  )

  // Identity echo: resolve the persona name behind the project mount once —
  // a read-only reassurance line, never a question (ask primitive §2.1).
  useEffect(() => {
    let cancelled = false
    Promise.all([
      apiFetch(`/api/v1/projects/${projectId}`, { toast: false })
        .then((res) => (res.ok ? res.json() : null))
        .catch(() => null),
      apiFetch("/api/v1/personas", { toast: false })
        .then((res) => (res.ok ? res.json() : []))
        .catch(() => []),
    ]).then(([project, personas]) => {
      if (cancelled) return
      setIdentityPersona(
        (personas as { id: string; name: string }[]).find(
          (p) => p.id === (project as { persona_id?: string } | null)?.persona_id
        )?.name ?? null
      )
    })
    return () => {
      cancelled = true
    }
  }, [projectId])

  // Witnessed-run tracking (declared BEFORE the terminal effect so a single
  // SSE commit settles it first): only a run seen live (pending/running)
  // may play the收官转场. A historical run arrives terminal in the first
  // snapshot — straight to the dock, never a replay (prohibition #5).
  const seenLiveRef = useRef(false)
  useEffect(() => {
    if (status === "pending" || status === "running") seenLiveRef.current = true
  }, [status])

  // Terminal: failure stays put so the step list shows what broke; success
  // either plays the collapse into the dock (desktop, witnessed) or keeps
  // the legacy hand-off (mobile navigates back to the results list).
  useEffect(() => {
    if (!terminal) return
    if (status === "failed") {
      toast.error(t("generationOverlay.failed"))
      return
    }
    if (!seenLiveRef.current) {
      // Rehydrated history (refresh / direct entry / another device): the
      // dock appears instantly — no toast, no replay.
      if (completionMode === "dock") setShell("dock")
      return
    }
    if (completionMode === "navigate") {
      toast.success(t("generationOverlay.completed"))
      onCompleteRef.current(runIdRef.current)
      return
    }
    void (async () => {
      // A fresh terminal resets the dock-summary priority: the new run's
      // aggregate is the latest agent line until a chat reply supersedes it.
      postTerminalReplyRef.current = false
      // The page refetches + mounts the choreographed canvas underneath
      // BEFORE the shell starts collapsing — the graph's birth replay and
      // the backdrop fade overlap (D3).
      await onCompleteRef.current(runIdRef.current)
      // Only a fullscreen shell plays the collapse — a dock watching a
      // refinement run finish just refreshes its summary in place.
      if (shell !== "fullscreen") return
      if (reducedMotion) {
        setShell("dock")
        return
      }
      setShell("collapsing")
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [terminal])

  // The collapse is one CSS beat (backdrop fade + message-area retract,
  // duration-500); then the dock takes over the bottom row.
  useEffect(() => {
    if (shell !== "collapsing") return
    const timer = setTimeout(() => setShell("dock"), 560)
    return () => clearTimeout(timer)
  }, [shell])

  // Entering the dock always lands on the summary view — the收官摘要 (or
  // the latest agent line) is the raised default (D4).
  useEffect(() => {
    if (shell === "dock") setDockView("summary")
  }, [shell])

  /** Shared landing for every path that starts a run (the dock's Start
   * button, a prose confirmation via /chat): the answered task book
   * archives as QA, the dock clears, and the step flow takes over. */
  const landOnStartedRun = useCallback((runId: string, answered: QuestionMessage | null) => {
    setPendingQuestion(null)
    if (answered) setAnsweredQuestion(answered)
    setRunId(runId)
    setPhase("running")
  }, [])

  const handleStartGeneration = useCallback(async () => {
    // runId && !terminal: a run is LIVE — starting now would double-launch.
    // (A terminal run does NOT block: the dock's refinement Start launches
    // the next run — runId set ≠ run live.) chatBusy: a refine turn is in
    // flight — starting now would race its response (the late task book
    // could re-dock over the running flow).
    if ((runId && !terminal) || isStarting || chatBusy) return
    setStartError(null)
    setIsStarting(true)
    try {
      if (pendingQuestion) {
        // Ask primitive: Start IS the answer to the docked task_book
        // question — one call answers, starts the run, and archives the QA.
        // "start" is a first-class answer kind (no magic option id); the
        // panel's edited task book rides along so hand edits (slots marked
        // explicit) reach the run instead of the stale stored intent.
        const res = await apiFetch(
          `/api/v1/chat/messages/${pendingQuestion.id}/answer`,
          {
            method: "POST",
            body: { kind: "start", autonomy, intent },
          },
        )
        if (!res.ok) {
          const detail = await res.json().catch(() => ({}))
          throw new Error(detail.detail || "Generation failed")
        }
        const answered = ((await res.json()) as { answered_question: QuestionMessage }).answered_question
        if (!answered.workflow_run_id) throw new Error("Generation failed")
        landOnStartedRun(answered.workflow_run_id, answered)
        return
      }
      // Legacy fallback: no question row (pre-dock projects) — /generate
      // settles the open question server-side the same way.
      const res = await apiFetch(`/api/v1/projects/${projectId}/generate`, {
        method: "POST",
        body: {
          slots: intent.outputs,
          target_language:
            intent.outputs.find((s) => s.language)?.language ?? "en",
          dub_languages: intent.dub_languages,
          instruction: intent.specific_instruction || prompt,
          autonomy,
        },
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail.detail || "Generation failed")
      }
      const data = (await res.json()) as { run_id: string }
      setRunId(data.run_id)
      setPhase("running")
    } catch (e) {
      setStartError(e instanceof Error ? e.message : t("generationOverlay.failed"))
      setIsStarting(false)
    }
  }, [runId, terminal, isStarting, chatBusy, pendingQuestion, autonomy, intent, projectId, prompt, t, landOnStartedRun])

  /** Cancel = bail: a graceful exit back to draft (never an error toast). */
  const handleCancel = useCallback(async () => {
    if (pendingQuestion) {
      await apiFetch(`/api/v1/chat/messages/${pendingQuestion.id}/answer`, {
        method: "POST",
        body: { kind: "bail" },
        toast: false,
      }).catch(() => {})
    }
    onClose()
  }, [pendingQuestion, onClose])

  useEffect(() => {
    if (
      initialIntent &&
      !initialRunId &&
      initialIntent.action === "generate" &&
      !initialNeedsClarification &&
      phase === "confirm" &&
      questionLoaded &&
      !autoStartedRef.current
    ) {
      autoStartedRef.current = true
      handleStartGeneration()
    }
  }, [initialIntent, initialRunId, initialNeedsClarification, phase, questionLoaded, handleStartGeneration])

  const canStartGeneration = intent.outputs.length > 0

  // The clips slot backing the voice-over multiplication line (null → the
  // 422-escape state; the dock's warning carries that case instead).
  const clipsSlotForDub = intent.outputs.find((s) => s.type === "clips") ?? null

  // Slot edits — every hand edit marks the slot explicit so it pins through
  // the next re-inference (pin-merge rule).
  const updateSlot = (index: number, patch: Partial<IntentSlot>) =>
    setIntent((prev) => ({
      ...prev,
      outputs: prev.outputs.map((s, i) =>
        i === index ? { ...s, ...patch, explicit: true } : s
      ),
    }))

  const addSlot = (type: OutputKey) =>
    setIntent((prev) => ({
      ...prev,
      outputs: [
        ...prev.outputs,
        {
          ...bareSlot(type),
          // A hand-added row starts from the plan's prevailing language —
          // the dropdown always shows a concrete value (no sentinel).
          language: prev.outputs.find((s) => s.language)?.language ?? "en",
          explicit: true,
        },
      ],
    }))

  const removeSlot = (index: number) =>
    setIntent((prev) => ({
      ...prev,
      outputs: prev.outputs.filter((_, i) => i !== index),
    }))

  const slotLabel = useCallback(
    (slot: IntentSlot) => {
      let label = t(`results.tabs.${slot.type}`, { defaultValue: slot.type })
      if (slot.language) {
        label += ` (${t(`languages.${slot.language}`, { defaultValue: slot.language })})`
      }
      if (slot.count) label += ` ×${slot.count}`
      return label
    },
    [t]
  )

  const summarizeBook = useCallback(
    (book: InferredIntent) => {
      const parts = [book.outputs.map(slotLabel).join(", ")]
      if (book.dub_languages.length > 0) {
        parts.push(
          t("generationOverlay.planSummaryDub", {
            langs: book.dub_languages
              .map((l) => t(`languages.${l}`, { defaultValue: l }))
              .join(", "),
          })
        )
      }
      return parts.join(" · ")
    },
    [slotLabel, t]
  )

  const planSummary = useMemo(() => summarizeBook(intent), [intent, summarizeBook])

  /** Assets carried by a message bubble must not also hang under the opening
   * prompt (a mid-conversation upload refreshed into `assets` would render
   * twice — the 2026-08-05 duplication bug). Server-promoted assets (the
   * declared-material transcript) have no bubble, so they still surface. */
  const openingAssets = useMemo(() => {
    const carried = new Set(
      messages.flatMap((m) => (m.assets ?? []).map((a) => a.id))
    )
    return assets.filter((a) => !carried.has(a.id))
  }, [assets, messages])

  /** True when the echo bubble of the turn that docked the current book is
   * in the flow — the card's own echo line then stays hidden. */
  const liveBubblePresent =
    liveBookMessageId !== null &&
    messages.some((m) => m.id === liveBookMessageId)

  /** Restore a superseded version as the current plan — the chip's snapshot
   * becomes the panel's book (it rides the next refine as prior_intent, and
   * Start uses it directly). Nothing is locked; older versions stay in the
   * flow as chips. */
  const restoreVersion = (index: number) => {
    const version = planVersions[index]
    if (!version) return
    setIntent(version.book)
    setExpandedVersion(null)
    toast.success(
      t("generationOverlay.versionRestored", { n: index + 1 })
    )
  }

  const pushMessage = (message: Omit<OverlayMessage, "id">) => {
    setMessages((prev) => [...prev, { ...message, id: crypto.randomUUID() }])
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
      const putRes = await fetch(upload_url, {
        method: "PUT",
        body: material,
        headers: material.type ? { "Content-Type": material.type } : {},
      })
      if (!putRes.ok) throw new Error("Failed to upload file")
      const assetRes = await apiFetch(`/api/v1/projects/${projectId}/assets`, {
        method: "POST",
        body: { type: inferAssetType(material), key, title: material.name },
        toast: false,
      })
      if (!assetRes.ok) throw new Error("Failed to create asset")
      const asset = (await assetRes.json()) as ProjectAsset
      setStaged((prev) =>
        prev.map((s) =>
          s.localId === localId ? { ...s, status: "done", asset } : s
        )
      )
    } catch {
      setStaged((prev) =>
        prev.map((s) => (s.localId === localId ? { ...s, status: "error" } : s))
      )
    }
  }

  const handleFilesPicked = (picked: FileList | null) => {
    const files = Array.from(picked ?? [])
    if (fileInputRef.current) fileInputRef.current.value = ""
    if (files.length === 0) return
    const additions: StagedUpload[] = files.map((file) => ({
      localId: crypto.randomUUID(),
      file,
      status: "uploading",
    }))
    setStaged((prev) => [...prev, ...additions])
    for (const s of additions) void uploadStaged(s.localId, s.file)
  }

  /** A staged chip's × : drop it from the input group; an already-created
   * asset is deleted server-side too (staged ≠ sent — it must not linger as
   * project material). */
  const removeStaged = (item: StagedUpload) => {
    setStaged((prev) => prev.filter((s) => s.localId !== item.localId))
    if (item.asset) {
      void apiFetch(`/api/v1/projects/${projectId}/assets/${item.asset.id}`, {
        method: "DELETE",
        toast: false,
      }).catch(() => {})
    }
  }

  const retryStaged = (item: StagedUpload) => {
    setStaged((prev) =>
      prev.map((s) =>
        s.localId === item.localId ? { ...s, status: "uploading" } : s
      )
    )
    void uploadStaged(item.localId, item.file)
  }

  /** An answered question collapses into the flow as a QA pair (ask
   * primitive: the flow archives decisions, the dock holds the open one).
   * Reason keys (payload data) render localized as the pair's detail line. */
  const pushQaArchive = (message: QuestionMessage) => {
    if (!message.answer) return
    const display = qaAnswerText(message.answer, t, !!message.workflow_run_id)
    pushMessage({
      role: "assistant",
      content: "",
      qa: {
        question: message.content ?? "",
        answer: display.text,
        muted: display.muted,
        detail: qaReasonsDetail(message.question, t),
      },
    })
  }

  /** The chat loop's reply: a pending question docks (never enters the
   * flow, prohibited-behavior #2); anything else renders as prose + an
   * optional RunCard. A docked task book also refetches the panel's plan —
   * and arms the fresh-flow auto-start when the first inference lands with
   * nothing to clarify. */
  const handleAssistantMessage = async (message: QuestionMessage) => {
    if (message.question && !message.answer) {
      if (
        message.question.kind === "task_book" &&
        runIdRef.current &&
        !terminalRef.current
      ) {
        // A run is already LIVE (started from another surface while this
        // turn was in flight) — a late task book must not pull the UI back
        // to confirm; the run flow owns the surface now. (A TERMINAL run
        // does not trigger this guard: the dock's refinement books dock
        // normally — runId set ≠ run live.)
        return
      }
      setPendingQuestion(message)
      if (message.question.kind === "task_book") {
        const pending = await fetchPendingIntent()
        if (pending) {
          setIntent(normalizeIntent(pending.intent))
          setReasons(pending.reasons ?? [])
          setIntentReady(true)
          setPhase("confirm")
          // No "plan updated" filler line on refinements — the turn's own
          // streamed echo bubble already says what changed.
          if (!intentReady && (pending.reasons ?? []).length === 0) {
            autoStartArmedRef.current = true
          }
        }
      }
      return
    }
    pushMessage({
      role: "assistant",
      content: message.content ?? "",
      runId: message.workflow_run_id,
    })
  }

  /** One endpoint for every turn (intent-surface-unification W2): the server
   * routes plan-path turns (task-book build / refine / confirm) and
   * chat-loop turns itself. The panel's current book rides confirm-phase
   * turns as prior_intent (its explicit slots pin through the merge);
   * mentions / the persona choice ride only the composer's first message.
   *
   * Transport is SSE (streamChat): prose deltas feed a typewriter-paced
   * preview bubble (reasoning models emit a short echo in one burst — pacing
   * keeps the "written live" feel); the terminal turn.completed envelope is
   * authoritative and FINALIZES THE PREVIEW IN PLACE — same React key, no
   * remount — so a docking task book never makes the text flicker. */
  const sendChat = async (
    text: string,
    opts?: {
      mentions?: { type: string; id: string; label: string }[]
      personaId?: string
      /** Files staged in the input group, sent with this turn — persisted on
       * the user message row so a refresh re-renders the chips. */
      attachments?: {
        id: string
        name: string
        type: "file" | "image" | "video" | "audio"
        url?: string
        size?: number
        status: "uploaded"
      }[]
      /** Failure handling for a user-typed turn: roll the optimistic bubble
       * back out of the flow and restore the draft (the server commits
       * nothing on a failed turn, so the flow must not keep it either). */
      rollbackId?: string
      draft?: string
      /** The turn's mention chips return with the draft on failure. */
      rollbackMentions?: ChatMention[]
      /** Consumed attachment chips return to the input group on failure. */
      rollbackStaged?: StagedUpload[]
    }
  ) => {
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setChatBusy(true)
    const streamId = crypto.randomUUID()
    let streamedAny = false
    const appendDelta = (delta: string) => {
      streamedAny = true
      setMessages((prev) =>
        prev.some((m) => m.id === streamId)
          ? prev.map((m) =>
              m.id === streamId ? { ...m, content: m.content + delta } : m
            )
          : [
              ...prev,
              { id: streamId, role: "assistant", content: delta, streaming: true },
            ]
      )
    }
    const typewriter = createTypewriter(appendDelta)
    /** In-place finalize: the preview bubble becomes the settled message
     * under the SAME key (the envelope's content wins); never a remount. */
    const finalizePreview = (content?: string, runId?: string | null) =>
      setMessages((prev) =>
        prev.map((m) =>
          m.id === streamId
            ? {
                ...m,
                content: content ?? m.content,
                runId: runId === undefined ? m.runId : runId,
                streaming: false,
              }
            : m
        )
      )
    try {
      const data = await streamChat<{
        assistant_message: QuestionMessage
        run_id: string | null
        answered_question?: QuestionMessage | null
      }>(
        {
          project_id: projectId,
          message: text,
          mentions: opts?.mentions ?? [],
          attachments: opts?.attachments ?? [],
          focus_output_id: focusOutput?.id,
          persona_id: opts?.personaId,
          prior_intent: phase === "confirm" && intentReady ? intent : undefined,
          // Consumed only when this turn confirms the book by prose — the
          // dock's tier must survive a typed "looks good, start it".
          autonomy: phase === "confirm" ? autonomy : undefined,
        },
        {
          signal: ctrl.signal,
          onDelta: (delta) => typewriter.push(delta),
        }
      )
      // Envelope wins: release any buffered prose, then land the turn.
      typewriter.flush()
      // A reply landing after the run's terminal supersedes the收官摘要 in
      // the dock summary (it is the newer agent line).
      if (terminalRef.current) postTerminalReplyRef.current = true
      // A turn can create assets server-side (declared-material promotion) —
      // refresh the prompt attachments when the project started empty.
      if (assets.length === 0) void fetchAssets()
      if (data.run_id) {
        // G-1: the prose confirmation answered the docked task book
        // server-side (kind=start) and the run is live — the same landing
        // as the dock's Start button.
        finalizePreview()
        landOnStartedRun(data.run_id, data.answered_question ?? null)
        return
      }
      // Deterministic autoResume settled the docked question with this very
      // text — archive its QA pair before the assistant's continuation.
      if (data.answered_question) {
        setPendingQuestion(null)
        pushQaArchive(data.answered_question)
      }
      const message = data.assistant_message
      if (message.question && !message.answer) {
        // A question docks (never enters the flow). The streamed echo bubble
        // STAYS in place (same key — never a remount); the superseded book
        // collapses into a version chip anchored after the echo bubble that
        // produced it — the same anchor the inline card occupied while the
        // turn was in flight — and the fresh card pins bottom-most.
        if (streamedAny) {
          finalizePreview()
          if (message.question.kind === "task_book") {
            if (intentReady && liveBookMessageId) {
              setPlanVersions((prev) => [
                ...prev,
                { messageId: liveBookMessageId, book: intentRef.current },
              ])
            }
            setLiveBookMessageId(streamId)
          }
        } else {
          setMessages((prev) => prev.filter((m) => m.id !== streamId))
        }
        await handleAssistantMessage(message)
      } else if (streamedAny) {
        // Prose reply: the preview bubble IS the settled message (same key;
        // the envelope content + run id are authoritative).
        finalizePreview(message.content ?? "", message.workflow_run_id)
      } else {
        setMessages((prev) => prev.filter((m) => m.id !== streamId))
        await handleAssistantMessage(message)
      }
    } catch (e) {
      typewriter.flush()
      if (e instanceof DOMException && e.name === "AbortError") {
        // Stopped mid-stream: the partial preview settles as static text
        // (the server may still finish the turn server-side).
        setMessages((prev) =>
          prev.map((m) => (m.id === streamId ? { ...m, streaming: false } : m))
        )
        return
      }
      // The server commits nothing on a failed turn — roll the optimistic
      // bubble (and any streamed preview) back out, restore the draft, and
      // re-stage the consumed attachment chips.
      setMessages((prev) => prev.filter((m) => m.id !== streamId))
      if (opts?.rollbackId) {
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
      }
      if (opts?.rollbackStaged?.length) {
        const chips = opts.rollbackStaged
        setStaged((prev) => {
          const kept = new Set(prev.map((s) => s.localId))
          return [...prev, ...chips.filter((c) => !kept.has(c.localId))]
        })
      }
      toast.error(e instanceof Error ? e.message : t("chat.failed"))
    } finally {
      if (abortRef.current === ctrl) {
        abortRef.current = null
        setChatBusy(false)
      }
    }
  }

  /** Fresh composer navigation: the handed-over draft is the conversation's
   * first message — send it once on mount (the opening bubble already
   * renders it from the prompt prop, so nothing is pushed to the flow).
   * Router state survives a page refresh, so before firing we check the
   * server: if the first send already landed, REBUILD from the server
   * (dock / live run) instead of duplicating the message — there is no
   * server-side dedup by design. */
  useEffect(() => {
    if (!firstMessage || initialRunId || firstMessageSentRef.current) return
    firstMessageSentRef.current = true
    void (async () => {
      try {
        const res = await apiFetch(`/api/v1/projects/${projectId}/results`, {
          toast: false,
        })
        if (res.ok) {
          const data = (await res.json()) as {
            prompt?: string | null
            latest_run?: {
              id: string
              status: string
              context?: {
                outputs?: unknown
                target_language?: string
                dub_languages?: string[]
                instruction?: string | null
              } | null
            } | null
          }
          if ((data.prompt ?? "") === firstMessage.text) {
            const run = data.latest_run
            if (run && (run.status === "pending" || run.status === "running")) {
              // Refresh after the run started: attach to it (intent rebuilt
              // from the run context for the confirmed-plan summary line).
              const runCtx = run.context ?? {}
              setIntent(
                normalizeIntent({
                  outputs: runCtx.outputs,
                  language: runCtx.target_language,
                  dub_languages: runCtx.dub_languages,
                  specific_instruction: runCtx.instruction,
                })
              )
              landOnStartedRun(run.id, null)
            } else {
              // Refresh while confirming: rebuild the dock + panel plan.
              const q = await fetchPendingQuestion()
              if (q) await handleAssistantMessage(q)
            }
            return
          }
        }
      } catch {
        /* results unreadable — fall through and send */
      }
      await sendChat(firstMessage.text, {
        mentions: firstMessage.mentions,
        personaId: firstMessage.personaId,
      })
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /** Fresh-flow auto-start: the first inference docked a book with nothing
   * to clarify (an explicit instruction) — start it once the dock state has
   * settled, without making the user press Start. */
  useEffect(() => {
    if (!autoStartArmedRef.current) return
    if (phase !== "confirm" || !intentReady) return
    if (!pendingQuestion || pendingQuestion.question?.kind !== "task_book") return
    autoStartArmedRef.current = false
    autoStartedRef.current = true
    handleStartGeneration()
  }, [phase, intentReady, pendingQuestion, handleStartGeneration])

  /** Docked choice question answered by a button click — the answer
   * endpoint records it and continues the conversation (answer = resume). */
  const handleChoiceAnswer = async (optionId: string) => {
    if (!pendingQuestion || answering) return
    setAnswering(true)
    try {
      const res = await apiFetch(
        `/api/v1/chat/messages/${pendingQuestion.id}/answer`,
        { method: "POST", body: { kind: "option", option_id: optionId } },
      )
      if (!res.ok) return // apiFetch already toasted the server's reason
      const data = (await res.json()) as {
        answered_question: QuestionMessage
        follow_up: QuestionMessage | null
      }
      setPendingQuestion(null)
      pushQaArchive(data.answered_question)
      if (data.follow_up) void handleAssistantMessage(data.follow_up)
    } finally {
      setAnswering(false)
    }
  }

  /** Checkpoint bail (期 4): stop the parked run — the endpoint settles the
   * node, skips the downstream and completes the run synchronously, so we
   * archive the QA and leave quietly (never an error toast, #5). */
  const handleCheckpointBail = async () => {
    if (!pendingQuestion || answering) return
    setAnswering(true)
    try {
      const res = await apiFetch(
        `/api/v1/chat/messages/${pendingQuestion.id}/answer`,
        { method: "POST", body: { kind: "bail" } },
      )
      if (!res.ok) return
      const data = (await res.json()) as { answered_question: QuestionMessage }
      setPendingQuestion(null)
      pushQaArchive(data.answered_question)
      toast.info(t("generationOverlay.stopped"))
      onClose()
    } finally {
      setAnswering(false)
    }
  }

  /** Stop the in-flight assistant reply (aborts the fetch; the user's own
   * message stays in the flow). */
  const handleStop = () => {
    abortRef.current?.abort()
    abortRef.current = null
    setChatBusy(false)
  }

  const handleSend = () => {
    const text = input.trim()
    const ready = staged.filter(
      (s): s is StagedUpload & { asset: ProjectAsset } =>
        s.status === "done" && !!s.asset
    )
    // isStarting: the dock's Start is mid-answer — a chat turn now would
    // race it (it could supersede the question being answered). An in-flight
    // upload blocks send — the chips must settle first (× removes one).
    if ((!text && ready.length === 0) || chatBusy || isStarting) return
    if (staged.some((s) => s.status === "uploading")) return
    const sentAssets = ready.map((s) => s.asset)
    const rollbackId = crypto.randomUUID()
    setMessages((prev) => [
      ...prev,
      { id: rollbackId, role: "user", content: text, assets: sentAssets },
    ])
    // Consumed on send (chip law ②): the editor's clear funnels the emptied
    // {text, mentions} back through onChange; an error chip stays staged for
    // retry/removal — it never rides a message.
    editorRef.current?.clear()
    setStaged((prev) => prev.filter((s) => s.status !== "done"))
    void sendChat(text, {
      rollbackId,
      draft: text,
      mentions,
      rollbackMentions: mentions,
      attachments: ready.map((s) => ({
        id: s.asset.id,
        name: s.asset.title || s.file.name,
        type: chatAttachmentType(s.asset.type),
        url: s.asset.file_url ?? undefined,
        size: s.file.size,
        status: "uploaded" as const,
      })),
      rollbackStaged: ready,
    })
  }

  const handleClose = () => {
    if (phase === "running" && !terminal) {
      toast.info(t("generationOverlay.continuesInBackground"))
    }
    onClose()
  }

  // Esc mirrors the back pill (fullscreen); in the dock it retracts the
  // history drawer — the dock itself has no close (it IS the page's chrome).
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return
      if (shell === "dock") {
        setDockView((v) => (v === "drawer" ? "summary" : v))
        return
      }
      if (shell === "fullscreen") handleClose()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, terminal, shell])

  const sectionLabel = "text-[11px] font-medium text-meta"

  // The answered task_book question's QA archive display (start via dock).
  const answeredDisplay = answeredQuestion?.answer
    ? qaAnswerText(answeredQuestion.answer, t, !!answeredQuestion.workflow_run_id)
    : null

  // The dock's live form outside the confirm phase: a pending choice
  // question from the chat loop (task_book docks only while confirming).
  const pendingChoice =
    pendingQuestion &&
    pendingQuestion.question?.kind === "choice" &&
    !pendingQuestion.answer
      ? pendingQuestion
      : null

  // Dock summary (D4): the run's terminal aggregate ("Done · 3 clips · …")
  // is the收官摘要; a chat reply sent AFTER the terminal is newer and
  // supersedes it. Restored docks read the summary off the SSE snapshot.
  const lastAssistant = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (m.role === "assistant" && !m.qa && !m.streaming && m.content.trim()) {
        return m
      }
    }
    return null
  }, [messages])
  const dockSummary =
    terminal && status !== "failed" && summary && !postTerminalReplyRef.current
      ? summary
      : (lastAssistant?.content ?? null)

  // Prohibition #6 — the dock never goes silent: new agent speech (a chat
  // reply / the收官摘要 landing / a choice ask) raises the summary back
  // from the collapsed pill.
  const lastAgentKey =
    shell === "dock"
      ? (lastAssistant?.id ?? (terminal && summary ? `summary:${runId ?? "run"}` : null))
      : null
  const lastAgentKeyRef = useRef<string | null>(null)
  useEffect(() => {
    if (!lastAgentKey) return
    const first = lastAgentKeyRef.current === null
    if (lastAgentKeyRef.current !== lastAgentKey) {
      lastAgentKeyRef.current = lastAgentKey
    }
    if (!first) setDockView((v) => (v === "collapsed" ? "summary" : v))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastAgentKey])
  useEffect(() => {
    if (shell === "dock" && pendingChoice) {
      setDockView((v) => (v === "collapsed" ? "summary" : v))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingChoice?.id, shell])

  // Plan-card placement (2026-08-06 in-flight rework): settled → pinned
  // bottom-most (order-10); while a chat turn is in flight → inline at its
  // echo anchor in the message loop (above the new user bubble + thinking
  // row), so the flow reads chronologically and the stale confirm dock can
  // hide. Restored sessions have no echo bubble — the card stays pinned.
  const planCardVisible = phase === "confirm" && intentReady
  const planCardInline = planCardVisible && chatBusy && liveBubblePresent
  const planCard = (
    <Message align="start">
      <MessageContent>
        <div className="w-full motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-300">
          {/* Prose echo of the understood plan — the card
              never lands naked (Opus pattern). The LLM's
              own one-line echo (intent.answer, streamed as
              deltas this turn and persisted in the pending
              intent) wins; the localized template is the
              fallback for legacy/null echoes. Hidden when
              the streamed bubble already carries it. */}
          {!liveBubblePresent && (
            <p className="mb-3 text-sm leading-relaxed">
              {intent.answer ??
                t("generationOverlay.planProse", { summary: planSummary })}
            </p>
          )}
          {/* No shadow/glow here: the scroller's paint
              containment clips the halo on the sides (it
              survived only on top, looking like a cut-off
              shadow). Depth comes from bg contrast alone. */}
          <Card className="ring-0 bg-muted">
            <div className="flex flex-col gap-7 p-6">
              <div className="space-y-1">
                <h3 className="text-base font-semibold">
                  {t("generationOverlay.title")}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {t("generationOverlay.subtitle")}
                </p>
              </div>

              {/* Identity echo — one read-only line, never a
                  question: whose style the run generates in (the
                  skin follows the persona, ADR-038). */}
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Mic2 className="h-3.5 w-3.5" />
                {t("generationOverlay.identityEcho", {
                  persona:
                    identityPersona ??
                    t("generationOverlay.identityPersonaAuto"),
                })}
              </p>

              {/* Task slots — one row per requested output.
                  Language is a per-row property (the book-
                  level field is retired): every row's
                  dropdown shows a concrete language.
                  Same-type siblings (e.g. an English and a
                  German post) are separate rows. */}
              <div className="flex flex-col gap-2">
                <div className="flex flex-col gap-1">
                  <span className={sectionLabel}>
                    {t("generationOverlay.outputsLabel")}
                  </span>
                  <p className="text-xs text-muted-foreground">
                    {t("generationOverlay.outputsHint")}
                  </p>
                </div>
                <div className="flex flex-col gap-2">
                  {intent.outputs.map((slot, index) => {
                    const meta = OUTPUT_OPTIONS.find(
                      (o) => o.key === slot.type
                    )
                    if (!meta) return null
                    const { labelKey, Icon } = meta
                    const limits = SLOT_COUNT_LIMITS[slot.type]
                    const count =
                      slot.count ?? SLOT_COUNT_DEFAULT[slot.type]
                    return (
                      <div
                        key={index}
                        className="flex flex-col gap-2 rounded-md bg-card p-3"
                      >
                        <div className="flex items-center gap-2">
                          <span className="flex items-center gap-1.5 text-sm">
                            <Icon className="h-3.5 w-3.5" />
                            {t(labelKey)}
                          </span>
                          {limits && count != null && (
                            <div className="flex items-center gap-1">
                              <Button
                                variant="outline"
                                size="icon"
                                className="h-7 w-7"
                                disabled={count <= limits[0]}
                                aria-label={t(
                                  "generationOverlay.countDecrease"
                                )}
                                onClick={() =>
                                  updateSlot(index, {
                                    count: Math.max(
                                      limits[0],
                                      count - 1
                                    ),
                                  })
                                }
                              >
                                <Minus className="h-3.5 w-3.5" />
                              </Button>
                              <span className="w-7 text-center text-sm tabular-nums">
                                {count}
                              </span>
                              <Button
                                variant="outline"
                                size="icon"
                                className="h-7 w-7"
                                disabled={count >= limits[1]}
                                aria-label={t(
                                  "generationOverlay.countIncrease"
                                )}
                                onClick={() =>
                                  updateSlot(index, {
                                    count: Math.min(
                                      limits[1],
                                      count + 1
                                    ),
                                  })
                                }
                              >
                                <Plus className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          )}
                          <div className="ml-auto flex items-center gap-1">
                            <Select
                              value={slot.language ?? "en"}
                              onValueChange={(value) =>
                                updateSlot(index, {
                                  language: (value as string) || "en",
                                })
                              }
                            >
                              <SelectTrigger className="h-8 w-28 text-xs">
                                <SelectValue>
                                  {(value: string) =>
                                    t(`languages.${value}`, {
                                      defaultValue: value,
                                    })
                                  }
                                </SelectValue>
                              </SelectTrigger>
                              <SelectContent>
                                {LANGUAGE_OPTIONS.map((lang) => (
                                  <SelectItem
                                    key={lang.code}
                                    value={lang.code}
                                  >
                                    {t(lang.labelKey)}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            {intent.outputs.length > 1 && (
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                aria-label={t(
                                  "generationOverlay.removeSlot"
                                )}
                                onClick={() => removeSlot(index)}
                              >
                                <X className="h-3.5 w-3.5" />
                              </Button>
                            )}
                          </div>
                        </div>
                        <Input
                          value={slot.focus ?? ""}
                          onChange={(e) =>
                            updateSlot(index, {
                              focus: e.target.value || null,
                            })
                          }
                          placeholder={t(
                            "generationOverlay.slotFocusPlaceholder",
                            { type: t(labelKey) }
                          )}
                          className="h-8 text-xs"
                        />
                      </div>
                    )
                  })}
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button
                        variant="outline"
                        size="sm"
                        // self-start: the section is a flex
                        // column — without this the trigger
                        // would stretch to full width.
                        className="h-9 gap-1.5 self-start"
                      />
                    }
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>{t("generationOverlay.addOutput")}</span>
                    <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent>
                    {OUTPUT_OPTIONS.map(({ key, labelKey, Icon }) => (
                      <DropdownMenuItem
                        key={key}
                        disabled={
                          key === "clips" &&
                          intent.outputs.some(
                            (s) => s.type === "clips"
                          )
                        }
                        onClick={() => addSlot(key)}
                      >
                        <Icon className="h-3.5 w-3.5" />
                        {t(labelKey)}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>

              {/* Voice-over versions (dub_languages) — one
                  chip per forked voice-over language. Every
                  clip gets one DERIVED version per language
                  (fork semantics), so the version count is a
                  multiplication — shown explicitly below.
                  Chips are removable (down to none = no
                  dubbing); adding a language goes through
                  chat refine, not panel editing (R1 scope). */}
              {intent.dub_languages.length > 0 && (
                <div className="flex flex-col gap-2">
                  <div className="flex flex-col gap-1">
                    <span className={sectionLabel}>
                      {t("generationOverlay.dubLabel")}
                    </span>
                    <p className="text-xs text-muted-foreground">
                      {t("generationOverlay.dubHint")}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {intent.dub_languages.map((lang) => (
                      <span
                        key={lang}
                        className="flex items-center gap-1.5 rounded-md bg-card px-2.5 py-1.5 text-sm"
                      >
                        <Mic2 className="h-3.5 w-3.5 text-muted-foreground" />
                        {t(`languages.${lang}`, { defaultValue: lang })}
                        <button
                          type="button"
                          aria-label={t(
                            "generationOverlay.removeDubLanguage"
                          )}
                          className="text-muted-foreground transition-colors hover:text-foreground"
                          onClick={() =>
                            setIntent((prev) => ({
                              ...prev,
                              dub_languages: prev.dub_languages.filter(
                                (l) => l !== lang
                              ),
                            }))
                          }
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </span>
                    ))}
                  </div>
                  {/* The multiplication, in the open: every
                      clip gets one version per language. */}
                  {clipsSlotForDub && (
                    <p className="text-xs text-muted-foreground">
                      {t("generationOverlay.dubVersionCount", {
                        clips:
                          clipsSlotForDub.count ??
                          SLOT_COUNT_DEFAULT.clips,
                        langs: intent.dub_languages.length,
                        total:
                          (clipsSlotForDub.count ??
                            SLOT_COUNT_DEFAULT.clips) *
                          intent.dub_languages.length,
                      })}
                    </p>
                  )}
                </div>
              )}

              {/* Instruction */}
              <div className="flex flex-col gap-2">
                <div className="flex flex-col gap-1">
                  <span className={sectionLabel}>
                    {t("generationOverlay.instructionLabel")}
                  </span>
                  <p className="text-xs text-muted-foreground">
                    {t("generationOverlay.instructionHint")}
                  </p>
                </div>
                <Textarea
                  value={intent.specific_instruction || ""}
                  onChange={(e) =>
                    setIntent((prev) => ({
                      ...prev,
                      specific_instruction: e.target.value,
                    }))
                  }
                  placeholder={t("generationOverlay.instructionPlaceholder")}
                  className="min-h-[100px] resize-none text-sm"
                />
              </div>
            </div>
          </Card>
        </div>
      </MessageContent>
    </Message>
  )

  /* The message flow — one JSX block, two hosts: the fullscreen chat
      region, or the dock's history drawer (never mounted in both at once).
      The message machine itself is untouched — only the shell changes. */
  const chatScroller = (
        <MessageScrollerProvider>
          <MessageScroller className="h-full">
            <MessageScrollerViewport className="scroll-fade-y">
              <MessageScrollerContent className="mx-auto w-full max-w-3xl gap-8 px-4 pb-8 pt-4">
                {/* Opening prompt */}
                {prompt ? (
                  <MessageScrollerItem>
                    <UserBubble text={prompt} assets={openingAssets} />
                  </MessageScrollerItem>
                ) : null}

                {/* Plan card (confirm phase) — pinned bottom-most
                    (order-10) while settled. During an in-flight turn it
                    unpins and renders inline at its echo anchor in the loop
                    below (the stale confirm dock hides with it); restored
                    sessions have no echo bubble to anchor to — the card
                    stays pinned. */}
                {planCardVisible && !planCardInline && (
                  <MessageScrollerItem className="order-10">
                    {planCard}
                  </MessageScrollerItem>
                )}

                {/* Running: the confirmed plan archives as a QA pair (start
                    via the dock) or collapses to a summary line (attach /
                    legacy paths rebuild it from the run context). */}
                {phase === "running" && (
                  <>
                    <MessageScrollerItem>
                      {answeredQuestion && answeredDisplay ? (
                        <QaPair
                          question={t("generationOverlay.confirmQuestion")}
                          questionDetail={planSummary}
                          answer={answeredDisplay.text}
                          muted={answeredDisplay.muted}
                        />
                      ) : (
                        <Message align="start">
                          <MessageContent>
                            <div className="flex w-full items-center gap-3 rounded-lg bg-muted px-4 py-3">
                              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-green-600/10 dark:bg-green-400/10">
                                <Check className="h-3.5 w-3.5 text-green-600 dark:text-green-400" />
                              </span>
                              <div className="min-w-0 truncate text-sm">
                                <span className="font-medium">
                                  {t("generationOverlay.title")}
                                </span>
                                <span className="text-muted-foreground">
                                  {" · "}
                                  {planSummary}
                                </span>
                              </div>
                            </div>
                          </MessageContent>
                        </Message>
                      )}
                    </MessageScrollerItem>
                    <MessageScrollerItem>
                      <Message align="start">
                        <MessageContent>
                          <div className="w-full space-y-4">
                            <p className="text-sm leading-relaxed">
                              {t("generationOverlay.startingLine")}
                            </p>
                            <div className="flex flex-col gap-2">
                              {/* Run still queued (assets processing / worker
                                  hasn't claimed it): no workflow steps exist
                                  yet, so stand in with a friendly marker —
                                  otherwise the flow looks dead on attach. */}
                              {steps.length === 0 && !terminal && (
                                <StepMarker
                                  status="running"
                                  label={
                                    assets.some(
                                      (a) =>
                                        a.processing_status === "pending" ||
                                        a.processing_status === "processing"
                                    )
                                      ? t("results.stepper.transcribing")
                                      : t("results.stepper.queued")
                                  }
                                />
                              )}
                              {steps.map((step) => (
                                <StepMarker
                                  key={step.id}
                                  status={step.status}
                                  label={
                                    // Same chain as RunCard: live summary →
                                    // friendly stage copy → kind fallback.
                                    step.summary ||
                                    (step.stage
                                      ? t(`results.stepper.${step.stage}`, {
                                          defaultValue: "",
                                        })
                                      : "") ||
                                    t(`chat.stepKinds.${step.kind}`, {
                                      defaultValue: step.kind,
                                    })
                                  }
                                  error={step.error}
                                />
                              ))}
                              {terminal && summary && (
                                <Marker variant="border" className="pt-2">
                                  <MarkerContent>{summary}</MarkerContent>
                                </Marker>
                              )}
                              {terminal && status === "failed" && (
                                <Marker
                                  variant="border"
                                  className="pt-2 text-destructive"
                                >
                                  <MarkerContent>
                                    {t("generationOverlay.failed")}
                                  </MarkerContent>
                                </Marker>
                              )}
                            </div>
                          </div>
                        </MessageContent>
                      </Message>
                    </MessageScrollerItem>
                  </>
                )}

                {/* Conversation below the pinned regions. A superseded plan
                    version's chip sits right after the echo bubble whose
                    turn produced it; the live book is the bottom-most card. */}
                {messages.map((m) => (
                  <Fragment key={m.id}>
                    <MessageScrollerItem>
                      {m.qa ? (
                        <QaPair
                          question={m.qa.question}
                          questionDetail={m.qa.detail}
                          answer={m.qa.answer}
                          muted={m.qa.muted}
                        />
                      ) : m.role === "user" ? (
                        <UserBubble text={m.content} assets={m.assets} />
                      ) : (
                        <>
                          {m.content ? (
                            <AssistantText text={m.content} streaming={m.streaming} />
                          ) : null}
                          {m.runId ? (
                            <Message align="start">
                              <MessageContent>
                                <RunCard runId={m.runId} projectId={projectId} />
                              </MessageContent>
                            </Message>
                          ) : null}
                        </>
                      )}
                    </MessageScrollerItem>
                    {planVersions.map((version, index) =>
                      version.messageId === m.id ? (
                        <MessageScrollerItem key={`${m.id}-plan-v${index + 1}`}>
                          <PlanVersionChip
                            n={index + 1}
                            book={version.book}
                            summary={summarizeBook(version.book)}
                            expanded={expandedVersion === index}
                            onToggle={() =>
                              setExpandedVersion(
                                expandedVersion === index ? null : index
                              )
                            }
                            onRestore={() => restoreVersion(index)}
                            slotLabel={slotLabel}
                          />
                        </MessageScrollerItem>
                      ) : null
                    )}
                    {/* In-flight only: the live plan card unpins from the
                        bottom and anchors right after its own echo bubble —
                        above the new user bubble and the thinking row. When
                        the turn lands, the version chip takes this slot and
                        the fresh card pins bottom-most again. */}
                    {planCardInline && m.id === liveBookMessageId ? (
                      <MessageScrollerItem key={`${m.id}-live-plan`}>
                        {planCard}
                      </MessageScrollerItem>
                    ) : null}
                  </Fragment>
                ))}

                {/* Thinking row covers send → first delta; once the preview
                    bubble exists it IS the progress indicator. */}
                {chatBusy && !messages.some((m) => m.streaming) && (
                  <MessageScrollerItem>
                    <ThinkingRow label={t("chat.thinking")} />
                  </MessageScrollerItem>
                )}
              </MessageScrollerContent>
            </MessageScrollerViewport>
            {/* Jump-to-latest pill — appears only when the user has scrolled
                up off the bottom (the primitive tracks visibility). */}
            <MessageScrollerButton direction="end" />
          </MessageScroller>
        </MessageScrollerProvider>
  )

  return (
    <div className="fixed inset-0 z-50 flex flex-col">
      {/* Backdrop — a pure visual layer (always pointer-events-none):
          opaque while fullscreen, fades away on the收官 frame (D3); in the
          dock the shell is click-through and the canvas shows through. */}
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-0 bg-background transition-opacity duration-500 motion-reduce:transition-none",
          shell === "fullscreen" ? "opacity-100" : "opacity-0"
        )}
      />

      {/* Header band — the back pill owns a real strip, so scrolled content
          structurally never enters its zone (a fade alone still lets text
          slide under the pill). Fullscreen only: the dock has no close. */}
      {shell === "fullscreen" && (
        <div className="relative shrink-0 px-4 pt-4">
          <Button
            variant="secondary"
            size="sm"
            className="h-9 gap-1.5 rounded-md px-3"
            onClick={handleClose}
          >
            <ArrowLeft className="h-4 w-4" />
            {t("generationOverlay.backToProjects")}
          </Button>
        </div>
      )}

      {/* Chat region — fullscreen it hosts the flow; on the收官 frame the
          flow retracts upward and fades (消息区上收); in the dock the
          region is an empty click-through spacer (the canvas owns the
          center). The REGION keeps its flex-1 slot throughout, so the
          bottom input row never moves (D3: 输入组全程零位移). */}
      {shell !== "dock" ? (
        <div
          className={cn(
            "relative min-h-0 flex-1 transition-all duration-500 motion-reduce:transition-none",
            shell === "collapsing" && "pointer-events-none -translate-y-4 opacity-0"
          )}
        >
          {chatScroller}
        </div>
      ) : (
        <div className="pointer-events-none min-h-0 flex-1" aria-hidden />
      )}

      {/* Bottom row — the input group's immutable slot across the three
          parking spots (composer / overlay / dock): it never moves (D3).
          The pending question docks directly above it (ask primitive): the
          flow archives decisions, the dock holds the one still open. The
          task-book dock HIDES while a turn is in flight (a stale plan must
          not be Start-able mid-revision); a choice dock JOINS the input
          visually (joined + the input drops its top rounding) — the input
          IS the freeform "something else" row, its placeholder already says
          so. In the dock shell the history drawer / summary card stack
          above everything (D4), floating over the canvas. */}
      <div
        className={cn(
          "relative shrink-0 px-4 pb-5 pt-2",
          shell === "dock" && "pointer-events-none"
        )}
      >
        <div
          className={cn(
            "mx-auto w-full max-w-3xl",
            shell === "dock" && "pointer-events-auto"
          )}
        >
          {/* Dock extras — the history drawer opens above the summary row;
              the summary card (latest agent line) is the drawer's toggle.
              Both use the shared overlay-surface frost over the canvas. */}
          {shell === "dock" && dockView === "drawer" && (
            <div className="overlay-surface mb-2 h-[min(55vh,520px)] overflow-hidden rounded-xl">
              {chatScroller}
            </div>
          )}
          {shell === "dock" && (
            <div className="mb-2 flex items-center gap-2">
              {dockView !== "collapsed" && dockSummary ? (
                <button
                  type="button"
                  onClick={() =>
                    setDockView((v) => (v === "drawer" ? "summary" : "drawer"))
                  }
                  className="overlay-surface flex min-w-0 flex-1 items-center gap-2 rounded-xl px-4 py-2.5 text-left"
                >
                  <Streamdown
                    mode="static"
                    className="line-clamp-2 min-w-0 flex-1 text-sm leading-snug [&_p]:inline"
                  >
                    {dockSummary}
                  </Streamdown>
                  {dockView === "drawer" ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                  ) : (
                    <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() =>
                    setDockView((v) => (v === "drawer" ? "summary" : "drawer"))
                  }
                  className="overlay-surface flex h-9 items-center gap-1.5 rounded-md px-3 text-sm"
                >
                  <History className="h-4 w-4" />
                  {t("results.dock.history")}
                </button>
              )}
              {dockView !== "collapsed" && dockSummary && (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t("results.dock.collapse")}
                  onClick={() => setDockView("collapsed")}
                  className="overlay-surface h-9 w-9 shrink-0 rounded-md"
                >
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
          )}
          {phase === "confirm" && intentReady && !chatBusy && (
            <QuestionDock
              kind="task_book"
              question={t("generationOverlay.confirmQuestion")}
              reasons={reasons}
              autonomy={autonomy}
              onAutonomyChange={setAutonomy}
              onStart={handleStartGeneration}
              onCancel={handleCancel}
              starting={isStarting}
              startDisabled={!canStartGeneration || chatBusy}
            />
          )}
          {phase !== "confirm" && pendingChoice && (
            <QuestionDock
              kind="choice"
              joined
              question={pendingChoice.content ?? ""}
              options={pendingChoice.question?.options ?? []}
              estimate={pendingChoice.question?.estimate}
              onAnswer={handleChoiceAnswer}
              answering={answering}
              onBail={
                // Checkpoint questions (a run parked on the answer) get the
                // bail affordance; plain chat asks don't — their graceful
                // exit is just typing the next message.
                pendingChoice.workflow_run_id ? handleCheckpointBail : undefined
              }
            />
          )}
          {phase === "confirm" && startError && (
            <p className="mb-2 text-sm text-destructive">{startError}</p>
          )}
          <div
            className={
              phase !== "confirm" && pendingChoice
                ? "rounded-b-lg bg-muted p-2"
                : "rounded-lg bg-muted p-2"
            }
          >
            {/* The canvas's focused product (D8 焦点注入): one chip riding
                the input group — visible, × purifies; it joins each turn as
                `focus_output_id` (a context line, never a scope). */}
            {focusOutput && (
              <div className="flex px-1 pb-2">
                <span className="flex min-w-0 items-center gap-1.5 rounded-md bg-card px-2 py-1 text-xs text-muted-foreground">
                  <Crosshair className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">
                    {t("results.dock.focus", { name: focusOutput.label })}
                  </span>
                  <button
                    type="button"
                    aria-label={t("results.dock.clearFocus")}
                    className="shrink-0 transition-colors hover:text-foreground"
                    onClick={onClearFocus}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </span>
              </div>
            )}
            {/* Staged attachments — the upload lifecycle lives here (never
                auto-sent): uploading chips shimmer, done chips wait for the
                send button, error chips offer retry; × removes (and deletes
                the already-created asset). */}
            {staged.length > 0 && (
              <AttachmentGroup className="px-1 pb-2">
                {staged.map((s) => {
                  const Icon = s.asset
                    ? assetTypeIcon(s.asset.type)
                    : s.file.type.startsWith("video/")
                      ? Video
                      : s.file.type.startsWith("audio/")
                        ? Mic2
                        : s.file.type.startsWith("image/")
                          ? ImageIcon
                          : FileText
                  const typeLabel = s.asset
                    ? t(`generationOverlay.assetTypes.${s.asset.type}`, {
                        defaultValue: s.asset.type,
                      })
                    : t("generationOverlay.assetTypes.file")
                  return (
                    <Attachment
                      key={s.localId}
                      size="sm"
                      state={
                        s.status === "uploading"
                          ? "uploading"
                          : s.status === "error"
                            ? "error"
                            : "done"
                      }
                    >
                      <AttachmentMedia>
                        <Icon />
                      </AttachmentMedia>
                      <AttachmentContent>
                        <AttachmentTitle>{s.file.name}</AttachmentTitle>
                        <AttachmentDescription>
                          {s.status === "error"
                            ? t("composer.uploadFailed")
                            : typeLabel}
                        </AttachmentDescription>
                      </AttachmentContent>
                      <AttachmentActions>
                        {s.status === "error" && (
                          <AttachmentAction
                            aria-label={t("generationOverlay.retryUpload")}
                            onClick={() => retryStaged(s)}
                          >
                            <Undo2 />
                          </AttachmentAction>
                        )}
                        <AttachmentAction
                          aria-label={t("generationOverlay.removeAttachment")}
                          onClick={() => removeStaged(s)}
                        >
                          <X />
                        </AttachmentAction>
                      </AttachmentActions>
                    </Attachment>
                  )
                })}
              </AttachmentGroup>
            )}
            <div className="flex items-end gap-2">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                accept="video/*,audio/*,image/*,.pdf,.txt,.md,.markdown,.pptx,.ppt"
                onChange={(e) => handleFilesPicked(e.target.files)}
              />
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 shrink-0"
                aria-label={t("generationOverlay.attachFiles")}
                onClick={() => fileInputRef.current?.click()}
              >
                <Paperclip className="h-4.5 w-4.5" />
              </Button>
              {/* The composer family's editor (one input component across
                  composer / overlay chat / output chat): @-chips inline —
                  asset = context enrichment, output = the pinned revision
                  target — Enter sends, IME guarded inside the component. */}
              <MentionEditor
                ref={editorRef}
                placeholder={
                  phase !== "confirm" &&
                  pendingChoice &&
                  (pendingChoice.question?.options?.length ?? 0) > 0 &&
                  pendingChoice.question?.allow_freeform !== false
                    ? t("chat.choicePlaceholder")
                    : phase === "confirm"
                      ? t("generationOverlay.chatPlaceholderConfirm")
                      : t("generationOverlay.chatPlaceholder")
                }
                mentionContext={mentionContext}
                onChange={handleEditorChange}
                onSubmit={handleSend}
                className="max-h-32 min-h-9 text-sm"
              />
              {chatBusy ? (
                <Button
                  size="icon"
                  variant="secondary"
                  className="h-9 w-9 shrink-0 rounded-full"
                  onClick={handleStop}
                  aria-label={t("chat.stop")}
                >
                  <Square className="h-3.5 w-3.5 fill-current" />
                </Button>
              ) : (
                <Button
                  size="icon"
                  className="h-9 w-9 shrink-0 rounded-full"
                  disabled={
                    (!input.trim() &&
                      !staged.some((s) => s.status === "done")) ||
                    staged.some((s) => s.status === "uploading")
                  }
                  onClick={handleSend}
                  aria-label={t("chat.send")}
                >
                  <ArrowUp className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
})
