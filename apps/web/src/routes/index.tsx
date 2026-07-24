import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"

import RotatingText from "@/components/RotatingText"
import { HomeComposer } from "@/components/home/HomeComposer"
import { RecentProjects } from "@/components/home/RecentProjects"

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
  const { t } = useTranslation()
  const [projectCount, setProjectCount] = useState(0)
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [brandTemplates, setBrandTemplates] = useState<BrandTemplate[]>([])
  const [mounted, setMounted] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    Promise.all([
      apiFetch("/api/v1/speakers").then((r) => r.json()),
      apiFetch("/api/v1/brand-templates").then((r) => (r.ok ? r.json() : [])),
    ]).then(([s, bt]) => {
      setSpeakers((s as Speaker[]) || [])
      setBrandTemplates(bt || [])
    })
  }, [])

  useEffect(() => {
    setMounted(true)
  }, [])

  const heroWords = t("home.heroWords", { returnObjects: true }) as string[]

  return (
    <div className="flex min-h-svh flex-1 flex-col">
      {/* Hero / Prompt */}
      <section className="flex flex-col items-center px-6 pt-16 pb-10">
        <div className="w-full max-w-3xl text-center">
          <h1 className="mb-4 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-4xl font-bold tracking-tight sm:text-5xl">
            <span>{t("home.heroPrefix")}</span>
            {mounted ? (
              <RotatingText
                texts={heroWords}
                rotationInterval={3000}
                splitBy="characters"
                staggerDuration={0.02}
                staggerFrom="random"
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
            onProjectCreated={() => setRefreshKey((k) => k + 1)}
          />
        </div>
      </section>

      {/* Projects */}
      <section className="px-6 pb-16">
        <div className="mx-auto w-full max-w-6xl">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-3">
            <span className="text-sm font-medium text-foreground">
              {t("home.allProjects", { count: projectCount })}
            </span>
          </div>

          <RecentProjects refreshKey={refreshKey} onCountChange={setProjectCount} />
        </div>
      </section>
    </div>
  )
}
