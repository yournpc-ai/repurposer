"use client"

import { Link, useNavigate } from "@tanstack/react-router"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  Loader2,
  ArrowUp,
  Plus,
  FileText,
  Mic2,
  Palette,
  SlidersHorizontal,
  ChevronDown,
  Check,
  Languages,
  Wand2,
  Users,
  Video,
  Image as ImageIcon,
  X,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { apiFetch } from "@/lib/api"
import { useAuth } from "@/components/AuthProvider"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Stack, type StackCardData } from "@/components/Stack"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

interface Speaker {
  id: string
  name: string
}

interface BrandTemplate {
  id: string
  name: string
}

interface Asset {
  id: string
  type: string
  processing_status: "pending" | "processing" | "completed" | "failed"
  processing_error: string | null
}

interface Project {
  id: string
  title: string
  status: string
}

interface InferredIntent {
  action: "generate" | "answer"
  answer: string | null
  language: string
  outputs: OutputKey[]
  clip_count: number | null
  specific_instruction: string | null
  confidence: number
}

const OUTPUT_OPTIONS = [
  "clips",
  "post",
  "quotes",
  "article",
  "carousel",
] as const
type OutputKey = (typeof OUTPUT_OPTIONS)[number]

// Outputs selected by default in the composer. Carousel is available as a
// top-level option but not checked by default because it is used less frequently
// than the core knowledge assets.
const DEFAULT_SELECTED_OUTPUTS: OutputKey[] = [
  "clips",
  "post",
]

const LANGUAGES = [
  { code: "en", labelKey: "languages.en" },
  { code: "fr", labelKey: "languages.fr" },
  { code: "de", labelKey: "languages.de" },
  { code: "es", labelKey: "languages.es" },
  { code: "it", labelKey: "languages.it" },
  { code: "zh", labelKey: "languages.zh" },
] as const

const DEFAULT_INTENT: InferredIntent = {
  action: "generate",
  answer: null,
  language: "en",
  outputs: DEFAULT_SELECTED_OUTPUTS,
  clip_count: null,
  specific_instruction: null,
  confidence: 1,
}

const DEFAULT_CLIP_COUNT = 5

interface HomeComposerProps {
  speakers: Speaker[]
  brandTemplates: BrandTemplate[]
  onGenerateStart?: () => void
  onProjectCreated?: (projectId: string) => void
  onError?: (error: string) => void
}

const EXTRACT_FROM_MATERIALS = "__extract__"

/** Dropdown/popover header: a short title plus a one-line explanation of what
 * this dimension controls, so first-time users understand the pill's purpose. */
function PillHeaderText({ title, desc }: { title: string; desc: string }) {
  return (
    <>
      <span className="block text-xs font-medium">{title}</span>
      <span className="mt-0.5 block text-[11px] font-normal leading-snug text-muted-foreground">
        {desc}
      </span>
    </>
  )
}

export function HomeComposer({
  speakers,
  brandTemplates,
  onGenerateStart,
  onProjectCreated,
  onError,
}: HomeComposerProps) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { requireAuth } = useAuth()

  const [prompt, setPrompt] = useState("")
  const [speakerId, setSpeakerId] = useState(EXTRACT_FROM_MATERIALS)
  const [outputs, setOutputs] = useState<OutputKey[]>(DEFAULT_SELECTED_OUTPUTS)
  const [clipCount, setClipCount] = useState<number>(DEFAULT_CLIP_COUNT)
  const [brandTemplateId, setBrandTemplateId] = useState("")
  const [language, setLanguage] = useState(DEFAULT_INTENT.language)
  const [files, setFiles] = useState<File[]>([])
  const [isGenerating, setIsGenerating] = useState(false)

  const [inferred, setInferred] = useState<InferredIntent>(DEFAULT_INTENT)
  const [isInferring, setIsInferring] = useState(false)
  // Track params the user has manually edited so inference doesn't overwrite
  // them. A ref, not state: pill clicks must never retrigger the inference
  // effect below (it fires an LLM call and re-renders mid-dropdown-animation).
  const lockedParamsRef = useRef<Set<string>>(new Set())

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // Last prompt text we auto-filled from pill selection, so a later pill
  // toggle can keep regenerating it without clobbering hand-typed text.
  const autofilledPromptRef = useRef("")
  // Live mirror of `prompt` for async callbacks: an in-flight inference
  // response must decide against what the box contains NOW, not the stale
  // value captured when the request started.
  const promptRef = useRef(prompt)
  useEffect(() => {
    promptRef.current = prompt
  }, [prompt])

  // Sync defaults once data is loaded.
  useEffect(() => {
    setBrandTemplateId((prev) => prev || (brandTemplates[0]?.id ?? ""))
  }, [brandTemplates])

  // Debounced intent inference.
  useEffect(() => {
    const text = prompt.trim()
    // Skip when empty, or when the text is our own autofill — pill toggles
    // already applied their choices; re-inferring would only churn renders.
    if (!text || prompt === autofilledPromptRef.current) {
      if (!text) setInferred(DEFAULT_INTENT)
      return
    }

    const controller = new AbortController()
    const timer = setTimeout(async () => {
      setIsInferring(true)
      try {
        const res = await apiFetch("/api/v1/infer-intent", {
          method: "POST",
          body: { prompt, filename: files[0]?.name || undefined },
          signal: controller.signal,
        })
        if (!res.ok) throw new Error("Intent inference failed")
        const data = (await res.json()) as { intent: InferredIntent }
        setInferred(data.intent)

        // Apply inferred values only to params the user hasn't locked.
        const locked = lockedParamsRef.current
        const nextLanguage = locked.has("language") ? language : data.intent.language
        const nextOutputs = locked.has("outputs") ? outputs : data.intent.outputs
        const nextClipCount = locked.has("clip_count")
          ? clipCount
          : data.intent.clip_count ?? DEFAULT_CLIP_COUNT

        setLanguage(nextLanguage)
        setOutputs(nextOutputs)
        setClipCount(nextClipCount)

        // Refresh autofill only if the box is STILL empty or auto-generated —
        // checked against the live prompt, so typing that happened while this
        // request was in flight is never clobbered.
        const live = promptRef.current
        const canAutofill = live.trim() === "" || live === autofilledPromptRef.current
        if (canAutofill) {
          const filled = buildPrefillPrompt(nextOutputs, nextLanguage, nextClipCount)
          autofilledPromptRef.current = filled
          setPrompt(filled)
        }
      } catch (e) {
        // Silent fallback: leave current values (aborted requests land here too).
      } finally {
        setIsInferring(false)
      }
    }, 600)

    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [prompt, files])

  const lockParam = (key: string) => {
    lockedParamsRef.current = new Set(lockedParamsRef.current).add(key)
  }

  const inferAssetType = (file: File): string => {
    if (file.type.startsWith("video/")) return "video"
    if (file.type.startsWith("audio/")) return "audio"
    if (file.type.startsWith("image/")) return "image"
    return "transcript"
  }

  const handleGenerate = async () => {
    await requireAuth(async () => {
      const hasContent = files.length > 0 || prompt.trim()
      if (!hasContent) {
        onError?.(t("home.noContentError"))
        return
      }
      if (outputs.length === 0) {
        onError?.(t("home.noOutputError"))
        return
      }
      // Clips need a renderable media source; a text-only prompt/transcript
      // can't produce a video. Block early with a clear message.
      if (
        outputs.includes("clips") &&
        !files.some((f) => ["video", "audio", "image"].includes(inferAssetType(f)))
      ) {
        onError?.(t("home.clipsNeedMedia"))
        return
      }
      setIsGenerating(true)
      onGenerateStart?.()
      try {
        const instruction =
          inferred.specific_instruction?.trim() || (prompt.trim() ? prompt.trim() : undefined)

        const projectRes = await apiFetch("/api/v1/projects", {
          method: "POST",
          body: {
            title: files[0]?.name || prompt.slice(0, 60) || t("common.untitled"),
            event_name: "",
            language,
            speaker_id:
              speakerId === EXTRACT_FROM_MATERIALS ? undefined : speakerId || undefined,
          },
        })
        if (!projectRes.ok) throw new Error("Failed to create project")
        const project = (await projectRes.json()) as Project

        const materials =
          files.length > 0 ? files : [new File([prompt], "prompt.txt", { type: "text/plain" })]
        await Promise.all(
          materials.map(async (material) => {
            const type = files.length > 0 ? inferAssetType(material) : "transcript"

            const urlRes = await apiFetch(`/api/v1/projects/${project.id}/assets/upload-url`, {
              method: "POST",
              body: {
                filename: material.name,
                content_type: material.type || undefined,
              },
            })
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

            const assetRes = await apiFetch(`/api/v1/projects/${project.id}/assets`, {
              method: "POST",
              body: { type, key },
            })
            if (!assetRes.ok) throw new Error("Failed to create asset")
            return (await assetRes.json()) as Asset
          })
        )

        // Asset processing (ASR / extraction) continues in the background;
        // the results page loading state covers that waiting window.
        const generateRes = await apiFetch(`/api/v1/projects/${project.id}/generate`, {
          method: "POST",
          body: {
            clip_count: clipCount,
            outputs,
            target_language: language,
            brand_template_id: brandTemplateId || undefined,
            instruction,
          },
        })
        if (!generateRes.ok) {
          const detail = await generateRes.json().catch(() => null)
          throw new Error(detail?.detail || "Generation failed")
        }

        onProjectCreated?.(project.id)
        navigate({ to: "/projects/$id", params: { id: project.id } })
      } catch (e) {
        onError?.(e instanceof Error ? e.message : "Something went wrong")
        setIsGenerating(false)
      }
    })
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? [])
    if (picked.length > 0) {
      setFiles((prev) => {
        const existing = new Set(prev.map((f) => `${f.name}:${f.size}`))
        const additions = picked.filter((f) => !existing.has(`${f.name}:${f.size}`))
        return [...prev, ...additions]
      })
    }
    // Reset so picking the same file again after removal still fires onChange.
    e.target.value = ""
  }

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const fileIconFor = (file: File) => {
    if (file.type.startsWith("video/")) return Video
    if (file.type.startsWith("audio/")) return Mic2
    if (file.type.startsWith("image/")) return ImageIcon
    return FileText
  }

  // Template-splice a prompt sentence from the selected output pills, e.g.
  // "generate 3 short clips, write a social long-form post and create
  // shareable quote cards from this talk". Language-aware via i18n.
  const buildPrefillPrompt = (
    selected: OutputKey[],
    lang: string,
    count: number = DEFAULT_CLIP_COUNT
  ): string => {
    if (selected.length === 0) return ""
    const fragments = selected.map((key) =>
      t(`composer.promptFragments.${key}`, key === "clips" ? { count } : undefined)
    )
    const last = fragments.pop() as string
    const base =
      fragments.length > 0
        ? `${fragments.join(", ")} ${t("composer.promptJoinAnd")} ${last} ${t("composer.promptFromTalk")}`
        : `${last} ${t("composer.promptFromTalk")}`
    if (lang === "en" || lang === "auto") return base
    const langOption = LANGUAGES.find((l) => l.code === lang)
    const langName = langOption ? t(langOption.labelKey) : lang
    return `${base} ${t("composer.promptInLanguage", { language: langName })}`
  }

  const toggleOutput = (key: OutputKey) => {
    lockParam("outputs")
    const next = outputs.includes(key)
      ? outputs.filter((o) => o !== key)
      : [...outputs, key]
    setOutputs(next)

    // Only autofill an empty box, or one we generated ourselves earlier —
    // never overwrite text the user actually typed.
    const canAutofill = prompt.trim() === "" || prompt === autofilledPromptRef.current
    if (canAutofill) {
      const filled = buildPrefillPrompt(next, language, clipCount)
      autofilledPromptRef.current = filled
      setPrompt(filled)
    }
  }

  const selectedSpeakerName =
    speakerId === EXTRACT_FROM_MATERIALS
      ? t("composer.extractFromMaterials")
      : speakers.find((s) => s.id === speakerId)?.name ?? t("composer.speaker")

  const hasIntent = prompt.trim().length > 0

  const fileCards: StackCardData[] = useMemo(
    () =>
      files.map((file, index) => {
        const Icon = fileIconFor(file)
        return {
          id: `${file.name}:${file.size}`,
          content: (
            <div className="relative flex h-full w-full flex-col items-center justify-center gap-1.5 rounded-lg bg-card p-2 text-center ring-1 ring-border shadow-md">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  removeFile(index)
                }}
                className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-muted text-muted-foreground hover:bg-destructive hover:text-destructive-foreground"
              >
                <X className="h-3 w-3" />
              </button>
              <Icon className="h-5 w-5 text-muted-foreground" />
              <span className="max-w-full break-all px-1 text-[10px] leading-tight text-muted-foreground">
                {file.name}
              </span>
            </div>
          ),
        }
      }),
    [files]
  )

  return (
    <Card className="overflow-hidden py-0 ring-1 ring-border shadow-xl">
      <CardContent className="p-4 text-left">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          accept=".txt,.md,.pdf,.doc,.docx,.srt,.vtt,.mp3,.mp4,.wav,.m4a"
          onChange={handleFileChange}
        />

        {/* Input area */}
        <div className="flex items-start gap-3">
          {files.length === 0 ? (
            <Tooltip>
              <TooltipTrigger
                render={
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="relative flex h-28 w-20 flex-shrink-0 flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-muted/50 p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  />
                }
              >
                <Plus className="h-6 w-6" />
                <span className="text-center text-[11px] leading-tight">{t("home.uploadSource")}</span>
              </TooltipTrigger>
              <TooltipContent>{t("home.uploadSourceTooltip")}</TooltipContent>
            </Tooltip>
          ) : (
            <div className="relative h-28 w-20 flex-shrink-0">
              <Stack
                cards={fileCards}
                className="h-full w-full"
                randomRotation
                sendToBackOnClick
                sensitivity={60}
              />
              {files.length > 1 && (
                <Badge
                  variant="secondary"
                  className="pointer-events-none absolute -left-2 -top-2 z-10 px-1.5 text-[10px]"
                >
                  {files.length}
                </Badge>
              )}
              <Tooltip>
                <TooltipTrigger
                  render={
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="absolute -bottom-2 -right-2 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground shadow"
                    />
                  }
                >
                  <Plus className="h-3.5 w-3.5" />
                </TooltipTrigger>
                <TooltipContent>{t("home.uploadSourceTooltip")}</TooltipContent>
              </Tooltip>
            </div>
          )}

          <div className="flex h-28 flex-1 flex-col">
            <Textarea
              ref={textareaRef}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  handleGenerate()
                }
              }}
              placeholder={t("home.pastePlaceholder")}
              className="min-h-0 flex-1 resize-none border-0 bg-transparent p-2 text-base shadow-none focus-visible:ring-0 dark:bg-transparent"
            />
            <div className="flex items-center justify-end px-2 pb-2">
              <Button
                className="h-9 w-9 rounded-full"
                size="icon"
                disabled={isGenerating || isInferring}
                onClick={handleGenerate}
              >
                {isGenerating ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                ) : (
                  <ArrowUp className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </div>

        {/* Editable intent chips */}
        <div className="mt-4 flex flex-wrap items-center gap-2 rounded-lg bg-muted/40 p-2">
            {/* Speaker */}
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 gap-1.5 rounded-md px-2 text-xs font-normal"
                  >
                    <Mic2 className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="max-w-[120px] truncate">
                      {selectedSpeakerName}
                    </span>
                    <ChevronDown className="h-3 w-3 text-muted-foreground" />
                  </Button>
                }
              />
              <DropdownMenuContent align="start" className="w-64">
                <DropdownMenuGroup>
                  <DropdownMenuLabel className="px-2 py-1.5">
                    <PillHeaderText
                      title={t("composer.speakerLabel")}
                      desc={t("composer.speakerDesc")}
                    />
                  </DropdownMenuLabel>
                  <DropdownMenuItem
                    onClick={() => {
                      lockParam("speaker")
                      setSpeakerId(EXTRACT_FROM_MATERIALS)
                    }}
                  >
                    <Wand2 className="mr-2 h-4 w-4 text-muted-foreground" />
                    <span className="flex-1 truncate">{t("composer.extractFromMaterials")}</span>
                    {speakerId === EXTRACT_FROM_MATERIALS && (
                      <Check className="ml-2 h-4 w-4" />
                    )}
                  </DropdownMenuItem>
                  {speakers.length > 0 && <DropdownMenuSeparator />}
                  {speakers.map((s) => (
                    <DropdownMenuItem
                      key={s.id}
                      onClick={() => {
                        lockParam("speaker")
                        setSpeakerId(s.id)
                      }}
                    >
                      <Mic2 className="mr-2 h-4 w-4 text-muted-foreground" />
                      <span className="flex-1 truncate">{s.name}</span>
                      {s.id === speakerId && <Check className="ml-2 h-4 w-4" />}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuGroup>
                <DropdownMenuGroup>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem render={<Link to="/speakers" />}>
                    <Users className="mr-2 h-4 w-4" />
                    {t("composer.manageSpeakers")}
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Brand template */}
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 gap-1.5 rounded-md px-2 text-xs font-normal"
                  >
                    <Palette className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="max-w-[120px] truncate">
                      {brandTemplates.find((b) => b.id === brandTemplateId)?.name ??
                        t("composer.brandDefault")}
                    </span>
                    <ChevronDown className="h-3 w-3 text-muted-foreground" />
                  </Button>
                }
              />
              <DropdownMenuContent align="start" className="w-64">
                <DropdownMenuGroup>
                  <DropdownMenuLabel className="px-2 py-1.5">
                    <PillHeaderText
                      title={t("composer.brandLabel")}
                      desc={t("composer.brandDesc")}
                    />
                  </DropdownMenuLabel>
                  {brandTemplates.map((b) => (
                    <DropdownMenuItem
                      key={b.id}
                      onClick={() => { lockParam("brand"); setBrandTemplateId(b.id) }}
                    >
                      <Palette className="mr-2 h-4 w-4 text-muted-foreground" />
                      <span className="flex-1 truncate">{b.name}</span>
                      {b.id === brandTemplateId && <Check className="ml-2 h-4 w-4" />}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuGroup>
                <DropdownMenuGroup>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem render={<Link to="/brand-template" />}>
                    <SlidersHorizontal className="mr-2 h-4 w-4" />
                    {t("composer.manageBrand")}
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Language */}
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 gap-1.5 rounded-md px-2 text-xs font-normal"
                  >
                    <Languages className="h-3.5 w-3.5 text-muted-foreground" />
                    <span>{t(`languages.${language as typeof LANGUAGES[number]["code"]}`)}</span>
                    <ChevronDown className="h-3 w-3 text-muted-foreground" />
                  </Button>
                }
              />
              <DropdownMenuContent align="start" className="w-56">
                <DropdownMenuGroup>
                  <DropdownMenuLabel className="px-2 py-1.5">
                    <PillHeaderText
                      title={t("composer.languageLabel")}
                      desc={t("composer.languageDesc")}
                    />
                  </DropdownMenuLabel>
                  {LANGUAGES.map((lang) => (
                    <DropdownMenuItem
                      key={lang.code}
                      onClick={() => { lockParam("language"); setLanguage(lang.code) }}
                    >
                      <span className="flex-1">{t(lang.labelKey)}</span>
                      {lang.code === language && <Check className="ml-2 h-4 w-4" />}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Outputs */}
            <Popover>
              <PopoverTrigger
                render={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 gap-1.5 rounded-md px-2 text-xs font-normal"
                  >
                    <SlidersHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
                    <span>{t("composer.outputs")}</span>
                    {outputs.length > 0 && (
                      <Badge variant="secondary" className="ml-1 px-1.5 text-[10px]">
                        {outputs.length}
                      </Badge>
                    )}
                    <ChevronDown className="h-3 w-3 text-muted-foreground" />
                  </Button>
                }
              />
              <PopoverContent align="start" className="w-64 gap-1 p-1">
                <div className="px-2 py-1.5">
                  <PillHeaderText
                    title={t("composer.outputsLabel")}
                    desc={t("composer.outputsDesc")}
                  />
                </div>
                {OUTPUT_OPTIONS.map((key) => {
                  const active = outputs.includes(key)
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => toggleOutput(key)}
                      className={cn(
                        "flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
                        active ? "bg-accent" : "hover:bg-accent/50"
                      )}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block text-xs leading-tight">
                          {t(`composer.outputOptions.${key}`)}
                        </span>
                        <span className="block text-[11px] leading-tight text-muted-foreground">
                          {t(`composer.outputDesc.${key}`)}
                        </span>
                      </span>
                      <span
                        className={cn(
                          "mt-px flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center rounded border transition-colors",
                          active
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-muted-foreground/40"
                        )}
                      >
                        {active && <Check className="h-2.5 w-2.5" />}
                      </span>
                    </button>
                  )
                })}
              </PopoverContent>
            </Popover>

            <Tooltip>
              <TooltipTrigger
                render={
                  <button
                    type="button"
                    className={cn(
                      "ml-auto flex h-8 w-8 items-center justify-center rounded-md text-primary transition-colors hover:bg-accent hover:text-foreground",
                      isInferring && "animate-pulse"
                    )}
                  >
                    {isInferring ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Wand2 className="h-4 w-4" />
                    )}
                  </button>
                }
              />
              <TooltipContent side="top">
                {isInferring
                  ? t("composer.detectingIntent")
                  : hasIntent
                    ? t("composer.aiDetected")
                    : t("composer.aiWillDetect")}
              </TooltipContent>
            </Tooltip>
          </div>
      </CardContent>
    </Card>
  )
}
