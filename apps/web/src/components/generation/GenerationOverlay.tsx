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
  FileText,
  Image as ImageIcon,
  Images,
  Loader2,
  Mic2,
  Minus,
  Newspaper,
  Plus,
  Quote,
  Sparkles,
  Square,
  Video,
  X,
} from "lucide-react"

import { apiFetch } from "@/lib/api"
import { useRunEvents } from "@/lib/use-run-events"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Bubble, BubbleContent, BubbleGroup } from "@/components/ui/bubble"
import { Message, MessageContent } from "@/components/ui/message"
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

type OutputKey = (typeof OUTPUT_OPTIONS)[number]["key"]
type Phase = "confirm" | "running" | "answer"

interface InferredIntent {
  action: "generate" | "answer"
  answer: string | null
  language: string
  outputs: string[]
  clip_count: number | null
  specific_instruction: string | null
}

interface OverlayMessage {
  id: string
  role: "user" | "assistant"
  content: string
  runId?: string | null
}

interface ProjectAsset {
  id: string
  type: string
  file_url: string | null
  title: string | null
  processing_status: "pending" | "processing" | "completed" | "failed"
}

const ATTACHMENT_STATE: Record<
  ProjectAsset["processing_status"],
  "uploading" | "processing" | "error" | "done"
> = {
  pending: "uploading",
  processing: "processing",
  failed: "error",
  completed: "done",
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
                  state={ATTACHMENT_STATE[asset.processing_status] ?? "done"}
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
          <Sparkles className="h-3.5 w-3.5 animate-pulse" />
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
      ? { ...initialIntent }
      : {
          action: "generate",
          answer: null,
          language: "en",
          outputs: ["post", "quotes", "article"],
          clip_count: 5,
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

  // Conversation below the pinned regions (plan card / progress).
  const [messages, setMessages] = useState<OverlayMessage[]>([])
  const [input, setInput] = useState("")
  const [chatBusy, setChatBusy] = useState(false)
  const [isComposing, setIsComposing] = useState(false)
  // Source materials shown as attachments on the opening prompt.
  const [assets, setAssets] = useState<ProjectAsset[]>([])

  const autoStartedRef = useRef(false)
  const intentFetchedRef = useRef(false)
  const followUpsRef = useRef<string[]>([])
  const abortRef = useRef<AbortController | null>(null)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  const { steps, status, terminal, summary } = useRunEvents(runId)

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

  const handleStartGeneration = useCallback(async () => {
    if (runId || isStarting) return
    setStartError(null)
    setIsStarting(true)
    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/generate`, {
        method: "POST",
        body: {
          outputs: intent.outputs,
          target_language: intent.language,
          clip_count: intent.outputs.includes("clips")
            ? intent.clip_count ?? 5
            : undefined,
          instruction: intent.specific_instruction || prompt,
          brand_template_id: brandTemplateId || undefined,
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
  }, [runId, isStarting, intent, projectId, prompt, brandTemplateId, t])

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
      .then((data) => {
        if (!data) throw new Error(t("generationOverlay.failed"))
        setIntent({ ...data.intent })
        setIntentReady(true)
        if (data.intent.action === "answer") {
          setPhase("answer")
        } else if (!data.needs_clarification) {
          handleStartGeneration()
        }
      })
      .catch((e) => {
        // Degrade to the editable defaults — Start still works without the
        // intent endpoint.
        setStartError(e instanceof Error ? e.message : t("generationOverlay.failed"))
        setIntentReady(true)
      })
  }, [initialIntent, projectId, prompt, t, handleStartGeneration])

  useEffect(() => {
    if (
      initialIntent &&
      !initialRunId &&
      initialIntent.action === "generate" &&
      !initialNeedsClarification &&
      phase === "confirm" &&
      !autoStartedRef.current
    ) {
      autoStartedRef.current = true
      handleStartGeneration()
    }
  }, [initialIntent, initialRunId, initialNeedsClarification, phase, handleStartGeneration])

  const toggleOutput = (key: OutputKey) => {
    setIntent((prev) => {
      const outputs = prev.outputs.includes(key)
        ? prev.outputs.filter((o) => o !== key)
        : [...prev.outputs, key]
      return { ...prev, outputs }
    })
  }

  const canStartGeneration = intent.outputs.length > 0 && !!intent.language

  const planSummary = useMemo(() => {
    const parts = [
      intent.outputs
        .map((o) => t(`results.tabs.${o}`, { defaultValue: o }))
        .join(", "),
      t(`languages.${intent.language}`, { defaultValue: intent.language }),
    ]
    if (intent.outputs.includes("clips") && intent.clip_count) {
      parts.push(t("generationOverlay.planSummaryClips", { count: intent.clip_count }))
    }
    return parts.join(" · ")
  }, [intent, t])

  // One-line plain-language summary of the selected outputs, shown under the
  // toggle pills so a first-time user learns what each output is.
  const selectedOutputDescs = useMemo(
    () =>
      intent.outputs
        .map((o) => t(`generationOverlay.outputDescs.${o}`, { defaultValue: "" }))
        .filter(Boolean),
    [intent.outputs, t]
  )

  const clipCount = intent.clip_count ?? 5
  const setClipCount = (next: number) =>
    setIntent((prev) => ({
      ...prev,
      clip_count: Math.min(10, Math.max(1, next)),
    }))

  const pushMessage = (message: Omit<OverlayMessage, "id">) => {
    setMessages((prev) => [...prev, { ...message, id: crypto.randomUUID() }])
  }

  /** Confirm-phase turn: refine the plan via intent re-inference. A question
   * (action="answer") is answered inline and leaves the plan untouched. */
  const sendPlanRefinement = async (text: string) => {
    followUpsRef.current.push(text)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setChatBusy(true)
    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/intent`, {
        method: "POST",
        body: { prompt: [prompt, ...followUpsRef.current].join("\n") },
        toast: false,
        signal: ctrl.signal,
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail.detail || t("generationOverlay.failed"))
      }
      const data = await res.json()
      if (data.intent.action === "answer" && data.intent.answer) {
        pushMessage({ role: "assistant", content: data.intent.answer })
      } else {
        setIntent({ ...data.intent })
        setIntentReady(true)
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

  /** Post-start turn: the project-scoped chat loop (CHAT_ARCH §3). A task
   * list dispatch comes back with a run_id and renders as a RunCard. */
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
        assistant_message: { content: string | null }
        run_id: string | null
      }
      pushMessage({
        role: "assistant",
        content: data.assistant_message.content ?? "",
        runId: data.run_id,
      })
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
                            <div className="flex flex-col gap-6 p-6">
                              <div className="space-y-1">
                                <h3 className="text-base font-semibold">
                                  {t("generationOverlay.title")}
                                </h3>
                                <p className="text-sm text-muted-foreground">
                                  {t("generationOverlay.subtitle")}
                                </p>
                              </div>

                              {/* Outputs */}
                              <div className="space-y-2">
                                <span className={sectionLabel}>
                                  {t("generationOverlay.outputsLabel")}
                                </span>
                                <div className="flex flex-wrap gap-2">
                                  {OUTPUT_OPTIONS.map(({ key, labelKey, Icon }) => {
                                    const active = intent.outputs.includes(key)
                                    return (
                                      <button
                                        key={key}
                                        type="button"
                                        onClick={() => toggleOutput(key)}
                                        className={`flex h-9 items-center gap-1.5 rounded-md px-3 text-xs transition-colors ${
                                          active
                                            ? "bg-foreground text-background"
                                            : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground"
                                        }`}
                                      >
                                        <Icon className="h-3.5 w-3.5" />
                                        <span>{t(labelKey)}</span>
                                      </button>
                                    )
                                  })}
                                </div>
                                {selectedOutputDescs.length > 0 && (
                                  <p className="text-xs text-muted-foreground">
                                    {selectedOutputDescs.join(" · ")}
                                  </p>
                                )}
                              </div>

                              {/* Language + clip count share a row on sm+ */}
                              <div
                                className={`grid grid-cols-1 gap-6 ${
                                  intent.outputs.includes("clips") ? "sm:grid-cols-2" : ""
                                }`}
                              >
                                <div className="space-y-2">
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

                                {intent.outputs.includes("clips") && (
                                  <div className="space-y-2">
                                    <span className={sectionLabel}>
                                      {t("generationOverlay.clipCountLabel")}
                                    </span>
                                    <div className="flex h-10 items-center gap-2">
                                      <Button
                                        variant="outline"
                                        size="icon"
                                        className="h-9 w-9"
                                        disabled={clipCount <= 1}
                                        aria-label={t("generationOverlay.clipCountDecrease")}
                                        onClick={() => setClipCount(clipCount - 1)}
                                      >
                                        <Minus className="h-4 w-4" />
                                      </Button>
                                      <span className="flex h-9 w-12 items-center justify-center text-sm tabular-nums">
                                        {clipCount}
                                      </span>
                                      <Button
                                        variant="outline"
                                        size="icon"
                                        className="h-9 w-9"
                                        disabled={clipCount >= 10}
                                        aria-label={t("generationOverlay.clipCountIncrease")}
                                        onClick={() => setClipCount(clipCount + 1)}
                                      >
                                        <Plus className="h-4 w-4" />
                                      </Button>
                                    </div>
                                    <p className="text-xs text-muted-foreground">
                                      {t("generationOverlay.clipCountHint")}
                                    </p>
                                  </div>
                                )}
                              </div>

                              {/* Instruction */}
                              <div className="space-y-2">
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

                              {startError && (
                                <p className="text-sm text-destructive">{startError}</p>
                              )}

                              {/* Confirm footer — inside the card (Opus-style),
                                  not a separate floating bar. "Decide later"
                                  just closes: the plan is persisted server-side
                                  and can be resumed from the projects list. */}
                              <div className="space-y-2">
                                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                  <div className="flex min-w-0 items-center gap-2 text-sm">
                                    <Check className="h-4 w-4 shrink-0 text-green-600 dark:text-green-400" />
                                    {t("generationOverlay.confirmQuestion")}
                                  </div>
                                  <div className="flex shrink-0 items-center gap-2">
                                    <Button variant="ghost" onClick={handleClose}>
                                      {t("generationOverlay.decideLater")}
                                    </Button>
                                    <Button
                                      disabled={!canStartGeneration || isStarting}
                                      onClick={handleStartGeneration}
                                    >
                                      {isStarting && (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                      )}
                                      {isStarting
                                        ? t("generationOverlay.starting")
                                        : t("generationOverlay.confirm")}
                                    </Button>
                                  </div>
                                </div>
                                <p className="text-xs text-muted-foreground">
                                  {t("generationOverlay.leaveNote")}
                                </p>
                              </div>
                            </div>
                          </Card>
                        </div>
                      </MessageContent>
                    </Message>
                  </MessageScrollerItem>
                )}

                {/* Running: confirmed plan collapses to a summary line, the
                    live steps light up below it. */}
                {phase === "running" && (
                  <>
                    <MessageScrollerItem>
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
                    {m.role === "user" ? (
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

      {/* Bottom input — one floating bar in the chat column's width. */}
      <div className="shrink-0 px-4 pb-5 pt-2">
        <div className="mx-auto w-full max-w-3xl">
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
                phase === "confirm"
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
