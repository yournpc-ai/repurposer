import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import { RECIPE_CARDS, type RecipeCard } from "@/lib/recipes"

import { HomeComposer } from "@/components/home/HomeComposer"
import { RecipeCard as RecipeCardView } from "@/components/home/RecipeCard"
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
  const { t } = useTranslation()
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [brandTemplates, setBrandTemplates] = useState<BrandTemplate[]>([])
  // The picked recipe lives here — the common parent of the card grid and
  // the composer (state lift stops at Home, never goes global).
  const [recipe, setRecipe] = useState<RecipeCard | null>(null)
  // The one card currently sounding (autoplay is muted; the toggle circle
  // unmutes one card at a time).
  const [soundingId, setSoundingId] = useState<string | null>(null)

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
            recipe={recipe}
          />
        </div>
      </section>

      {/* Recipe gallery (RECIPES §7.3): vertical auto-playing teasers, one
          row of four — remixing a live card prefills the composer and pins
          the task book; reserved cards stay visible with a Soon pill
          (presence over gating, 2026-07-31). */}
      <section className="flex flex-col items-center px-6 pb-16">
        <div className="w-full max-w-5xl">
          <h2 className="mb-4 text-sm text-muted-foreground">
            {t("recipes.sectionTitle")}
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {RECIPE_CARDS.map((card) => (
              <RecipeCardView
                key={card.id}
                card={card}
                sounding={soundingId === card.id}
                onToggleSound={(id) =>
                  setSoundingId((prev) => (prev === id ? null : id))
                }
                onSelect={setRecipe}
              />
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}
