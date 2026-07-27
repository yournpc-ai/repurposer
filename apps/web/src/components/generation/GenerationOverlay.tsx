"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  Check,
  FileText,
  Image as ImageIcon,
  Loader2,
  Mic2,
  Palette,
  Video,
  X,
} from "lucide-react"

import { apiFetch } from "@/lib/api"
import { useRunEvents } from "@/lib/use-run-events"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Bubble,
  BubbleContent,
  BubbleGroup,
} from "@/components/ui/bubble"
import {
  Message,
  MessageAvatar,
  MessageContent,
  MessageGroup,
} from "@/components/ui/message"
import {
  Marker,
  MarkerContent,
  MarkerIcon,
} from "@/components/ui/marker"
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

const OUTPUT_OPTIONS = [
  { key: "clips", labelKey: "results.tabs.clips" },
  { key: "post", labelKey: "results.tabs.post" },
  { key: "quotes", labelKey: "results.tabs.quotes" },
  { key: "article", labelKey: "results.tabs.article" },
  { key: "carousel", labelKey: "results.tabs.carousel" },
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

interface GenerationOverlayProps {
  projectId: string
  prompt: string
  initialIntent?: InferredIntent | null
  initialNeedsClarification?: boolean
  brandTemplateId?: string
  onClose: () => void
  onComplete: () => void
}

function OutputTypeIcon({ type }: { type: string }) {
  switch (type) {
    case "video":
    case "clips":
      return <Video className="h-4 w-4" />
    case "audio":
      return <Mic2 className="h-4 w-4" />
    case "image":
      return <ImageIcon className="h-4 w-4" />
    default:
      return <FileText className="h-4 w-4" />
  }
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
      <MarkerContent className={status === "running" ? "animate-pulse" : undefined}>
        {label}
        {status === "failed" && error ? ` — ${error}` : ""}
      </MarkerContent>
    </Marker>
  )
}

export function GenerationOverlay({
  projectId,
  prompt,
  initialIntent,
  initialNeedsClarification = true,
  brandTemplateId,
  onClose,
  onComplete,
}: GenerationOverlayProps) {
  const { t } = useTranslation()

  const [phase, setPhase] = useState<Phase>(
    initialIntent?.action === "answer" ? "answer" : "confirm"
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
  const [_needsClarification, setNeedsClarification] = useState(
    initialNeedsClarification
  )
  const [runId, setRunId] = useState<string | null>(null)
  const [startError, setStartError] = useState<string | null>(null)
  const autoStartedRef = useRef(false)

  const { steps, status, terminal, summary } = useRunEvents(
    runId,
    () => {
      toast.success(t("generationOverlay.completed"))
      onComplete()
    }
  )

  const handleStartGeneration = useCallback(async () => {
    if (runId) return
    setStartError(null)
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
    }
  }, [runId, intent, projectId, prompt, brandTemplateId, t])

  useEffect(() => {
    if (!initialIntent) {
      apiFetch(`/api/v1/projects/${projectId}/intent`, {
        method: "POST",
        body: { prompt },
      })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (!data) return
          setIntent({ ...data.intent })
          setNeedsClarification(data.needs_clarification)
          if (data.intent.action === "answer") {
            setPhase("answer")
          } else if (!data.needs_clarification) {
            handleStartGeneration()
          }
        })
        .catch(() => {
          setStartError(t("generationOverlay.failed"))
        })
    }
  }, [initialIntent, projectId, prompt, t, handleStartGeneration])

  useEffect(() => {
    if (
      initialIntent &&
      initialIntent.action === "generate" &&
      !initialNeedsClarification &&
      phase === "confirm" &&
      !autoStartedRef.current
    ) {
      autoStartedRef.current = true
      handleStartGeneration()
    }
  }, [initialIntent, initialNeedsClarification, phase, handleStartGeneration])

  const toggleOutput = (key: OutputKey) => {
    setIntent((prev) => {
      const outputs = prev.outputs.includes(key)
        ? prev.outputs.filter((o) => o !== key)
        : [...prev.outputs, key]
      return { ...prev, outputs }
    })
  }

  const canStartGeneration = useMemo(() => {
    return intent.outputs.length > 0 && intent.language
  }, [intent])

  const handleClose = () => {
    if (phase === "running" && !terminal) {
      toast.info(t("generationOverlay.continuesInBackground"))
    }
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={handleClose}
            aria-label={t("generationOverlay.close")}
          >
            <X className="h-4 w-4" />
          </Button>
          <h2 className="text-sm font-medium">
            {t("generationOverlay.title")}
          </h2>
        </div>
      </header>

      {/* Chat area */}
      <div className="min-h-0 flex-1">
        <MessageScrollerProvider>
          <MessageScroller className="h-full">
            <MessageScrollerViewport>
              <MessageScrollerContent className="px-6 py-8">
                <MessageGroup>
                  {/* User message */}
                  <MessageScrollerItem>
                    <Message align="end">
                      <MessageContent>
                        <BubbleGroup>
                          <Bubble variant="muted" align="end">
                            <BubbleContent>
                              <p className="whitespace-pre-wrap">{prompt}</p>
                            </BubbleContent>
                          </Bubble>
                        </BubbleGroup>
                      </MessageContent>
                    </Message>
                  </MessageScrollerItem>

                  {/* Confirm / answer message */}
                  {phase === "answer" ? (
                    <MessageScrollerItem>
                      <Message align="start">
                        <MessageAvatar>
                          <Palette className="h-4 w-4" />
                        </MessageAvatar>
                        <MessageContent>
                          <Bubble variant="secondary">
                            <BubbleContent>
                              <p className="whitespace-pre-wrap">
                                {intent.answer || t("chat.intro")}
                              </p>
                              <div className="mt-4 flex justify-end">
                                <Button size="sm" onClick={handleClose}>
                                  {t("common.back")}
                                </Button>
                              </div>
                            </BubbleContent>
                          </Bubble>
                        </MessageContent>
                      </Message>
                    </MessageScrollerItem>
                  ) : (
                    <MessageScrollerItem>
                      <Message align="start">
                        <MessageAvatar>
                          <Palette className="h-4 w-4" />
                        </MessageAvatar>
                        <MessageContent>
                          <Bubble variant="secondary">
                            <BubbleContent className="min-w-[280px] max-w-[420px]">
                              <p className="mb-4 text-sm">
                                {t("generationOverlay.taskSummary")}
                              </p>

                              {/* Outputs */}
                              <div className="mb-4">
                                <label className="mb-2 block text-xs text-muted-foreground">
                                  {t("generationOverlay.outputsLabel")}
                                </label>
                                <div className="flex flex-wrap gap-2">
                                  {OUTPUT_OPTIONS.map((option) => {
                                    const active = intent.outputs.includes(option.key)
                                    return (
                                      <button
                                        key={option.key}
                                        type="button"
                                        onClick={() => toggleOutput(option.key)}
                                        className={`
                                          flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs transition-colors
                                          ${
                                            active
                                              ? "border-primary bg-primary/10 text-primary"
                                              : "border-border bg-background text-muted-foreground hover:bg-accent"
                                          }
                                        `}
                                      >
                                        <OutputTypeIcon type={option.key} />
                                        <span>{t(option.labelKey)}</span>
                                      </button>
                                    )
                                  })}
                                </div>
                              </div>

                              {/* Language */}
                              <div className="mb-4">
                                <label className="mb-2 block text-xs text-muted-foreground">
                                  {t("generationOverlay.languageLabel")}
                                </label>
                                <Select
                                  value={intent.language}
                                  onValueChange={(value) =>
                                    setIntent((prev) => ({
                                      ...prev,
                                      language: (value as string) || "en",
                                    }))
                                  }
                                >
                                  <SelectTrigger className="w-full">
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent>
                                    {LANGUAGE_OPTIONS.map((lang) => (
                                      <SelectItem key={lang.code} value={lang.code}>
                                        {t(lang.labelKey)}
                                      </SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                              </div>

                              {/* Clip count */}
                              {intent.outputs.includes("clips") && (
                                <div className="mb-4">
                                  <label className="mb-2 block text-xs text-muted-foreground">
                                    {t("generationOverlay.clipCountLabel")}
                                  </label>
                                  <Input
                                    type="number"
                                    min={1}
                                    max={10}
                                    value={intent.clip_count ?? 5}
                                    onChange={(e) =>
                                      setIntent((prev) => ({
                                        ...prev,
                                        clip_count: parseInt(e.target.value, 10) || 1,
                                      }))
                                    }
                                    className="h-9 text-xs"
                                  />
                                </div>
                              )}

                              {/* Instruction */}
                              <div className="mb-4">
                                <label className="mb-2 block text-xs text-muted-foreground">
                                  {t("generationOverlay.instructionLabel")}
                                </label>
                                <Textarea
                                  value={intent.specific_instruction || ""}
                                  onChange={(e) =>
                                    setIntent((prev) => ({
                                      ...prev,
                                      specific_instruction: e.target.value,
                                    }))
                                  }
                                  className="min-h-[80px] resize-none text-xs"
                                />
                              </div>

                              {startError && (
                                <p className="mb-4 text-xs text-destructive">
                                  {startError}
                                </p>
                              )}

                              <Button
                                size="sm"
                                className="w-full"
                                disabled={!canStartGeneration}
                                onClick={handleStartGeneration}
                              >
                                {t("generationOverlay.confirm")}
                              </Button>
                            </BubbleContent>
                          </Bubble>
                        </MessageContent>
                      </Message>
                    </MessageScrollerItem>
                  )}

                  {/* Running checklist */}
                  {phase === "running" && (
                    <MessageScrollerItem>
                      <Message align="start">
                        <MessageAvatar>
                          <Palette className="h-4 w-4" />
                        </MessageAvatar>
                        <MessageContent>
                          <Bubble variant="secondary">
                            <BubbleContent className="min-w-[280px]">
                              <p className="mb-3 text-sm">
                                {t("generationOverlay.started")}
                              </p>
                              <div className="flex flex-col gap-1">
                                {steps.map((step) => (
                                  <StepMarker
                                    key={step.id}
                                    status={step.status}
                                    label={
                                      step.summary ||
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
                                  <Marker variant="border" className="pt-2 text-destructive">
                                    <MarkerContent>
                                      {t("generationOverlay.failed")}
                                    </MarkerContent>
                                  </Marker>
                                )}
                              </div>
                            </BubbleContent>
                          </Bubble>
                        </MessageContent>
                      </Message>
                    </MessageScrollerItem>
                  )}
                </MessageGroup>
              </MessageScrollerContent>
            </MessageScrollerViewport>
          </MessageScroller>
        </MessageScrollerProvider>
      </div>
    </div>
  )
}
