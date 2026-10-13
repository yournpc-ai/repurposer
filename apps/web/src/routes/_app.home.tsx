import { createFileRoute } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import { fetchRecipeCards, type RecipePublic } from "@/lib/recipes"
import type { ChatMention } from "@/lib/mentions"

import { HomeComposer } from "@/components/home/HomeComposer"
import { LogoMark } from "@/components/LogoMark"
import { RecipeTabs } from "@/components/home/RecipeTabs"
import { RecipeShelf } from "@/components/home/RecipeShelf"
import { resolveRecipeFamilies } from "@/components/home/recipeFamilies"
import type { PersonaPickerEntry } from "@/components/composer/PersonaPanel"
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

  // App-shell surface: the route root is exactly the viewport tall (h-svh) and
  // NEVER scrolls.
  // ONE scrollport holds everything (stage spacer / hero+composer chrome /
  // recipe shelf), no scrollbar (MiniMax parity — position sense comes from
  // motion, not chrome).
  const scrollRef = useRef<HTMLDivElement>(null)
  const chromeRef = useRef<HTMLDivElement>(null)
  const subtitleRef = useRef<HTMLDivElement>(null)
  // The chrome's flow top = the docking scrollTop (offsetTop is unaffected by
  // scroll); the subtitle's rest height feeds its fold. Both measured on
  // mount, re-measured on resize.
  const pinPointRef = useRef<number | null>(null)
  const [subtitleH, setSubtitleH] = useState<number | null>(null)
  const [heroP, setHeroP] = useState(0)
  const [dockP, setDockP] = useState(0)

  useEffect(() => {
    const measure = () => {
      const chrome = chromeRef.current
      if (chrome) pinPointRef.current = chrome.offsetTop
      const sub = subtitleRef.current
      if (sub) setSubtitleH(sub.offsetHeight)
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
    // must not take the composer's personas down with it (and with zero
    // cards the shelf simply renders nothing — 无真内容不上架).
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

  // Anchor the composer on focus: when the user clicks the prompt band (or
  // tabs into it), scroll all the way back to the rest state (scrollTop=0).
  // The morph is scroll-linked, so a docked chrome snaps back to the
  // expanded composer card the moment the scrollTop lands at zero — no
  // half-measure: half-scroll leaves the chrome mid-collapse and the band
  // in an awkward hybrid pose. Full-back is the only state worth focusing
  // the prompt in.
  const handleComposerFocus = useCallback(() => {
    const container = scrollRef.current
    if (!container) return
    if (container.scrollTop === 0) return
    container.scrollTo({ top: 0, behavior: "smooth" })
  }, [])

  // 卡片点击唯一归宿 (D5 禁则 8): composer 预填 — never a template editor.
  // clear + insertText REPLACES the draft (prototype parity; the staged
  // files ride untouched — the chips band is the valuable payload, the text
  // is the recipe's launch template). insertText focuses the editor, and
  // the band's onFocus above scrolls the chrome back to rest — the shelf
  // lives below the fold, so the prefill lands center-stage.
  const handlePrefill = useCallback(
    (prefillKey: string) => {
      editorRef.current?.clear()
      editorRef.current?.insertText(t(prefillKey))
    },
    [t],
  )

  // Two-level tab shelf (D5, prototype 屏①): families × subs × horizontal
  // shelves, resolved data-driven — a family without real content never
  // renders (上架纪律: 无真 demo 不上架). The selection is the route's; the
  // per-family sub memory survives family hops (prototype parity), and an
  // invalidated selection (cards refetch) falls back to the first seat.
  const families = useMemo(() => resolveRecipeFamilies(cards), [cards])
  const [activeFamilyId, setActiveFamilyId] = useState<string | null>(null)
  const [subByFamily, setSubByFamily] = useState<Record<string, string>>({})
  const activeFamily =
    families.find((f) => f.id === activeFamilyId) ?? families[0] ?? null
  const activeSub =
    activeFamily?.subs.find((s) => s.id === subByFamily[activeFamily.id]) ??
    activeFamily?.subs[0] ??
    null

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

  return (
    <div className="h-svh">
      <div ref={scrollRef} className="h-full overflow-y-auto no-scrollbar">
        {/* Rest offset — parks the hero+composer cluster center-stage while
            letting the shelf peek above the fold (the page's gravity cue
            that there is more below). */}
        <div className="h-[20vh]" />

        {/* Hero + composer chrome — sticky: at rest the whole cluster sits
            center-stage in flow; scrolling docks it at the top (title
            persists smaller, composer morphs into the one-line explore bar).
            The backdrop (page fill, scroll-linked opacity) keeps shelf cards
            from peeking beside the narrower bar; the clear space below the
            bar interpolates 48→56px with dockP (rest-state shelf rhythm ↔
            docked-bar protection, same pure-function interpolation as every
            other morph — no clocks), then the 32px bottom mask dissolves
            whatever passes. */}
        <div
          ref={chromeRef}
          className="sticky top-0 z-20 px-4 pt-3 [mask-image:linear-gradient(to_bottom,black_calc(100%-32px),transparent)]"
          style={{ paddingBottom: 48 + 8 * dockP }}
        >
          <div
            aria-hidden
            className="absolute inset-0 -z-10 bg-background"
            style={{ opacity: dockP }}
          />
          <div className="mx-auto w-full max-w-2xl">
            {/* Studio hero (MiniMax anatomy, 2026-08-21): the BRAND LOCKUP
                (LogoMark + wordmark — the core hero, persists and docks
                smaller; the mark sizes in em so it scales with the font) +
                the category line (你的自媒体Agent团队 — folds away on
                scroll). Colors: brand = foreground, tagline =
                muted-foreground — no two-tone leftovers. */}
            <h1
              className={`mb-3 flex items-center justify-center gap-2 font-display font-medium tracking-tight text-foreground transition-all duration-300 ${
                dockP >= 1 ? "text-xl" : "text-3xl sm:text-4xl"
              }`}
            >
              {/* The mark sizes in em so it scales with the font; 0.9em lands
                  the square on the wordmark's CAP HEIGHT (1em+ floats it
                  above the glyphs' optical center). */}
              <LogoMark className="h-[0.9em] w-[0.9em]" />
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
              onFocus={handleComposerFocus}
            />
          </div>
        </div>

        {/* Recipe shelf (D5, flora-parity-ui 批): the two-level tab track
            (families × subs) sits IN FLOW below the composer chrome, then
            the active sub's horizontal shelves. Cards reuse RecipeCard
            (schematic covers); MG families render real demo videos
            loop/muted. Every card click prefills the composer — the ONLY
            destination (禁则 8, 永不是模板编辑器). */}
        <section className="flex flex-col items-center px-4 pb-[max(64px,40vh)] sm:px-6">
          <div className="w-full max-w-6xl">
            {activeFamily && (
              <>
                <RecipeTabs
                  families={families}
                  activeFamilyId={activeFamily.id}
                  activeSubId={activeSub?.id ?? null}
                  onSelectFamily={setActiveFamilyId}
                  onSelectSub={(familyId, subId) =>
                    setSubByFamily((m) => ({ ...m, [familyId]: subId }))
                  }
                />
                <div className="mt-8 flex flex-col gap-8">
                  {activeSub?.shelves.map((shelf, shelfIndex) => (
                    <RecipeShelf
                      key={shelf.id}
                      title={t(`recipes.shelf.titles.${shelf.id}`)}
                      items={shelf.items}
                      onPrefill={handlePrefill}
                      // Tour step 3 anchors the FIFTH card of the templates
                      // family's first shelf (row-1 mid on wide viewports):
                      // the tour's scrollIntoView block:"center" centers it,
                      // so the shelf fills the viewport under the docked
                      // composer bar at any screen height. Fewer than 5
                      // cards → the step auto-skips.
                      tourAnchorIndex={
                        activeFamily.id === "templates" && shelfIndex === 0
                          ? 4
                          : undefined
                      }
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
