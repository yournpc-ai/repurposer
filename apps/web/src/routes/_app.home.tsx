import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"

import { apiFetch } from "@/lib/api"

import { HomeComposer } from "@/components/home/HomeComposer"
import type { SpeakerPickerEntry } from "@/components/home/SpeakerPickerModal"

type Speaker = SpeakerPickerEntry

interface BrandTemplate {
  id: string
  name: string
}

export const Route = createFileRoute("/_app/home")({
  component: Home,
})

function Home() {
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [brandTemplates, setBrandTemplates] = useState<BrandTemplate[]>([])

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
          <HomeComposer speakers={speakers} brandTemplates={brandTemplates} />
        </div>
      </section>
    </div>
  )
}
