import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { MessageSquarePlus, Bell, Star } from "lucide-react"

import { apiFetch } from "@/lib/api"

import { Button } from "@/components/ui/button"
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

export const Route = createFileRoute("/")({
  component: Home,
})

function Home() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [projects, setProjects] = useState<Project[]>([])
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [brandTemplates, setBrandTemplates] = useState<BrandTemplate[]>([])
  const [error, setError] = useState("")
  const [mounted, setMounted] = useState(false)
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
            onGenerateStart={() => setError("")}
            onProjectCreated={() => setRefreshKey((k) => k + 1)}
            onError={setError}
          />

          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        </div>
      </section>

      {/* Projects */}
      <section className="px-6 pb-16">
        <div className="mx-auto w-full max-w-6xl">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-3">
            <span className="text-sm font-medium text-foreground">
              {t("home.allProjects", { count: projects.length })}
            </span>
          </div>

          <RecentProjects refreshKey={refreshKey} />
        </div>
      </section>
    </div>
  )
}
