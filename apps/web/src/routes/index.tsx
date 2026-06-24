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
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { LanguageSwitcher } from "@/components/language-switcher"
import { ThemeToggle } from "@/components/theme-toggle"

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

const tools = [
  { icon: Linkedin, id: "linkedinPost", isNew: false },
  { icon: Quote, id: "quoteCard", isNew: false },
  { icon: Languages, id: "multiLangSummary", isNew: true },
  { icon: Newspaper, id: "newsletter", isNew: false },
  { icon: Lightbulb, id: "keyInsights", isNew: true },
  { icon: FileText, id: "onePager", isNew: false },
  { icon: Presentation, id: "slides", isNew: true },
  { icon: PenTool, id: "blogPost", isNew: false },
  { icon: Megaphone, id: "pressRelease", isNew: true },
] as const

const tones = ["professional", "thoughtLeadership", "conversational", "academic"] as const
const lengths = ["short", "medium", "long"] as const
const variantOptions = [1, 3, 5] as const

type Tone = (typeof tones)[number]
type Length = (typeof lengths)[number]

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
  const [length, setLength] = useState<Length>("medium")
  const [variants, setVariants] = useState<number>(3)
  const [fileName, setFileName] = useState("")
  const [isGenerating, setIsGenerating] = useState(false)
  const [autoSave, setAutoSave] = useState(true)
  const [autoImport, setAutoImport] = useState(false)
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
  }, [])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`
  }, [prompt])

  const handleGenerate = async () => {
    if (!prompt.trim() || !speakerId) return
    setIsGenerating(true)
    try {
      const res = await fetch(`${API_URL}/api/v1/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: prompt.slice(0, 60),
          event_name: "",
          language: "en",
          speaker_id: speakerId,
        }),
      })
      const project = await res.json()
      navigate({ to: "/projects/$id", params: { id: project.id } })
    } finally {
      setIsGenerating(false)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFileName(e.target.files?.[0]?.name ?? "")
  }

  const handleFeatureClick = (label: string) => {
    setPrompt((prev) => {
      if (prev.trim()) return `${prev}\n${t("home.promptAppendTool", { label })}`
      return t("home.promptSeedTool", { label })
    })
    textareaRef.current?.focus()
  }

  return (
    <div className="flex min-h-svh flex-1 flex-col">
      {/* Global top bar */}
      <header className="flex items-center justify-between px-6 py-4">
        <Button variant="outline" className="gap-2">
          <MessageSquarePlus className="h-4 w-4" />
          {t("home.newChat")}
        </Button>

        <div className="flex items-center gap-3">
          <ThemeToggle />
          <LanguageSwitcher />

          <Button variant="ghost" size="icon" className="relative">
            <Bell className="h-5 w-5" />
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] text-white">
              24
            </span>
          </Button>

          <div className="flex h-7 items-center gap-2 rounded-md border bg-card px-3 text-sm">
            <Star className="h-4 w-4 fill-amber-400 text-amber-500" />
            <span>0</span>
          </div>

          <Button>{t("home.credits")}</Button>
        </div>
      </header>

      {/* Hero / Prompt */}
      <section className="flex flex-col items-center px-6 pt-16 pb-10">
        <div className="w-full max-w-3xl text-center">
          <h1 className="mb-10 text-4xl font-bold tracking-tight sm:text-5xl">
            {t("home.hero")}
          </h1>

          <Card className="overflow-hidden py-0 ring-1 ring-border shadow-xl">
            <CardContent className="p-4 text-left">
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept=".txt,.md,.pdf,.doc,.docx,.srt,.vtt"
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
                        <span className="text-[10px]">{t("home.reference")}</span>
                      </>
                    )}
                  </TooltipTrigger>
                  <TooltipContent>{t("home.referenceTooltip")}</TooltipContent>
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
                  placeholder={t("home.placeholder")}
                  className="min-h-[80px] flex-1 resize-none border-0 bg-transparent p-2 text-base shadow-none focus-visible:ring-0"
                />
              </div>

              <div className="mt-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  {/* Speaker */}
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      render={
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-9 gap-1.5 rounded-md px-3 text-sm"
                        >
                          <Mic2 className="h-4 w-4 text-muted-foreground" />
                          <span className="max-w-[120px] truncate">
                            {speakers.find((s) => s.id === speakerId)?.name ??
                              t("composer.speaker")}
                          </span>
                          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                        </Button>
                      }
                    />
                    <DropdownMenuContent align="start" className="w-52">
                      <DropdownMenuLabel>{t("composer.speakerLabel")}</DropdownMenuLabel>
                      {speakers.map((s) => (
                        <DropdownMenuItem key={s.id} onClick={() => setSpeakerId(s.id)}>
                          <Mic2 className="mr-2 h-4 w-4 text-muted-foreground" />
                          <span className="flex-1 truncate">{s.name}</span>
                          {s.id === speakerId && <Check className="ml-2 h-4 w-4" />}
                        </DropdownMenuItem>
                      ))}
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

                  {/* Format */}
                  <Popover>
                    <PopoverTrigger
                      render={
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-9 gap-1.5 rounded-md px-3 text-sm"
                        >
                          <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
                          <span>{t("composer.format")}</span>
                          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                        </Button>
                      }
                    />
                    <PopoverContent align="start" className="w-72 space-y-3 p-3">
                      <div>
                        <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                          {t("composer.length")}
                        </p>
                        <div className="grid grid-cols-3 gap-1.5">
                          {lengths.map((l) => (
                            <button
                              key={l}
                              type="button"
                              onClick={() => setLength(l)}
                              className={cn(
                                "h-8 rounded-md border text-xs font-medium transition-colors",
                                length === l
                                  ? "border-primary bg-primary/10 text-foreground"
                                  : "border-border text-muted-foreground hover:bg-accent"
                              )}
                            >
                              {t(`composer.lengths.${l}`)}
                            </button>
                          ))}
                        </div>
                      </div>
                      <div>
                        <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                          {t("composer.variants")}
                        </p>
                        <div className="grid grid-cols-3 gap-1.5">
                          {variantOptions.map((n) => (
                            <button
                              key={n}
                              type="button"
                              onClick={() => setVariants(n)}
                              className={cn(
                                "h-8 rounded-md border text-xs font-medium transition-colors",
                                variants === n
                                  ? "border-primary bg-primary/10 text-foreground"
                                  : "border-border text-muted-foreground hover:bg-accent"
                              )}
                            >
                              {n}
                            </button>
                          ))}
                        </div>
                      </div>
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
                    disabled={!prompt.trim() || !speakerId || isGenerating}
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
        </div>

        {/* Tool row */}
        <div className="mt-12 flex w-full max-w-5xl flex-wrap items-start justify-center gap-x-3 gap-y-6">
          {tools.map((tool) => (
            <button
              key={tool.id}
              onClick={() => handleFeatureClick(t(`home.tools.${tool.id}`))}
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
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-card text-primary shadow-sm transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                <tool.icon className="h-6 w-6" />
              </div>
              <span className="text-center text-xs font-medium leading-tight">
                {t(`home.tools.${tool.id}`)}
              </span>
            </button>
          ))}
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

              <label className="flex items-center gap-2 rounded-full px-3 py-1.5">
                <Switch
                  size="sm"
                  checked={autoSave}
                  onCheckedChange={setAutoSave}
                />
                <span className="text-xs">{t("home.autoSave")}</span>
              </label>

              <label className="flex items-center gap-2 rounded-full px-3 py-1.5">
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
                  className="group flex flex-col gap-3 rounded-xl border bg-card/50 p-3 transition-colors hover:bg-accent"
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
    </div>
  )
}
