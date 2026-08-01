"use client"

/** GenerationOverlay — the post-composer conversation surface.
 *
 * Full-screen chat (Opus-style): the composer prompt opens the conversation,
 * the inferred task book arrives as an editable plan card pinned in the flow,
 * and confirming starts the run — whose steps light up below. The bottom
 * input is always live: before confirmation it refines the plan (intent
 * re-inference, or a plain answer to a question); after the run starts it
 * talks to the project-scoped chat loop (CHAT_ARCH §3).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  ArrowLeft,
  ArrowUp,
  Check,
  ChevronDown,
  CircleHelp,
  FileText,
  Image as ImageIcon,
  Images,
  Loader2,
  Mic2,
  Minus,
  Newspaper,
  Plus,
  Quote,
  Square,
  Video,
  X,
} from "lucide-react"

import { apiFetch } from "@/lib/api"
import { useRunEvents } from "@/lib/use-run-events"
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
  AttachmentContent,
  AttachmentDescription,
  AttachmentGroup,
  AttachmentMedia,
  AttachmentTitle,
} from "@/components/ui/attachment"
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import {
  MessageScroller,
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
import type { IntentSlot } from "@/lib/types"

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

/** Slot-language Select sentinel for "same as the task book" (null). */
const BOOK_LANGUAGE = "__book__"

type OutputKey = (typeof OUTPUT_OPTIONS)[number]["key"]
type Phase = "confirm" | "running" | "answer"

export interface InferredIntent {
  action: "generate" | "answer"
  answer: string | null
  language: string
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
 * slot-shaped InferredIntent the panel edits. */
export function normalizeIntent(raw: unknown): InferredIntent {
  const data = (raw ?? {}) as Record<string, unknown>
  return {
    action: data.action === "answer" ? "answer" : "generate",
    answer: (data.answer as string | null) ?? null,
    language: typeof data.language === "string" && data.language ? data.language : "en",
    outputs: normalizeSlots(data.outputs, data.clip_count as number | null),
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
  /** QA archive item (answered question collapsing into the flow). */
  qa?: { question: string; answer: string; muted: boolean }
}

/** The typed question payload mirrored from the API (messages.question). */
interface QuestionPayload {
  kind: "task_book" | "choice" | "confirm"
  options?: { id: string; label: string }[]
  allow_freeform?: boolean
  cost_hint?: string | null
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

/** The /intent turn's discriminated union (B1 + G-1): a plan to confirm, a
 * prose answer, or the docked task book started by a prose confirmation
 * ("looks good, start it" — the QA archive row rides along). */
type IntentTurnResponse =
  | { type: "plan"; intent: unknown; reasons?: string[] }
  | { type: "answer"; text: string }
  | { type: "started"; run_id: string; answered_question: QuestionMessage }

interface ProjectAsset {
  id: string
  type: string
  file_url: string | null
  title: string | null
  processing_status: "pending" | "processing" | "completed" | "failed"
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

interface GenerationOverlayProps {
  projectId: string
  prompt: string
  initialIntent?: InferredIntent | null
  initialNeedsClarification?: boolean
  /** needs_clarification reason keys from the last inference — the dock
   * shows them as the "needs your check" line (回显). */
  initialReasons?: string[]
  brandTemplateId?: string
  /** Attach to an already-running generation (returning visitor): skips the
   * confirm phase and the intent fallback, lands straight on the step flow. */
  initialRunId?: string | null
  onClose: () => void
  onComplete: () => void
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
 * The opening prompt carries the project's source materials as attachments. */
function UserBubble({ text, assets }: { text: string; assets?: ProjectAsset[] }) {
  const { t } = useTranslation()
  return (
    <Message align="end">
      <MessageContent>
        <BubbleGroup>
          <Bubble variant="muted" align="end">
            <BubbleContent className="rounded-2xl px-4 py-2.5 text-sm">
              <p className="whitespace-pre-wrap">{text}</p>
            </BubbleContent>
          </Bubble>
        </BubbleGroup>
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

/** Assistant prose — plain text, no bubble (Opus pattern). */
function AssistantText({ text }: { text: string }) {
  return (
    <Message align="start">
      <MessageContent>
        <p className="max-w-[85%] whitespace-pre-wrap text-sm leading-relaxed">
          {text}
        </p>
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

export function GenerationOverlay({
  projectId,
  prompt,
  initialIntent,
  initialNeedsClarification = true,
  initialReasons,
  brandTemplateId,
  initialRunId,
  onClose,
  onComplete,
}: GenerationOverlayProps) {
  const { t } = useTranslation()

  const [phase, setPhase] = useState<Phase>(
    initialRunId
      ? "running"
      : initialIntent?.action === "answer"
        ? "answer"
        : "confirm"
  )
  const [intent, setIntent] = useState<InferredIntent>(() =>
    initialIntent
      ? normalizeIntent(initialIntent)
      : {
          action: "generate",
          answer: null,
          language: "en",
          outputs: [bareSlot("post"), bareSlot("quotes"), bareSlot("article")],
          dub_languages: [],
          specific_instruction: prompt,
        }
  )
  // The plan card renders only once a real inference has landed (the
  // composer normally hands one over; the fetch below is the fallback).
  // Attach mode never shows the card, so it starts ready.
  const [intentReady, setIntentReady] = useState(!!initialIntent || !!initialRunId)
  const [runId, setRunId] = useState<string | null>(initialRunId ?? null)
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
  const [chatBusy, setChatBusy] = useState(false)
  const [isComposing, setIsComposing] = useState(false)
  // Source materials shown as attachments on the opening prompt.
  const [assets, setAssets] = useState<ProjectAsset[]>([])
  // Identity echo line (speaker voice + brand skin) — resolved once.
  const [identity, setIdentity] = useState<{ speaker: string | null; brand: string | null }>({
    speaker: null,
    brand: null,
  })

  const autoStartedRef = useRef(false)
  const intentFetchedRef = useRef(false)
  const followUpsRef = useRef<string[]>([])
  const abortRef = useRef<AbortController | null>(null)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  const { steps, status, terminal, summary } = useRunEvents(runId)

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
          items?: (QuestionMessage & { role: "user" | "assistant" })[]
        }
        const history: OverlayMessage[] = []
        for (const m of data.items ?? []) {
          if (m.role === "user") {
            if ((m.content ?? "") === prompt) continue
            history.push({ id: m.id, role: "user", content: m.content ?? "" })
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

  // Load the project's assets once for the prompt attachments.
  useEffect(() => {
    let cancelled = false
    apiFetch(`/api/v1/projects/${projectId}/assets`, { toast: false })
      .then((res) => (res.ok ? res.json() : []))
      .then((data: ProjectAsset[]) => {
        if (!cancelled) setAssets(data)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [projectId])

  // Identity echo: resolve the speaker / brand names behind the ids once —
  // a read-only reassurance line, never a question (ask primitive §2.1).
  useEffect(() => {
    let cancelled = false
    Promise.all([
      apiFetch(`/api/v1/projects/${projectId}`, { toast: false })
        .then((res) => (res.ok ? res.json() : null))
        .catch(() => null),
      apiFetch("/api/v1/speakers", { toast: false })
        .then((res) => (res.ok ? res.json() : []))
        .catch(() => []),
      apiFetch("/api/v1/brand-templates", { toast: false })
        .then((res) => (res.ok ? res.json() : []))
        .catch(() => []),
    ]).then(([project, speakers, brands]) => {
      if (cancelled) return
      const speaker =
        (speakers as { id: string; name: string }[]).find(
          (s) => s.id === (project as { speaker_id?: string } | null)?.speaker_id
        )?.name ?? null
      const brand =
        (brands as { id: string; name: string }[]).find((b) => b.id === brandTemplateId)
          ?.name ?? null
      setIdentity({ speaker, brand })
    })
    return () => {
      cancelled = true
    }
  }, [projectId, brandTemplateId])

  // Terminal: success hands off to the results page; failure stays put so
  // the step list shows what broke (the results page carries the retry).
  useEffect(() => {
    if (!terminal) return
    if (status === "failed") {
      toast.error(t("generationOverlay.failed"))
      return
    }
    toast.success(t("generationOverlay.completed"))
    onCompleteRef.current()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [terminal])

  /** Shared landing for every path that starts a run (the dock's Start
   * button, a prose confirmation via /intent): the answered task book
   * archives as QA, the dock clears, and the step flow takes over. */
  const landOnStartedRun = useCallback((runId: string, answered: QuestionMessage | null) => {
    setPendingQuestion(null)
    if (answered) setAnsweredQuestion(answered)
    setRunId(runId)
    setPhase("running")
  }, [])

  const handleStartGeneration = useCallback(async () => {
    if (runId || isStarting) return
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
          target_language: intent.language,
          dub_languages: intent.dub_languages,
          instruction: intent.specific_instruction || prompt,
          brand_template_id: brandTemplateId || undefined,
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
  }, [runId, isStarting, pendingQuestion, autonomy, intent, projectId, prompt, brandTemplateId, t, landOnStartedRun])

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

  // Fallback intent fetch (direct visit without a composer-provided intent).
  // Guarded by ref — setIntent recreates handleStartGeneration, which would
  // otherwise retrigger this effect forever. Attach mode skips it entirely:
  // the run is already going, there is no plan to infer.
  useEffect(() => {
    if (initialIntent || initialRunId || intentFetchedRef.current) return
    intentFetchedRef.current = true
    apiFetch(`/api/v1/projects/${projectId}/intent`, {
      method: "POST",
      body: { prompt },
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: IntentTurnResponse | null) => {
        if (!data) throw new Error(t("generationOverlay.failed"))
        if (data.type === "started") {
          // Defensive: a restored session's prose confirmation may start the
          // run straight from the fallback fetch.
          landOnStartedRun(data.run_id, data.answered_question)
          setIntentReady(true)
          return
        }
        if (data.type === "answer") {
          // Capability answer — archived server-side; show it in the flow.
          pushMessage({ role: "assistant", content: data.text })
          setPhase("answer")
          setIntentReady(true)
          return
        }
        setIntent(normalizeIntent(data.intent))
        setReasons(data.reasons ?? [])
        setIntentReady(true)
        if ((data.reasons ?? []).length === 0) {
          handleStartGeneration()
        }
      })
      .catch((e) => {
        // Degrade to the editable defaults — Start still works without the
        // intent endpoint.
        setStartError(e instanceof Error ? e.message : t("generationOverlay.failed"))
        setIntentReady(true)
      })
  }, [initialIntent, projectId, prompt, t, handleStartGeneration, landOnStartedRun])

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

  const canStartGeneration = intent.outputs.length > 0 && !!intent.language

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
      outputs: [...prev.outputs, { ...bareSlot(type), explicit: true }],
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

  const planSummary = useMemo(() => {
    const parts = [
      intent.outputs.map(slotLabel).join(", "),
      t(`languages.${intent.language}`, { defaultValue: intent.language }),
    ]
    if (intent.dub_languages.length > 0) {
      parts.push(
        t("generationOverlay.planSummaryDub", {
          langs: intent.dub_languages
            .map((l) => t(`languages.${l}`, { defaultValue: l }))
            .join(", "),
        })
      )
    }
    return parts.join(" · ")
  }, [intent, slotLabel, t])

  const pushMessage = (message: Omit<OverlayMessage, "id">) => {
    setMessages((prev) => [...prev, { ...message, id: crypto.randomUUID() }])
  }

  /** Confirm-phase turn: refine the plan via intent re-inference. The panel's
   * current (possibly hand-edited) book rides along — its explicit slots pin
   * through the merge. A question (action="answer") is answered inline and
   * leaves the plan untouched; a prose confirmation (action="start") starts
   * the run like the dock's Start button. */
  const sendPlanRefinement = async (text: string) => {
    followUpsRef.current.push(text)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setChatBusy(true)
    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/intent`, {
        method: "POST",
        body: {
          prompt: [prompt, ...followUpsRef.current].join("\n"),
          prior: intent,
          turn: text,
          // Consumed only when this turn starts the run (action="start") —
          // the dock's tier must survive a prose confirmation.
          autonomy,
        },
        toast: false,
        signal: ctrl.signal,
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail.detail || t("generationOverlay.failed"))
      }
      const data = (await res.json()) as IntentTurnResponse
      if (data.type === "started") {
        // G-1: the prose confirmation answered the docked task book
        // server-side (kind=start) and the run is live.
        landOnStartedRun(data.run_id, data.answered_question)
        return
      }
      if (data.type === "answer") {
        // Capability answer — the exchange is also archived server-side (B1).
        pushMessage({ role: "assistant", content: data.text })
      } else {
        setReasons(data.reasons ?? [])
        setIntent(normalizeIntent(data.intent))
        setIntentReady(true)
        // The refinement superseded the old question server-side and raised
        // a new one — the dock must point at the new row.
        setPendingQuestion(await fetchPendingQuestion())
        pushMessage({ role: "assistant", content: t("generationOverlay.planUpdated") })
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return
      pushMessage({
        role: "assistant",
        content: e instanceof Error ? e.message : t("generationOverlay.failed"),
      })
    } finally {
      // Identity guard: after a manual stop a newer request may already own
      // the busy state — only the owning request clears it.
      if (abortRef.current === ctrl) {
        abortRef.current = null
        setChatBusy(false)
      }
    }
  }

  /** An answered question collapses into the flow as a QA pair (ask
   * primitive: the flow archives decisions, the dock holds the open one). */
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
      },
    })
  }

  /** The chat loop's reply: a pending question docks (never enters the
   * flow, prohibited-behavior #2); anything else renders as prose + an
   * optional RunCard. */
  const handleAssistantMessage = (message: QuestionMessage) => {
    if (message.question && !message.answer) {
      setPendingQuestion(message)
      return
    }
    pushMessage({
      role: "assistant",
      content: message.content ?? "",
      runId: message.workflow_run_id,
    })
  }

  /** Post-start turn: the project-scoped chat loop (CHAT_ARCH §3). A task
   * list dispatch comes back with a run_id and renders as a RunCard; a
   * pending choice question docks; an autoResumed one archives its QA. */
  const sendProjectChat = async (text: string) => {
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setChatBusy(true)
    try {
      const res = await apiFetch("/api/v1/chat", {
        method: "POST",
        body: { project_id: projectId, message: text },
        toast: false,
        signal: ctrl.signal,
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail.detail || t("chat.failed"))
      }
      const data = (await res.json()) as {
        assistant_message: QuestionMessage
        run_id: string | null
        answered_question?: QuestionMessage | null
      }
      // Deterministic autoResume settled the docked question with this very
      // text — archive its QA pair before the assistant's continuation.
      if (data.answered_question) {
        setPendingQuestion(null)
        pushQaArchive(data.answered_question)
      }
      handleAssistantMessage(data.assistant_message)
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return
      pushMessage({
        role: "assistant",
        content: e instanceof Error ? e.message : t("chat.failed"),
      })
    } finally {
      if (abortRef.current === ctrl) {
        abortRef.current = null
        setChatBusy(false)
      }
    }
  }

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
      if (data.follow_up) handleAssistantMessage(data.follow_up)
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
    if (!text || chatBusy) return
    pushMessage({ role: "user", content: text })
    setInput("")
    if (phase === "confirm") {
      void sendPlanRefinement(text)
    } else {
      void sendProjectChat(text)
    }
  }

  const handleClose = () => {
    if (phase === "running" && !terminal) {
      toast.info(t("generationOverlay.continuesInBackground"))
    }
    onClose()
  }

  // Esc mirrors the back pill.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, terminal])

  const sectionLabel = "text-[11px] font-medium uppercase tracking-wider text-muted-foreground"

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

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      {/* Back pill — floats over the scroll column, Opus-style: a plain
          rounded bg block, no shadow. */}
      <div className="absolute left-4 top-4 z-10">
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

      {/* Chat column */}
      <div className="min-h-0 flex-1">
        <MessageScrollerProvider>
          <MessageScroller className="h-full">
            <MessageScrollerViewport>
              <MessageScrollerContent className="mx-auto w-full max-w-3xl gap-8 px-4 pb-8 pt-16">
                {/* Opening prompt */}
                {prompt ? (
                  <MessageScrollerItem>
                    <UserBubble text={prompt} assets={assets} />
                  </MessageScrollerItem>
                ) : null}

                {/* Answer intent: the reply is the whole conversation opener. */}
                {phase === "answer" && (
                  <MessageScrollerItem>
                    <AssistantText text={intent.answer || t("chat.intro")} />
                  </MessageScrollerItem>
                )}

                {/* Plan card (pinned while confirming) */}
                {phase !== "answer" && !intentReady && (
                  <MessageScrollerItem>
                    <ThinkingRow label={t("chat.thinking")} />
                  </MessageScrollerItem>
                )}
                {phase === "confirm" && intentReady && (
                  <MessageScrollerItem>
                    <Message align="start">
                      <MessageContent>
                        <div className="w-full">
                          {/* Prose echo of the understood plan — the card
                              never lands naked (Opus pattern). */}
                          <p className="mb-3 max-w-[85%] text-sm leading-relaxed">
                            {t("generationOverlay.planProse", { summary: planSummary })}
                          </p>
                          {/* No shadow/glow here: the scroller's paint
                              containment clips the halo on the sides (it
                              survived only on top, looking like a cut-off
                              shadow). Depth comes from bg contrast alone. */}
                          <Card className="ring-0 bg-muted/50">
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
                                  question: whose voice, which brand skin. */}
                              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                                <Mic2 className="h-3.5 w-3.5" />
                                {t("generationOverlay.identityEcho", {
                                  speaker:
                                    identity.speaker ??
                                    t("generationOverlay.identitySpeakerAuto"),
                                  brand:
                                    identity.brand ??
                                    t("generationOverlay.identityBrandDefault"),
                                })}
                              </p>

                              {/* Task-book language (slot-level "same as book"
                                  overrides live on each slot row) */}
                              <div className="flex flex-col gap-4">
                                <span className={sectionLabel}>
                                  {t("generationOverlay.languageLabel")}
                                </span>
                                <Select
                                  value={intent.language}
                                  onValueChange={(value) =>
                                    setIntent((prev) => ({
                                      ...prev,
                                      language: (value as string) || "en",
                                    }))
                                  }
                                >
                                  <SelectTrigger className="h-10 w-full text-sm">
                                    <SelectValue>
                                      {(value: string) =>
                                        t(`languages.${value}`, { defaultValue: value })
                                      }
                                    </SelectValue>
                                  </SelectTrigger>
                                  <SelectContent>
                                    {LANGUAGE_OPTIONS.map((lang) => (
                                      <SelectItem key={lang.code} value={lang.code}>
                                        {t(lang.labelKey)}
                                      </SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                                <p className="text-xs text-muted-foreground">
                                  {t("generationOverlay.languageHint")}
                                </p>
                              </div>

                              {/* Task slots — one row per requested output.
                                  Same-type siblings (e.g. an English and a
                                  German post) are separate rows. */}
                              <div className="flex flex-col gap-4">
                                <span className={sectionLabel}>
                                  {t("generationOverlay.outputsLabel")}
                                </span>
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
                                        className="flex flex-col gap-2 rounded-md bg-background/60 p-3"
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
                                              value={slot.language ?? BOOK_LANGUAGE}
                                              onValueChange={(value) =>
                                                updateSlot(index, {
                                                  language:
                                                    value === BOOK_LANGUAGE
                                                      ? null
                                                      : (value as string),
                                                })
                                              }
                                            >
                                              <SelectTrigger className="h-8 w-28 text-xs">
                                                <SelectValue>
                                                  {(value: string) =>
                                                    value === BOOK_LANGUAGE
                                                      ? t(
                                                          "generationOverlay.slotLanguageDefault"
                                                        )
                                                      : t(`languages.${value}`, {
                                                          defaultValue: value,
                                                        })
                                                  }
                                                </SelectValue>
                                              </SelectTrigger>
                                              <SelectContent>
                                                <SelectItem value={BOOK_LANGUAGE}>
                                                  {t(
                                                    "generationOverlay.slotLanguageDefault"
                                                  )}
                                                </SelectItem>
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

                              {/* Voice dub languages (dub_languages) — one
                                  chip per forked voice-over version. Chips
                                  are removable (down to none = no dubbing);
                                  adding a language goes through chat refine,
                                  not panel editing (R1 scope). */}
                              {intent.dub_languages.length > 0 && (
                                <div className="flex flex-col gap-4">
                                  <span className={sectionLabel}>
                                    {t("generationOverlay.dubLabel")}
                                  </span>
                                  <div className="flex flex-wrap gap-2">
                                    {intent.dub_languages.map((lang) => (
                                      <span
                                        key={lang}
                                        className="flex items-center gap-1.5 rounded-md bg-background/60 px-2.5 py-1.5 text-sm"
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
                                </div>
                              )}

                              {/* Instruction */}
                              <div className="flex flex-col gap-4">
                                <span className={sectionLabel}>
                                  {t("generationOverlay.instructionLabel")}
                                </span>
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
                            <div className="flex w-full items-center gap-3 rounded-lg bg-muted/50 px-4 py-3">
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
                            <p className="max-w-[85%] text-sm leading-relaxed">
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

                {/* Conversation below the pinned regions */}
                {messages.map((m) => (
                  <MessageScrollerItem key={m.id}>
                    {m.qa ? (
                      <QaPair
                        question={m.qa.question}
                        answer={m.qa.answer}
                        muted={m.qa.muted}
                      />
                    ) : m.role === "user" ? (
                      <UserBubble text={m.content} />
                    ) : (
                      <>
                        {m.content ? <AssistantText text={m.content} /> : null}
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
                ))}

                {chatBusy && (
                  <MessageScrollerItem>
                    <ThinkingRow label={t("chat.thinking")} />
                  </MessageScrollerItem>
                )}
              </MessageScrollerContent>
            </MessageScrollerViewport>
          </MessageScroller>
        </MessageScrollerProvider>
      </div>

      {/* Bottom input — one floating bar in the chat column's width. The
          pending question docks directly above it (ask primitive): the flow
          archives decisions, the dock holds the one still open. */}
      <div className="shrink-0 px-4 pb-5 pt-2">
        <div className="mx-auto w-full max-w-3xl">
          {phase === "confirm" && intentReady && (
            <QuestionDock
              kind="task_book"
              question={t("generationOverlay.confirmQuestion")}
              reasons={reasons}
              autonomy={autonomy}
              onAutonomyChange={setAutonomy}
              onStart={handleStartGeneration}
              onCancel={handleCancel}
              starting={isStarting}
              startDisabled={!canStartGeneration}
            />
          )}
          {phase !== "confirm" && pendingChoice && (
            <QuestionDock
              kind="choice"
              question={pendingChoice.content ?? ""}
              options={pendingChoice.question?.options ?? []}
              costHint={pendingChoice.question?.cost_hint}
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
          <div className="flex items-end gap-2 rounded-lg bg-muted/50 p-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onCompositionStart={() => setIsComposing(true)}
              onCompositionEnd={() => setIsComposing(false)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !isComposing) {
                  e.preventDefault()
                  handleSend()
                }
              }}
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
              rows={1}
              className="max-h-32 min-h-9 flex-1 resize-none border-0 bg-transparent text-sm shadow-none focus-visible:ring-0 dark:bg-transparent"
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
                disabled={!input.trim()}
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
  )
}
