import { Link, createFileRoute, useNavigate } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  ArrowUp,
  Plus,
  MessageSquarePlus,
  Linkedin,
  Quote,
  Languages,
  Newspaper,
  Lightbulb,
  FileText,
  Presentation,
  PenTool,
  Megaphone,
  Bell,
  Star,
  Mic2,
  SlidersHorizontal,
  Sparkles,
  ChevronDown,
  Check,
  FolderKanban,
} from "lucide-react"

import { cn } from "@/lib/utils"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LanguageSwitcher } from "@/components/language-switcher"
import { ThemeToggle } from "@/components/theme-toggle"
import RotatingText from "@/components/RotatingText"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

interface Project {
  id: string
  title: string
  status: string
}

interface Speaker {
  id: string
  name: string
}

const OUTPUT_OPTIONS = ["clips", "linkedin", "quote_cards"] as const
type OutputKey = (typeof OUTPUT_OPTIONS)[number]

const tools = [
  { icon: Linkedin, id: "linkedinPost", outputKey: "linkedin", isNew: false },
  { icon: Quote, id: "quoteCard", outputKey: "quote_cards", isNew: false },
  { icon: Languages, id: "multiLangSummary", outputKey: null, isNew: true },
  { icon: Newspaper, id: "newsletter", outputKey: null, isNew: false },
  { icon: Lightbulb, id: "keyInsights", outputKey: null, isNew: true },
  { icon: FileText, id: "onePager", outputKey: null, isNew: false },
  { icon: Presentation, id: "slides", outputKey: null, isNew: true },
  { icon: PenTool, id: "blogPost", outputKey: null, isNew: false },
  { icon: Megaphone, id: "pressRelease", outputKey: null, isNew: true },
] as const

const tones = ["professional", "thoughtLeadership", "conversational", "academic"] as const
type Tone = (typeof tones)[number]

// Maps the composer's tone onto the backend ToneSettings schema.
const TONE_MAP: Record<
  Tone,
  {
    academic_vs_casual: number
    rational_vs_passionate: number
    audience: "academic" | "industry" | "general" | "investor"
  }
> = {
  professional: { academic_vs_casual: 0.35, rational_vs_passionate: 0.45, audience: "industry" },
  thoughtLeadership: { academic_vs_casual: 0.45, rational_vs_passionate: 0.4, audience: "industry" },
  conversational: { academic_vs_casual: 0.7, rational_vs_passionate: 0.6, audience: "general" },
  academic: { academic_vs_casual: 0.15, rational_vs_passionate: 0.3, audience: "academic" },
}

export const Route = createFileRoute("/")({
  component: Home,
})

function Home() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [projects, setProjects] = useState<Project[]>([])
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [prompt, setPrompt] = useState("")
  const [speakerId, setSpeakerId] = useState("")
  const [tone, setTone] = useState<Tone>("professional")
  const [outputs, setOutputs] = useState<OutputKey[]>(["linkedin", "quote_cards"])
  const [fileName, setFileName] = useState("")
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState("")
  const [mounted, setMounted] = useState(false)
  const [autoSave, setAutoSave] = useState(true)
  const [autoImport, setAutoImport] = useState(false)

  // Inline speaker creation
  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState("")
  const [newTitle, setNewTitle] = useState("")
  const [creatingSpeaker, setCreatingSpeaker] = useState(false)

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    Promise.all([
      fetch(`${API_URL}/api/v1/speakers`).then((r) => r.json()),
      fetch(`${API_URL}/api/v1/projects`).then((r) => r.json()),
    ]).then(([s, p]) => {
      setSpeakers(s)
      setProjects(p.slice(0, 3))
    })
  }, [createOpen])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`
  }, [prompt])

  // RotatingText uses framer-motion; render it only after mount to keep the
  // first paint identical between server and client (no hydration mismatch).
  useEffect(() => setMounted(true), [])

  const heroWords = t("home.heroWords", { returnObjects: true }) as string[]

  const handleCreateSpeaker = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newName.trim()) return
    setCreatingSpeaker(true)
    try {
      const res = await fetch(`${API_URL}/api/v1/speakers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim(), title: newTitle.trim() || null, language: "en" }),
      })
      if (!res.ok) throw new Error("Failed")
      const speaker: Speaker = await res.json()
      setSpeakers((prev) => [speaker, ...prev])
      setSpeakerId(speaker.id)
      setNewName("")
      setNewTitle("")
      setCreateOpen(false)
    } catch {
      setError(t("home.speakerCreateFailed"))
    } finally {
      setCreatingSpeaker(false)
    }
  }

  const handleGenerate = async () => {
    const file = fileInputRef.current?.files?.[0]
    const hasContent = file || prompt.trim()
    if (!hasContent) {
      setError(t("home.noContentError"))
      return
    }
    setIsGenerating(true)
    setError("")
    try {
      // 1. Create the project.
      const projectRes = await fetch(`${API_URL}/api/v1/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: file?.name || prompt.slice(0, 60) || t("common.untitled"),
          event_name: "",
          language: "en",
          speaker_id: speakerId || undefined,
        }),
      })
      if (!projectRes.ok) throw new Error("Failed to create project")
      const project = await projectRes.json()

      // 2. Upload the source material: file or typed prompt as transcript.
      const form = new FormData()
      form.append("type", "transcript")
      form.append("file", file ?? new File([prompt], "prompt.txt", { type: "text/plain" }))
      const assetRes = await fetch(
        `${API_URL}/api/v1/projects/${project.id}/assets`,
        { method: "POST", body: form }
      )
      if (!assetRes.ok) throw new Error("Failed to upload material")

      // 3. Kick off generation. Clips are always generated; outputs controls extras.
      const generateRes = await fetch(
        `${API_URL}/api/v1/projects/${project.id}/generate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            clip_count: 3,
            outputs: ["clips", ...outputs],
            tone_settings: {
              ...TONE_MAP[tone],
              concise_vs_detailed: 0.5,
            },
            target_language: "en",
          }),
        }
      )
      if (!generateRes.ok) {
        const detail = await generateRes.json().catch(() => null)
        throw new Error(detail?.detail || "Generation failed")
      }

      // 4. Open the project to view results.
      navigate({ to: "/projects/$id", params: { id: project.id } })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong")
    } finally {
      setIsGenerating(false)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFileName(e.target.files?.[0]?.name ?? "")
  }

  const toggleOutput = (key: OutputKey) => {
    setOutputs((prev) =>
      prev.includes(key) ? prev.filter((o) => o !== key) : [...prev, key]
    )
  }

  const handleToolClick = (tool: (typeof tools)[number]) => {
    if (tool.outputKey) {
      toggleOutput(tool.outputKey)
      return
    }
    setError(t("home.comingSoon"))
    setTimeout(() => setError(""), 2000)
  }

  const selectedSpeakerName = speakerId
    ? speakers.find((s) => s.id === speakerId)?.name
    : t("composer.styleDefault")

  return (
    <div className="flex min-h-svh flex-1 flex-col">
      {/* Global top bar */}
      <header className="flex items-center justify-between px-6 py-4">
        <Button variant="outline" className="gap-2" onClick={() => navigate({ to: "/" })}>
          <MessageSquarePlus className="h-4 w-4" />
          {t("home.newChat")}
        </Button>

        <div className="flex items-center gap-3">
          <ThemeToggle />
          <LanguageSwitcher />

          <Button variant="ghost" size="icon" className="relative">
            <Bell className="h-5 w-5" />
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] text-destructive-foreground">
              24
            </span>
          </Button>

          <div className="flex h-7 items-center gap-2 rounded-md bg-card px-3 text-sm ring-1 ring-border">
            <Star className="h-4 w-4 fill-amber-400 text-amber-500" />
            <span>0</span>
          </div>

          <Button>{t("home.credits")}</Button>
        </div>
      </header>

      {/* Hero / Prompt */}
      <section className="flex flex-col items-center px-6 pt-16 pb-10">
        <div className="w-full max-w-3xl text-center">
          <h1 className="mb-4 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-4xl font-bold tracking-tight sm:text-5xl">
            <span>{t("home.heroPrefix")}</span>
            {mounted ? (
              <RotatingText
                texts={heroWords}
                rotationInterval={2200}
                splitBy="characters"
                staggerDuration={0.02}
                mainClassName="text-primary"
                splitLevelClassName="overflow-hidden py-1"
              />
            ) : (
              <span className="text-primary">{heroWords[0]}</span>
            )}
          </h1>
          <p className="mb-10 text-base text-muted-foreground sm:text-lg">
            {t("home.heroSubtitle")}
          </p>

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
                <div className="flex items-center gap-2">
                  {/* Style / Speaker */}
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
                      <DropdownMenuItem onClick={() => setSpeakerId("")}>
                        <Mic2 className="mr-2 h-4 w-4 text-muted-foreground" />
                        <span className="flex-1 truncate">{t("composer.styleDefault")}</span>
                        {speakerId === "" && <Check className="ml-2 h-4 w-4" />}
                      </DropdownMenuItem>
                      {speakers.length > 0 && <DropdownMenuSeparator />}
                      {speakers.map((s) => (
                        <DropdownMenuItem key={s.id} onClick={() => setSpeakerId(s.id)}>
                          <Mic2 className="mr-2 h-4 w-4 text-muted-foreground" />
                          <span className="flex-1 truncate">{s.name}</span>
                          {s.id === speakerId && <Check className="ml-2 h-4 w-4" />}
                        </DropdownMenuItem>
                      ))}
                      <DropdownMenuSeparator />
                      <DropdownMenuItem onClick={() => setCreateOpen(true)}>
                        <Plus className="mr-2 h-4 w-4" />
                        {t("composer.createSpeaker")}
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
                  <div className="flex h-9 items-center gap-1.5 px-1 text-sm text-muted-foreground">
                    <Star className="h-4 w-4 fill-amber-400 text-amber-500" />
                    <span>0</span>
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
              </div>
            </CardContent>
          </Card>

          {error && (
            <p className="mt-3 text-sm text-destructive">{error}</p>
          )}
          {isGenerating && !error && (
            <p className="mt-3 text-sm text-muted-foreground">
              {t("home.generating")}
            </p>
          )}
        </div>

        {/* Tool row */}
        <div className="mt-12 flex w-full max-w-5xl flex-wrap items-start justify-center gap-x-3 gap-y-6">
          {tools.map((tool) => {
            const active = tool.outputKey ? outputs.includes(tool.outputKey) : false
            return (
              <button
                key={tool.id}
                onClick={() => handleToolClick(tool)}
                className="group relative flex w-[84px] flex-col items-center gap-2.5"
              >
                {tool.isNew && (
                  <Badge
                    variant="secondary"
                    className="absolute -top-2 right-1 z-10 px-1.5 text-[10px]"
                  >
                    New
                  </Badge>
                )}
                <div
                  className={cn(
                    "flex h-14 w-14 items-center justify-center rounded-lg bg-card text-primary shadow-sm transition-colors group-hover:bg-primary group-hover:text-primary-foreground",
                    active && "ring-2 ring-primary bg-primary/10"
                  )}
                >
                  <tool.icon className="h-6 w-6" />
                </div>
                <span className="text-center text-xs leading-tight">
                  {t(`home.tools.${tool.id}`)}
                </span>
              </button>
            )
          })}
        </div>
      </section>

      {/* Projects */}
      <section className="px-6 pb-16">
        <div className="mx-auto w-full max-w-6xl">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-3">
            <div className="flex items-center gap-6 text-sm">
              <span className="font-medium text-foreground">
                {t("home.allProjects", { count: projects.length })}
              </span>
              <Link
                to="/library"
                className="text-muted-foreground transition-colors hover:text-foreground"
              >
                {t("home.savedProjects", { count: 0 })}
              </Link>
            </div>

            <div className="flex items-center gap-4 text-sm">
              <span className="text-muted-foreground">{t("home.storage")}</span>

              <label className="flex items-center gap-2 rounded-md px-3 py-1.5">
                <Switch
                  size="sm"
                  checked={autoSave}
                  onCheckedChange={setAutoSave}
                />
                <span className="text-xs">{t("home.autoSave")}</span>
              </label>

              <label className="flex items-center gap-2 rounded-md px-3 py-1.5">
                <Switch
                  size="sm"
                  checked={autoImport}
                  onCheckedChange={setAutoImport}
                />
                <span className="text-xs">{t("home.autoImport")}</span>
                <Badge variant="secondary" className="text-[10px]">
                  {t("home.beta")}
                </Badge>
              </label>
            </div>
          </div>

          {projects.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              {t("home.noProjects")}
            </p>
          ) : (
            <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {projects.map((project) => (
                <Link
                  key={project.id}
                  to="/projects/$id"
                  params={{ id: project.id }}
                  className="group flex flex-col gap-3 rounded-xl bg-card/50 p-3 ring-1 ring-border transition-colors hover:bg-accent"
                >
                  <div className="flex aspect-video items-center justify-center rounded-lg bg-primary/10">
                    <FolderKanban className="h-7 w-7 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{project.title}</p>
                    <p className="mt-0.5 text-xs capitalize text-muted-foreground">
                      {project.status}
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Create Speaker Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <form onSubmit={handleCreateSpeaker}>
            <DialogHeader>
              <DialogTitle>{t("composer.createSpeaker")}</DialogTitle>
              <DialogDescription>{t("speakers.dialogDesc")}</DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="speaker-name">{t("speakers.labelName")}</Label>
                <Input
                  id="speaker-name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder={t("speakers.labelName")}
                  required
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="speaker-title">{t("speakers.labelTitle")}</Label>
                <Input
                  id="speaker-title"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder={t("speakers.noTitle")}
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="submit" disabled={creatingSpeaker || !newName.trim()}>
                {creatingSpeaker ? t("common.creating") : t("common.create")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
