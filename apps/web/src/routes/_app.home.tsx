import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"

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

export const Route = createFileRoute("/_app/home")({
  component: Home,
})

function Home() {
  const { t } = useTranslation()
  const [projectCount, setProjectCount] = useState(0)
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [brandTemplates, setBrandTemplates] = useState<BrandTemplate[]>([])
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

  return (
    <div className="flex min-h-svh flex-1 flex-col">
      {/* Workbench header + Composer */}
      <section className="flex flex-col items-center px-6 pt-16 pb-10">
        <div className="w-full max-w-3xl">
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
