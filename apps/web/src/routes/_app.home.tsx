import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import { liveRecipeCards, type RecipeCard } from "@/lib/recipes"

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

      {/* Recipe cards (RECIPES §7): capability demos that prefill the
          composer and pin the task book. Only live cards render — a card
          ships when its capability is real (点亮纪律). */}
      {liveRecipeCards.length > 0 && (
        <section className="flex flex-col items-center px-6 pb-16">
          <div className="w-full max-w-3xl">
            <h2 className="mb-4 text-sm text-muted-foreground">
              {t("recipes.sectionTitle")}
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {liveRecipeCards.map((card) => (
                <RecipeCardView key={card.id} card={card} onSelect={setRecipe} />
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
