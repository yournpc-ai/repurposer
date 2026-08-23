import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useRef, useState, type CSSProperties } from "react"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import { fetchRecipeCards, type RecipePublic } from "@/lib/recipes"
import type { ChatMention } from "@/lib/mentions"

import { HomeComposer } from "@/components/home/HomeComposer"
import { LogoMark } from "@/components/LogoMark"
import { RecipeCard as RecipeCardView } from "@/components/home/RecipeCard"
import { RecipeInspectOverlay } from "@/components/recipes/RecipeInspectOverlay"
import type { PersonaPickerEntry } from "@/components/home/PersonaPanel"
import type { MentionEditorHandle } from "@/components/mentions/MentionEditor"

type Persona = PersonaPickerEntry

export const Route = createFileRoute("/_app/home")({
  component: Home,
})

/** Scroll choreography (ADR-046 walkthrough pass 3, MiniMax parity): at rest
 * the cluster parks CENTER-STAGE (the 28vh spacer); scrolling slides it up
 * until the composer docks at the top as the one-line explore bar. The
 * subtitle folds over the first 160px; the composer's morph is SCROLL-LINKED
 * over the last 140px before the dock point (dockP — a pure function of
 * scrollTop, never a clock transition: the form always matches position
 * exactly, fast scrolls included; no thresholds, no hysteresis). The core
 * hero (the title) PERSISTS — it docks smaller above the bar. */
const HERO_SCROLL_PX = 160
const DOCK_WINDOW_PX = 140

function Home() {
  const { t } = useTranslation()
  const [personas, setPersonas] = useState<Persona[]>([])
  const [cards, setCards] = useState<RecipePublic[]>([])
  // The draft (prompt + mentions) is the editor's reported mirror — the DOM
  // owns the text; Home keeps it as the send payload and acts on the editor
  // through `editorRef`.
  const [prompt, setPrompt] = useState("")
  const [mentions, setMentions] = useState<ChatMention[]>([])
  const editorRef = useRef<MentionEditorHandle>(null)
  // Every live-card click (body or hover Remix, 2026-08-10) opens the inspect
  // overlay — inspect tabs + the launch zone (the composer's send mechanism
  // parked inside). The composer keeps only the manual @-mention path.
  const [inspecting, setInspecting] = useState<RecipePublic | null>(null)

  // App-shell surface: the route root is exactly the viewport tall (h-svh) and
  // NEVER scrolls — the dot grid it carries stays pinned to the viewport.
  // ONE scrollport holds everything (stage spacer / hero+composer chrome /
  // gallery), no scrollbar (MiniMax parity — position sense comes from
  // motion, not chrome).
  const scrollRef = useRef<HTMLDivElement>(null)
  const chromeRef = useRef<HTMLDivElement>(null)
  const subtitleRef = useRef<HTMLDivElement>(null)
  const titleRef = useRef<HTMLHeadingElement>(null)
  // The chrome's flow top = the docking scrollTop (offsetTop is unaffected by
  // scroll); the subtitle's rest height feeds its fold; the section title's
  // height feeds ITS identical fold (mirror copy — same morph family,
  // same RAF driver). All three measured on mount, re-measured on resize.
  const pinPointRef = useRef<number | null>(null)
  const [subtitleH, setSubtitleH] = useState<number | null>(null)
  const [titleH, setTitleH] = useState<number | null>(null)
  const [heroP, setHeroP] = useState(0)
  const [dockP, setDockP] = useState(0)

  useEffect(() => {
    const measure = () => {
      const chrome = chromeRef.current
      if (chrome) pinPointRef.current = chrome.offsetTop
      const sub = subtitleRef.current
      if (sub) setSubtitleH(sub.offsetHeight)
      const title = titleRef.current
      if (title) setTitleH(title.offsetHeight)
    }
    measure()
    window.addEventListener("resize", measure)
    return () => window.removeEventListener("resize", measure)
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    let raf = 0
    const onScroll = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const st = el.scrollTop
        setHeroP(Math.min(1, Math.max(0, st / HERO_SCROLL_PX)))
        const pin = pinPointRef.current
        setDockP(
          pin == null
            ? 0
            : Math.min(1, Math.max(0, (st - (pin - DOCK_WINDOW_PX)) / DOCK_WINDOW_PX)),
        )
      })
    }
    el.addEventListener("scroll", onScroll, { passive: true })
    return () => {
      el.removeEventListener("scroll", onScroll)
      cancelAnimationFrame(raf)
    }
  }, [])

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

  // Subtitle fold: copy-level fade + measured-height collapse (the gap below
  // it is padding, so the fold swallows it too). The TITLE never folds — it
  // is the core hero and docks smaller above the bar. The fold lives INSIDE
  // the chrome (below its top edge), so the docking point never moves.
  const subtitleStyle: CSSProperties = {
    maxHeight: subtitleH == null ? undefined : (1 - heroP) * subtitleH,
    opacity: 1 - heroP,
    transform: `translateY(${-12 * heroP}px)`,
    filter: heroP === 0 ? undefined : `blur(${heroP * 3}px)`,
    visibility: heroP >= 1 ? "hidden" : undefined,
  }

  // Section title — LITERAL MIRROR of subtitleStyle (every field, same
  // heroP driver, same 0–160px window). Subtitle FOLDS upward into the
  // chrome; h2 FOLDS upward into the chrome on the SAME scroll trigger
  // — two identical morphs on opposite sides of the chrome's top edge.
  // At rest (heroP=0): opacity 1, full height, no transform, no blur
  // (the earlier `opacity: titleP` mistake hid it at rest; using
  // heroP=0 at rest gives opacity 1 = visible).
  const titleStyle: CSSProperties = {
    maxHeight: titleH == null ? undefined : (1 - heroP) * titleH,
    opacity: 1 - heroP,
    transform: `translateY(${-12 * heroP}px)`,
    filter: heroP === 0 ? undefined : `blur(${heroP * 3}px)`,
    visibility: heroP >= 1 ? "hidden" : undefined,
  }

  return (
    <div className="h-svh dot-grid">
      <div ref={scrollRef} className="h-full overflow-y-auto no-scrollbar">
        {/* Rest offset — parks the hero+composer cluster center-stage. */}
        <div className="h-[28vh]" />

        {/* Hero + composer chrome — sticky: at rest the whole cluster sits
            center-stage in flow; scrolling docks it at the top (title
            persists smaller, composer morphs into the one-line explore bar).
            The backdrop (page fill + the same dot grid, scroll-linked
            opacity) keeps wider gallery cards from peeking beside the
            narrower bar; generous clear space hangs below the docked bar (pb-14),
            then the 32px bottom mask dissolves whatever passes. */}
        <div
          ref={chromeRef}
          className="sticky top-0 z-20 px-4 pt-3 pb-14 [mask-image:linear-gradient(to_bottom,black_calc(100%-32px),transparent)]"
        >
          <div
            aria-hidden
            className="absolute inset-0 -z-10 bg-background dot-grid"
            style={{ opacity: dockP }}
          />
          <div className="mx-auto w-full max-w-3xl">
            {/* Studio hero (MiniMax anatomy, 2026-08-21): the BRAND LOCKUP
                (LogoMark + wordmark — the core hero, persists and docks
                smaller; the mark sizes in em so it scales with the font) +
                the category line (你的自媒体Agent团队 — folds away on
                scroll). Colors: brand = foreground, tagline =
                muted-foreground — no two-tone leftovers. */}
            <h1
              className={`mb-3 flex items-center justify-center gap-2.5 font-display font-medium tracking-tight text-foreground transition-all duration-300 ${
                dockP >= 1 ? "text-xl" : "text-3xl sm:text-4xl"
              }`}
            >
              <LogoMark className="h-[1.05em] w-[1.05em]" />
              <span>Repurposer</span>
            </h1>
            <div
              ref={subtitleRef}
              style={subtitleStyle}
              className="overflow-hidden"
            >
              <p className="mx-auto max-w-xl pb-12 text-center text-sm leading-relaxed text-muted-foreground sm:text-base">
                {t("home.brandTagline")}
              </p>
            </div>
            <HomeComposer
              dockP={dockP}
              personas={personas}
              prompt={prompt}
              onPromptChange={setPrompt}
              mentions={mentions}
              onMentionsChange={setMentions}
              editorRef={editorRef}
            />
          </div>
        </div>

        {/* Recipe gallery (recipe-gallery v2, ADR-048): uniform 4-column grid
            of process-schematic covers — no real media on the card face, no
            featured spans, no masonry. Card order = registry insertion order
            (RECIPES §4: row 1 video sources, row 2 text/image sources).
            Every click opens the inspect overlay — the ONLY launch path
            (ADR-040). */}
        <section className="flex flex-col items-center px-4 pt-3 pb-10 sm:px-6 sm:pt-4 sm:pb-16">
          <div className="w-full max-w-6xl">
            <h2
              ref={titleRef}
              style={titleStyle}
              className="mb-6 overflow-hidden text-center text-base font-medium text-balance sm:text-lg md:text-xl"
            >
              {t("recipes.sectionTitle")}
            </h2>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
              {cards.map((card, index) => (
                <div
                  key={card.id}
                  data-tour={index === 0 ? "home-recipes" : undefined}
                >
                  <RecipeCardView
                    card={card}
                    onInspect={(c) => {
                      // The overlay owns attention from here.
                      setInspecting(c)
                    }}
                  />
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>

      {inspecting && (
        <RecipeInspectOverlay
          card={inspecting}
          onClose={() => setInspecting(null)}
        />
      )}
    </div>
  )
}
