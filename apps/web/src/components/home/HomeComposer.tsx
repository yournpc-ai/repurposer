import { Link, useNavigate } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  ArrowUp,
  Plus,
  FileText,
  Mic2,
  Palette,
  Sparkles,
  SlidersHorizontal,
  ChevronDown,
  Check,
  Languages,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { apiFetch } from "@/lib/api"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import {
  DropdownMenu,
  DropdownMenuContent,
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

const OUTPUT_OPTIONS = ["clips", "linkedin", "quote_cards", "summary"] as const
type OutputKey = (typeof OUTPUT_OPTIONS)[number]

const tones = ["professional", "thoughtLeadership", "conversational", "academic"] as const
type Tone = (typeof tones)[number]

const LANGUAGES = [
  { code: "en", labelKey: "languages.en" },
  { code: "fr", labelKey: "languages.fr" },
  { code: "de", labelKey: "languages.de" },
  { code: "es", labelKey: "languages.es" },
  { code: "it", labelKey: "languages.it" },
  { code: "zh", labelKey: "languages.zh" },
] as const

// Maps the composer's tone onto the backend ToneSettings schema.
const TONE_MAP: Record<
  Tone,
  {
    academic_vs_casual: number
    rational_vs_passionate: number
    audience: "academic" | "industry" | "general" | "investor"
  }
> = {
  professional: {
    academic_vs_casual: 0.35,
    rational_vs_passionate: 0.45,
    audience: "industry",
  },
  thoughtLeadership: {
    academic_vs_casual: 0.45,
    rational_vs_passionate: 0.4,
    audience: "industry",
  },
  conversational: {
    academic_vs_casual: 0.7,
    rational_vs_passionate: 0.6,
    audience: "general",
  },
  academic: {
    academic_vs_casual: 0.15,
    rational_vs_passionate: 0.3,
    audience: "academic",
  },
}

interface HomeComposerProps {
  speakers: Speaker[]
  brandTemplates: BrandTemplate[]
  outputs?: OutputKey[]
  onOutputsChange?: (outputs: OutputKey[]) => void
  onGenerateStart?: () => void
  onProjectCreated?: (projectId: string) => void
  onError?: (error: string) => void
}

export function HomeComposer({
  speakers,
  brandTemplates,
  outputs: controlledOutputs,
  onOutputsChange,
  onGenerateStart,
  onProjectCreated,
  onError,
}: HomeComposerProps) {
  const navigate = useNavigate()
  const { t } = useTranslation()

  const [prompt, setPrompt] = useState("")
  const [speakerId, setSpeakerId] = useState("")
  const [tone, setTone] = useState<Tone>("professional")
  const [internalOutputs, setInternalOutputs] = useState<OutputKey[]>([
    "linkedin",
    "quote_cards",
    "summary",
  ])
  const outputs = controlledOutputs ?? internalOutputs
  const setOutputs = onOutputsChange ?? setInternalOutputs
  const [brandTemplateId, setBrandTemplateId] = useState("")
  const [language, setLanguage] = useState("en")
  const [fileName, setFileName] = useState("")
  const [isGenerating, setIsGenerating] = useState(false)

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Sync defaults once data is loaded.
  useEffect(() => {
    setSpeakerId((prev) => prev || (speakers[0]?.id ?? ""))
    setBrandTemplateId((prev) => prev || (brandTemplates[0]?.id ?? ""))
  }, [speakers, brandTemplates])

  // Auto-resize textarea.
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`
  }, [prompt])

  // Prompt keyword matching auto-checks outputs.
  useEffect(() => {
    const lower = prompt.toLowerCase()
    const next = new Set(outputs)
    const has = (keywords: string[]) => keywords.some((k) => lower.includes(k))

    if (has(["linkedin", "post"])) next.add("linkedin")
    if (has(["quote", "card"])) next.add("quote_cards")
    if (has(["summary", "abstract", "tldr"])) next.add("summary")
    // clips are always generated; no toggle needed.

    const arr = Array.from(next).filter((o): o is OutputKey =>
      OUTPUT_OPTIONS.includes(o as OutputKey)
    )
    if (arr.join(",") !== outputs.join(",")) {
      setOutputs(arr)
    }
  }, [prompt])

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
    const file = fileInputRef.current?.files?.[0]
    const hasContent = file || prompt.trim()
    if (!hasContent) {
      onError?.(t("home.noContentError"))
      return
    }
    setIsGenerating(true)
    onGenerateStart?.()
    try {
      const projectRes = await apiFetch("/api/v1/projects", {
        method: "POST",
        body: {
          title: file?.name || prompt.slice(0, 60) || t("common.untitled"),
          event_name: "",
          language,
          speaker_id: speakerId || undefined,
        },
      })
      if (!projectRes.ok) throw new Error("Failed to create project")
      const project = (await projectRes.json()) as Project

      const form = new FormData()
      form.append("type", file ? inferAssetType(file) : "transcript")
      form.append(
        "file",
        file ?? new File([prompt], "prompt.txt", { type: "text/plain" })
      )
      const assetRes = await apiFetch(`/api/v1/projects/${project.id}/assets`, {
        method: "POST",
        body: form,
      })
      if (!assetRes.ok) throw new Error("Failed to upload material")
      const asset = (await assetRes.json()) as Asset

      await waitForAssetProcessed(project.id, asset.id)

      const messageRes = await apiFetch(`/api/v1/projects/${project.id}/messages`, {
        method: "POST",
        body: {
          role: "user",
          content: prompt,
          attachments: [],
          meta: {
            params: {
              outputs: ["clips", ...outputs],
              tone,
              speakerId,
              brandTemplateId,
              language,
            },
          },
        },
      })
      if (!messageRes.ok) throw new Error("Failed to create message")

      const generateRes = await apiFetch(`/api/v1/projects/${project.id}/generate`, {
        method: "POST",
        body: {
          clip_count: 3,
          outputs: ["clips", ...outputs],
          tone_settings: {
            ...TONE_MAP[tone],
            concise_vs_detailed: 0.5,
          },
          target_language: language,
          brand_template_id: brandTemplateId || undefined,
          instruction: file && prompt.trim() ? prompt.trim() : undefined,
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
    setFileName(e.target.files?.[0]?.name ?? "")
  }

  const toggleOutput = (key: OutputKey) => {
    const next = outputs.includes(key)
      ? outputs.filter((o) => o !== key)
      : [...outputs, key]
    setOutputs(next)
  }

  const selectedSpeakerName = speakerId
    ? speakers.find((s) => s.id === speakerId)?.name
    : t("composer.styleDefault")

  return (
    <Card className="overflow-hidden py-0 ring-1 ring-border shadow-xl">
      <CardContent className="p-4 text-left">
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".txt,.md,.pdf,.doc,.docx,.srt,.vtt,.mp3,.mp4,.wav,.m4a"
          onChange={handleFileChange}
        />

        <div className="flex items-start gap-3">
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
              {fileName ? (
                <>
                  <FileText className="h-5 w-5" />
                  <span className="line-clamp-2 px-1 text-center text-[9px] leading-tight">
                    {fileName}
                  </span>
                </>
              ) : (
                <>
                  <Plus className="h-5 w-5" />
                  <span className="text-[10px]">{t("home.uploadSource")}</span>
                </>
              )}
            </TooltipTrigger>
            <TooltipContent>{t("home.uploadSourceTooltip")}</TooltipContent>
          </Tooltip>

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

        <div className="mt-4 flex items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {/* Speaker */}
            {speakers.length > 0 && (
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-9 gap-1.5 rounded-md px-3 text-sm"
                    >
                      <Mic2 className="h-4 w-4 text-muted-foreground" />
                      <span className="max-w-[140px] truncate">
                        {selectedSpeakerName}
                      </span>
                      <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                    </Button>
                  }
                />
                <DropdownMenuContent align="start" className="w-56">
                  <DropdownMenuLabel>{t("composer.styleLabel")}</DropdownMenuLabel>
                  {speakers.map((s) => (
                    <DropdownMenuItem key={s.id} onClick={() => setSpeakerId(s.id)}>
                      <Mic2 className="mr-2 h-4 w-4 text-muted-foreground" />
                      <span className="flex-1 truncate">{s.name}</span>
                      {s.id === speakerId && <Check className="ml-2 h-4 w-4" />}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            )}

            {/* Brand template */}
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 gap-1.5 rounded-md px-3 text-sm"
                  >
                    <Palette className="h-4 w-4 text-muted-foreground" />
                    <span className="max-w-[120px] truncate">
                      {brandTemplates.find((b) => b.id === brandTemplateId)?.name ??
                        t("composer.brandDefault")}
                    </span>
                    <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                  </Button>
                }
              />
              <DropdownMenuContent align="start" className="w-56">
                <DropdownMenuLabel>{t("composer.brandLabel")}</DropdownMenuLabel>
                {brandTemplates.map((b) => (
                  <DropdownMenuItem
                    key={b.id}
                    onClick={() => setBrandTemplateId(b.id)}
                  >
                    <Palette className="mr-2 h-4 w-4 text-muted-foreground" />
                    <span className="flex-1 truncate">{b.name}</span>
                    {b.id === brandTemplateId && <Check className="ml-2 h-4 w-4" />}
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem render={<Link to="/brand-template" />}>
                  <SlidersHorizontal className="mr-2 h-4 w-4" />
                  {t("composer.manageBrand")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Tone */}
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 gap-1.5 rounded-md px-3 text-sm"
                  >
                    <Sparkles className="h-4 w-4 text-muted-foreground" />
                    <span>{t(`composer.tones.${tone}`)}</span>
                    <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                  </Button>
                }
              />
              <DropdownMenuContent align="start" className="w-60">
                <DropdownMenuLabel>{t("composer.toneLabel")}</DropdownMenuLabel>
                {tones.map((tn) => (
                  <DropdownMenuItem key={tn} onClick={() => setTone(tn)}>
                    <div className="flex-1">
                      <p className="text-sm">{t(`composer.tones.${tn}`)}</p>
                      <p className="text-xs text-muted-foreground">
                        {t(`composer.toneDesc.${tn}`)}
                      </p>
                    </div>
                    {tn === tone && <Check className="ml-2 h-4 w-4" />}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Language */}
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 gap-1.5 rounded-md px-3 text-sm"
                  >
                    <Languages className="h-4 w-4 text-muted-foreground" />
                    <span>{t(`languages.${language as typeof LANGUAGES[number]["code"]}`)}</span>
                    <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                  </Button>
                }
              />
              <DropdownMenuContent align="start" className="w-48">
                <DropdownMenuLabel>{t("common.language")}</DropdownMenuLabel>
                {LANGUAGES.map((lang) => (
                  <DropdownMenuItem
                    key={lang.code}
                    onClick={() => setLanguage(lang.code)}
                  >
                    <span className="flex-1">{t(lang.labelKey)}</span>
                    {lang.code === language && <Check className="ml-2 h-4 w-4" />}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Outputs */}
            <Popover>
              <PopoverTrigger
                render={
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 gap-1.5 rounded-md px-3 text-sm"
                  >
                    <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
                    <span>{t("composer.outputs")}</span>
                    {outputs.length > 0 && (
                      <Badge variant="secondary" className="ml-1 px-1.5 text-[10px]">
                        {outputs.length + 1}
                      </Badge>
                    )}
                    <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                  </Button>
                }
              />
              <PopoverContent align="start" className="w-56 space-y-1 p-2">
                <p className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
                  {t("composer.outputsLabel")}
                </p>
                <div className="rounded-md border px-3 py-2 text-xs text-muted-foreground">
                  {t("composer.outputOptions.clips")} — {t("home.alwaysIncluded")}
                </div>
                {OUTPUT_OPTIONS.filter((o) => o !== "clips").map((key) => {
                  const active = outputs.includes(key)
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
                      {t(`composer.outputOptions.${key}`)}
                      {active && <Check className="h-4 w-4" />}
                    </button>
                  )
                })}
              </PopoverContent>
            </Popover>
          </div>

          <div className="flex items-center gap-3">
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
        </div>
      </CardContent>
    </Card>
  )
}
