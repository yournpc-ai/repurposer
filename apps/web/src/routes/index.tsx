import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  MessageSquarePlus,
  Linkedin,
  Quote,
  Languages,
  Newspaper,
  Lightbulb,
  FileText,
  Presentation,
  PenTool,
  Images,
  Bell,
  Star,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { apiFetch } from "@/lib/api"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { LanguageSwitcher } from "@/components/language-switcher"
import { ThemeToggle } from "@/components/theme-toggle"
import RotatingText from "@/components/RotatingText"
import { HomeComposer } from "@/components/home/HomeComposer"
import { RecentProjects } from "@/components/home/RecentProjects"

interface Project {
  id: string
  title: string
  status: string
}

interface Speaker {
  id: string
  name: string
}

interface BrandTemplate {
  id: string
  name: string
}

const OUTPUT_OPTIONS = ["clips", "linkedin", "quote_cards", "summary"] as const
type OutputKey = (typeof OUTPUT_OPTIONS)[number]

const tools = [
  { icon: Linkedin, id: "linkedinPost", outputKey: "linkedin", isNew: false },
  { icon: Quote, id: "quoteCard", outputKey: "quote_cards", isNew: false },
  { icon: Languages, id: "multiLangSummary", outputKey: "summary", isNew: false },
  { icon: Newspaper, id: "newsletter", outputKey: null, isNew: false },
  { icon: Lightbulb, id: "keyInsights", outputKey: null, isNew: true },
  { icon: FileText, id: "onePager", outputKey: null, isNew: false },
  { icon: Presentation, id: "slides", outputKey: null, isNew: true },
  { icon: PenTool, id: "blogPost", outputKey: null, isNew: false },
  { icon: Images, id: "socialCarousel", outputKey: null, isNew: true },
] as const

export const Route = createFileRoute("/")({
  component: Home,
})

function Home() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [projects, setProjects] = useState<Project[]>([])
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [brandTemplates, setBrandTemplates] = useState<BrandTemplate[]>([])
  const [outputs, setOutputs] = useState<OutputKey[]>([
    "linkedin",
    "quote_cards",
    "summary",
  ])
  const [error, setError] = useState("")
  const [mounted, setMounted] = useState(false)
  const [autoSave, setAutoSave] = useState(true)
  const [autoImport, setAutoImport] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    Promise.all([
      apiFetch("/api/v1/speakers").then((r) => r.json()),
      apiFetch("/api/v1/projects").then((r) => r.json()),
      apiFetch("/api/v1/brand-templates").then((r) => (r.ok ? r.json() : [])),
    ]).then(([s, p, bt]) => {
      setSpeakers((s as Speaker[]) || [])
      setProjects(p || [])
      setBrandTemplates(bt || [])
    })
  }, [])

  useEffect(() => {
    setMounted(true)
  }, [])

  const heroWords = t("home.heroWords", { returnObjects: true }) as string[]

  const handleToolClick = (tool: (typeof tools)[number]) => {
    if (tool.outputKey) {
      setOutputs((prev) =>
        prev.includes(tool.outputKey as OutputKey)
          ? prev.filter((o) => o !== tool.outputKey)
          : [...prev, tool.outputKey as OutputKey]
      )
      return
    }
    setError(t("home.comingSoon"))
    setTimeout(() => setError(""), 2000)
  }

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

          <HomeComposer
            speakers={speakers}
            brandTemplates={brandTemplates}
            outputs={outputs}
            onOutputsChange={setOutputs}
            onGenerateStart={() => setError("")}
            onProjectCreated={() => setRefreshKey((k) => k + 1)}
            onError={setError}
          />

          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        </div>

        {/* Tool row */}
        <div className="mt-12 flex w-full max-w-5xl flex-wrap items-start justify-center gap-x-3 gap-y-6">
          {tools.map((tool) => {
            const active = tool.outputKey
              ? outputs.includes(tool.outputKey as OutputKey)
              : false
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
            </div>

            <div className="flex items-center gap-4 text-sm">
              <span className="text-muted-foreground">{t("home.storage")}</span>

              <label className="flex items-center gap-2 rounded-md px-3 py-1.5">
                <Switch size="sm" checked={autoSave} onCheckedChange={setAutoSave} />
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

          <RecentProjects refreshKey={refreshKey} />
        </div>
      </section>
    </div>
  )
}
