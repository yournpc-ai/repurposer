import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
import { Trans, useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import { fetchRecipeCards, type RecipeCard } from "@/lib/recipes"
import type { ChatMention } from "@/lib/mentions"

import { HomeComposer } from "@/components/home/HomeComposer"
import { RecipeCard as RecipeCardView } from "@/components/home/RecipeCard"
import type { SpeakerPickerEntry } from "@/components/home/SpeakerPickerModal"
import type { MentionEditorHandle } from "@/components/mentions/MentionEditor"

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
  const [cards, setCards] = useState<RecipeCard[]>([])
  // The draft (prompt + mentions) is the editor's reported mirror — the DOM
  // owns the text; Home keeps it as the send payload and acts on the editor
  // through `editorRef` (a card's Remix inserts its chip + template).
  const [prompt, setPrompt] = useState("")
  const [mentions, setMentions] = useState<ChatMention[]>([])
  const editorRef = useRef<MentionEditorHandle>(null)
  // The one card currently sounding (autoplay is muted; the toggle circle
  // unmutes one card at a time).
  const [soundingId, setSoundingId] = useState<string | null>(null)

  useEffect(() => {
    // Each fetch degrades to empty independently — a recipes-endpoint hiccup
    // must not take the composer's speakers/brands down with it.
    Promise.all([
      apiFetch("/api/v1/speakers")
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => []),
      apiFetch("/api/v1/brand-templates")
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => []),
      fetchRecipeCards().catch(() => []),
    ]).then(([s, bt, rc]) => {
      setSpeakers((s as Speaker[]) || [])
      setBrandTemplates(bt || [])
      setCards(rc)
    })
  }, [])

  // Remix (docs/tasks/recipe-mention.md §2.4): insert a recipe mention chip
  // INLINE into the sentence + the card's prompt template as visible,
  // editable text — appended when the user has already typed (their words
  // are never clobbered). The pinned task book resolves server-side from the
  // mention alone — never from a client-built prior.
  const handleRecipeSelect = (card: RecipeCard) => {
    editorRef.current?.insertMention({
      type: "recipe",
      id: card.id,
      label: t(`recipes.${card.id}.title`),
    })
    const template = t(`recipes.${card.id}.promptTemplate`)
    editorRef.current?.insertText(prompt.trim() ? `\n${template}` : template)
    editorRef.current?.focus()
  }

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
            speakers={speakers}
            brandTemplates={brandTemplates}
            prompt={prompt}
            onPromptChange={setPrompt}
            mentions={mentions}
            onMentionsChange={setMentions}
            editorRef={editorRef}
          />
        </div>
      </section>

      {/* Recipe gallery (RECIPES §7.3): vertical auto-playing teasers fed by
          the server registry (fetchRecipeCards); a live card's Remix inserts
          a mention chip into the composer above. */}
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
                  onSelect={handleRecipeSelect}
                />
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}
