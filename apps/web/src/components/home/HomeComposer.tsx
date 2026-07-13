"use client"

import { Link, useNavigate } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
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
  Linkedin,
  Quote,
  Image as ImageIcon,
  X,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { apiFetch } from "@/lib/api"

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
  language: string
  outputs: OutputKey[]
  specific_instruction: string | null
  confidence: number
}

const OUTPUT_OPTIONS = ["clips", "linkedin", "quote_cards", "summary"] as const
type OutputKey = (typeof OUTPUT_OPTIONS)[number]

const OUTPUT_ICONS = {
  clips: Video,
  linkedin: Linkedin,
  quote_cards: Quote,
  summary: Languages,
} as const

const LANGUAGES = [
  { code: "en", labelKey: "languages.en" },
  { code: "fr", labelKey: "languages.fr" },
  { code: "de", labelKey: "languages.de" },
  { code: "es", labelKey: "languages.es" },
  { code: "it", labelKey: "languages.it" },
  { code: "zh", labelKey: "languages.zh" },
] as const

const DEFAULT_INTENT: InferredIntent = {
  language: "en",
  outputs: ["clips", "linkedin", "quote_cards", "summary"],
  specific_instruction: null,
  confidence: 1,
}

const DEFAULT_CLIP_COUNT = 3

interface HomeComposerProps {
  speakers: Speaker[]
  brandTemplates: BrandTemplate[]
  onGenerateStart?: () => void
  onProjectCreated?: (projectId: string) => void
  onError?: (error: string) => void
}

const EXTRACT_FROM_MATERIALS = "__extract__"

export function HomeComposer({
  speakers,
  brandTemplates,
  onGenerateStart,
  onProjectCreated,
  onError,
}: HomeComposerProps) {
  const navigate = useNavigate()
  const { t } = useTranslation()

  const [prompt, setPrompt] = useState("")
  const [speakerId, setSpeakerId] = useState(EXTRACT_FROM_MATERIALS)
  const [outputs, setOutputs] = useState<OutputKey[]>(DEFAULT_INTENT.outputs)
  const [brandTemplateId, setBrandTemplateId] = useState("")
  const [language, setLanguage] = useState(DEFAULT_INTENT.language)
  const [files, setFiles] = useState<File[]>([])
  const [isGenerating, setIsGenerating] = useState(false)

  const [inferred, setInferred] = useState<InferredIntent>(DEFAULT_INTENT)
  const [isInferring, setIsInferring] = useState(false)
  // Track params the user has manually edited so inference doesn't overwrite them.
  const [lockedParams, setLockedParams] = useState<Set<string>>(new Set())

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // Last prompt text we auto-filled from pill selection, so a later pill
  // toggle can keep regenerating it without clobbering hand-typed text.
  const autofilledPromptRef = useRef("")

  // Sync defaults once data is loaded.
  useEffect(() => {
    setBrandTemplateId((prev) => prev || (brandTemplates[0]?.id ?? ""))
  }, [brandTemplates])

  // Auto-resize textarea.
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`
  }, [prompt])

  // Debounced intent inference.
  useEffect(() => {
    if (!prompt.trim()) {
      setInferred(DEFAULT_INTENT)
      return
    }

    const timer = setTimeout(async () => {
      setIsInferring(true)
      try {
        const res = await apiFetch("/api/v1/infer-intent", {
          method: "POST",
          body: { prompt, filename: files[0]?.name || undefined },
        })
        if (!res.ok) throw new Error("Intent inference failed")
        const data = (await res.json()) as { intent: InferredIntent }
        setInferred(data.intent)

        // Apply inferred values only to params the user hasn't locked.
        setLanguage((prev) => (lockedParams.has("language") ? prev : data.intent.language))
        setOutputs((prev) => (lockedParams.has("outputs") ? prev : data.intent.outputs))
      } catch (e) {
        // Silent fallback: leave current values.
      } finally {
        setIsInferring(false)
      }
    }, 600)

    return () => clearTimeout(timer)
  }, [prompt, files])

  const lockParam = (key: string) => {
    setLockedParams((prev) => new Set(prev).add(key))
  }

  const inferAssetType = (file: File): string => {
    if (file.type.startsWith("video/")) return "video"
    if (file.type.startsWith("audio/")) return "audio"
    if (file.type.startsWith("image/")) return "image"
    return "transcript"
  }

  const waitForAssetProcessed = async (projectId: string, assetId: string) => {
    for (let i = 0; i < 120; i++) {
      const res = await apiFetch(`/api/v1/projects/${projectId}/assets/${assetId}`)
      if (!res.ok) throw new Error("Failed to check asset status")
      const asset: Asset = await res.json()
      if (asset.processing_status === "completed") return
      if (asset.processing_status === "failed") {
        throw new Error(asset.processing_error || "Asset processing failed")
      }
      await new Promise((resolve) => setTimeout(resolve, 2500))
    }
    throw new Error("Asset processing timed out")
  }

  const handleGenerate = async () => {
    const hasContent = files.length > 0 || prompt.trim()
    if (!hasContent) {
      onError?.(t("home.noContentError"))
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
      const uploaded = await Promise.all(
        materials.map(async (material) => {
          const form = new FormData()
          form.append("type", files.length > 0 ? inferAssetType(material) : "transcript")
          form.append("file", material)
          const assetRes = await apiFetch(`/api/v1/projects/${project.id}/assets`, {
            method: "POST",
            body: form,
          })
          if (!assetRes.ok) throw new Error("Failed to upload material")
          return (await assetRes.json()) as Asset
        })
      )

      await Promise.all(uploaded.map((asset) => waitForAssetProcessed(project.id, asset.id)))

      const generateRes = await apiFetch(`/api/v1/projects/${project.id}/generate`, {
        method: "POST",
        body: {
          clip_count: DEFAULT_CLIP_COUNT,
          outputs: ["clips", ...outputs],
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
  // "generate 3 short clips, write a LinkedIn long-form post and create
  // shareable quote cards from this talk". Language-aware via i18n.
  const buildPrefillPrompt = (selected: OutputKey[], lang: string): string => {
    if (selected.length === 0) return ""
    const fragments = selected.map((key) =>
      t(
        `composer.promptFragments.${key}`,
        key === "clips" ? { count: DEFAULT_CLIP_COUNT } : undefined
      )
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
      const filled = buildPrefillPrompt(next, language)
      autofilledPromptRef.current = filled
      setPrompt(filled)
    }
  }

  const selectedSpeakerName =
    speakerId === EXTRACT_FROM_MATERIALS
      ? t("composer.extractFromMaterials")
      : speakers.find((s) => s.id === speakerId)?.name ?? t("composer.speaker")

  const hasIntent = prompt.trim().length > 0

  const fileCards: StackCardData[] = files.map((file, index) => {
    const Icon = fileIconFor(file)
    return {
      id: `${file.name}:${file.size}`,
      content: (
        <div className="relative flex h-full w-full flex-col items-center justify-center gap-1 rounded-lg bg-card p-1.5 text-center ring-1 ring-border shadow-md">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              removeFile(index)
            }}
            className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-muted text-muted-foreground hover:bg-destructive hover:text-destructive-foreground"
          >
            <X className="h-2.5 w-2.5" />
          </button>
          <Icon className="h-4 w-4 text-muted-foreground" />
          <span className="line-clamp-2 px-1 text-[8px] leading-tight text-muted-foreground">
            {file.name}
          </span>
        </div>
      ),
    }
  })

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
                    className="relative flex h-20 w-14 flex-shrink-0 flex-col items-center justify-center gap-1 rounded-lg border border-dashed bg-muted/50 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  />
                }
              >
                <Plus className="h-5 w-5" />
                <span className="text-[10px]">{t("home.uploadSource")}</span>
              </TooltipTrigger>
              <TooltipContent>{t("home.uploadSourceTooltip")}</TooltipContent>
            </Tooltip>
          ) : (
            <div className="relative h-20 w-14 flex-shrink-0">
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
                      className="absolute -bottom-1.5 -right-1.5 z-10 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground shadow"
                    />
                  }
                >
                  <Plus className="h-3 w-3" />
                </TooltipTrigger>
                <TooltipContent>{t("home.uploadSourceTooltip")}</TooltipContent>
              </Tooltip>
            </div>
          )}

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
            className="min-h-[80px] flex-1 resize-none border-0 bg-transparent p-2 text-base shadow-none focus-visible:ring-0"
          />
        </div>

        {/* Generate + confirmation layer */}
        <div className="mt-4 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Wand2 className={cn("h-3.5 w-3.5", isInferring && "animate-pulse")} />
              <span>
                {isInferring
                  ? t("composer.detectingIntent")
                  : hasIntent
                    ? t("composer.aiDetected")
                    : t("composer.aiWillDetect")}
              </span>
            </div>
            <Button
              className="h-9 w-9 rounded-full"
              size="icon"
              disabled={isGenerating}
              onClick={handleGenerate}
            >
              {isGenerating ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
              ) : (
                <ArrowUp className="h-4 w-4" />
              )}
            </Button>
          </div>

          {/* Editable intent chips */}
          <div className="flex flex-wrap items-center gap-2 rounded-lg bg-muted/40 p-2">
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
              <DropdownMenuContent align="start" className="w-56">
                <DropdownMenuGroup>
                  <DropdownMenuLabel>{t("composer.speakerLabel")}</DropdownMenuLabel>
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
              <DropdownMenuContent align="start" className="w-56">
                <DropdownMenuGroup>
                  <DropdownMenuLabel>{t("composer.brandLabel")}</DropdownMenuLabel>
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
              <DropdownMenuContent align="start" className="w-48">
                <DropdownMenuGroup>
                  <DropdownMenuLabel>{t("common.language")}</DropdownMenuLabel>
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
                        {outputs.length + 1}
                      </Badge>
                    )}
                    <ChevronDown className="h-3 w-3 text-muted-foreground" />
                  </Button>
                }
              />
              <PopoverContent align="start" className="w-56 space-y-1 p-2">
                <p className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
                  {t("composer.outputsLabel")}
                </p>
                <div className="flex w-full items-center justify-between rounded-md bg-accent px-2 py-1.5 text-sm text-foreground">
                  <span className="flex items-center gap-2">
                    <Video className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                    <span className="flex flex-col">
                      <span>{t("composer.outputOptions.clips")}</span>
                      <span className="text-xs font-normal text-muted-foreground">
                        {t("home.alwaysIncluded")}
                      </span>
                    </span>
                  </span>
                  <Check className="h-4 w-4 flex-shrink-0" />
                </div>
                {OUTPUT_OPTIONS.filter((o) => o !== "clips").map((key) => {
                  const active = outputs.includes(key)
                  const Icon = OUTPUT_ICONS[key]
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => toggleOutput(key)}
                      className={cn(
                        "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm transition-colors",
                        active ? "bg-accent text-foreground" : "hover:bg-accent/50"
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <Icon className="h-4 w-4 text-muted-foreground" />
                        {t(`composer.outputOptions.${key}`)}
                      </span>
                      {active && <Check className="h-4 w-4" />}
                    </button>
                  )
                })}
              </PopoverContent>
            </Popover>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
