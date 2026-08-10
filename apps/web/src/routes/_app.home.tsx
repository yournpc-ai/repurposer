import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
import { Trans, useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import { fetchRecipeCards, type RecipeCard } from "@/lib/recipes"
import type { ChatMention } from "@/lib/mentions"

import { HomeComposer } from "@/components/home/HomeComposer"
import { RecipeCard as RecipeCardView } from "@/components/home/RecipeCard"
import { RecipeInspectOverlay } from "@/components/recipes/RecipeInspectOverlay"
import type { PersonaPickerEntry } from "@/components/home/PersonaPickerModal"
import type { MentionEditorHandle } from "@/components/mentions/MentionEditor"

type Persona = PersonaPickerEntry

export const Route = createFileRoute("/_app/home")({
  component: Home,
})

function Home() {
  const { t } = useTranslation()
  const [personas, setPersonas] = useState<Persona[]>([])
  const [cards, setCards] = useState<RecipeCard[]>([])
  // The draft (prompt + mentions) is the editor's reported mirror — the DOM
  // owns the text; Home keeps it as the send payload and acts on the editor
  // through `editorRef`.
  const [prompt, setPrompt] = useState("")
  const [mentions, setMentions] = useState<ChatMention[]>([])
  const editorRef = useRef<MentionEditorHandle>(null)
  // The one card currently sounding (autoplay is muted; the toggle circle
  // unmutes one card at a time).
  const [soundingId, setSoundingId] = useState<string | null>(null)
  // Every live-card click (body or hover Remix, 2026-08-10) opens the inspect
  // overlay — inspect tabs + the launch zone (the composer's send mechanism
  // parked inside). The composer keeps only the manual @-mention path.
  const [inspecting, setInspecting] = useState<RecipeCard | null>(null)

  useEffect(() => {
    // Each fetch degrades to empty independently — a recipes-endpoint hiccup
    // must not take the composer's personas down with it.
    Promise.all([
      apiFetch("/api/v1/personas")
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => []),
      fetchRecipeCards().catch(() => []),
    ]).then(([s, rc]) => {
      setPersonas((s as Persona[]) || [])
      setCards(rc)
    })
  }, [])

  return (
    // flex-1 (inside SidebarInset's flex column) fills the viewport minus
    // the sticky header exactly — never min-h-svh here: that would add the
    // full viewport height BELOW the header and pin a permanent scrollbar.
    <div className="flex flex-1 flex-col">
      {/* Studio header + Composer */}
      <section className="flex flex-col items-center px-4 pt-2 pb-10">
        {/* Two-line studio welcome: a reception hello (users arrive here
            already convinced by the landing page) + a spec note (full-length
            talks accepted) — practical orientation only, no positioning.
            Monochrome contrast accent, no hue, per design language. */}
        <h1 className="mb-3 max-w-2xl text-balance text-center font-display text-3xl font-medium tracking-tight text-muted-foreground sm:text-4xl">
          <Trans
            i18nKey="home.welcomeTitle"
            components={{ b: <span className="text-foreground" /> }}
          />
        </h1>
        <p className="mb-10 max-w-xl text-center text-sm leading-relaxed text-muted-foreground sm:text-base">
          <Trans
            i18nKey="home.welcomeSubtitle"
            components={{ b: <strong className="font-medium text-foreground" /> }}
          />
        </p>
        <div className="w-full max-w-3xl">
          <HomeComposer
            personas={personas}
            prompt={prompt}
            onPromptChange={setPrompt}
            mentions={mentions}
            onMentionsChange={setMentions}
            editorRef={editorRef}
          />
        </div>
      </section>

      {/* Recipe gallery (RECIPES §7.3): vertical auto-playing teasers fed by
          the server registry (fetchRecipeCards); every live-card click opens
          the inspect overlay with the launch zone inside. */}
      <section className="flex flex-col items-center px-6 pb-16">
        <div className="w-full max-w-6xl">
          <h2 className="mb-6 text-center text-xl font-medium">
            {t("recipes.sectionTitle")}
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {cards.map((card, index) => (
              <div key={card.id} data-tour={index === 0 ? "home-recipes" : undefined}>
                <RecipeCardView
                  card={card}
                  sounding={soundingId === card.id}
                  onToggleSound={(id) =>
                    setSoundingId((prev) => (prev === id ? null : id))
                  }
                  onInspect={setInspecting}
                />
              </div>
            ))}
          </div>
        </div>
      </section>

      {inspecting && (
        <RecipeInspectOverlay
          card={inspecting}
          onClose={() => setInspecting(null)}
        />
      )}
    </div>
  )
}
