import { createFileRoute } from "@tanstack/react-router"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import type { ChatMention } from "@/lib/mentions"
import { fetchChatSkills, skillOptionForReference, type SkillOption } from "@/lib/skills"
import { consumeLandingCreate } from "@/lib/landingCreate"

import { HomeComposer } from "@/components/home/HomeComposer"
import type { PersonaPickerEntry } from "@/components/composer/PersonaPanel"
import type { MentionEditorHandle } from "@/components/mentions/MentionEditor"

type Persona = PersonaPickerEntry

export const Route = createFileRoute("/_app/home")({
  component: Home,
})

/** Scroll choreography (2026-10 bottom-dock ruling): the hero cluster
 * (one-line question + composer card) is plain IN-FLOW content — it
 * scrolls away naturally and NOTHING sticks at the top. ONE scroll-linked
 * effect survives: the composer morphs card → one-line bar over the last
 * DOCK_WINDOW_PX before its slot exits the viewport top (dockP — a pure
 * function of scrollTop, never a clock transition: the form always matches
 * position exactly, fast scrolls included; no thresholds, no hysteresis).
 * Once the slot is fully out of view, the SAME composer DOM flips to `fixed`
 * as the stadium bar at the viewport BOTTOM — zero reparent, the
 * MentionEditor never unmounts. The slot reserves its exact height at the
 * flip moment, so docking changes NOTHING about scroll geometry: near the
 * bottom of the page no layout dimension is a function of scrollTop, which
 * kills the scrollTop-clamping feedback loop (the title-jitter class) by
 * construction. The tab track pins at the top instead (plain sticky top-0,
 * no measurement). */
const DOCK_WINDOW_PX = 140

function Home() {
  const { t } = useTranslation()
  const [personas, setPersonas] = useState<Persona[]>([])
  // The draft (prompt + mentions) is the editor's reported mirror — the DOM
  // owns the text; Home keeps it as the send payload and acts on the editor
  // through `editorRef`.
  const [prompt, setPrompt] = useState("")
  const [mentions, setMentions] = useState<ChatMention[]>([])
  const [skillOptions, setSkillOptions] = useState<SkillOption[]>([])
  const [selectedSkill, setSelectedSkill] = useState<SkillOption | null>(null)
  const editorRef = useRef<MentionEditorHandle>(null)
  // App-shell surface: the route root is exactly the viewport tall (h-svh) and
  // NEVER scrolls.
  // ONE scrollport holds everything (stage spacer / hero / composer slot /
  // recipe shelf), no scrollbar (MiniMax parity — position sense comes from
  // motion, not chrome).
  const scrollRef = useRef<HTMLDivElement>(null)
  const slotRef = useRef<HTMLDivElement>(null)
  // The composer slot's flow top = the morph's end point (offsetTop is
  // unaffected by scroll). Measured on mount, re-measured on resize.
  const pinPointRef = useRef<number | null>(null)
  const dockedRef = useRef(false)
  const [dockP, setDockP] = useState(0)
  // docked = the composer rides as the fixed bottom bar. slotH = the slot's
  // height reserved at the flip moment — the morph completes 140px BEFORE the
  // flip point, so the composer is always the 56px bar when it docks and the
  // reservation is exact (a wrong reservation would shift scroll geometry at
  // the flip and resurrect the feedback loop).
  const [docked, setDocked] = useState(false)
  const [slotH, setSlotH] = useState<number | null>(null)
  // The docked bar's horizontal seat is MEASURED, not re-derived: a fixed
  // bar centering itself on the VIEWPORT (mx-auto) lands off-center
  // whenever the sidebar shifts the content area, and `absolute` is no
  // escape (an absolutely-positioned descendant of a scroller scrolls away
  // with the content — only `fixed` escapes). The slot's viewport rect
  // already carries the sidebar's displacement, so the fixed bar takes its
  // left/width verbatim. Two refresh paths, nothing more: every scroll
  // frame (covers the flip moment), and a per-frame poll while docked
  // (covers sidebar width transitions / window resizes when the user isn't
  // scrolling). The set-state guard keeps the poll render-free.
  const [slotRect, setSlotRect] = useState<{
    left: number
    width: number
  } | null>(null)

  const measureRect = useCallback(() => {
    const slot = slotRef.current
    if (!slot) return
    const r = slot.getBoundingClientRect()
    setSlotRect((prev) =>
      prev && prev.left === r.left && prev.width === r.width
        ? prev
        : { left: r.left, width: r.width },
    )
  }, [])

  // While docked the bar's seat must track EVERY drift source (sidebar
  // width transition, window resize, zoom) — poll per animation frame.
  useEffect(() => {
    if (!docked) return
    let raf = 0
    const loop = () => {
      measureRect()
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [docked, measureRect])

  useEffect(() => {
    const measure = () => {
      const slot = slotRef.current
      if (slot) pinPointRef.current = slot.offsetTop
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
        const slot = slotRef.current
        const pin = pinPointRef.current
        // Keep the dock seat fresh on every scroll frame too — the flip
        // moment reads it below.
        measureRect()
        const dock =
          pin == null
            ? 0
            : Math.min(
                1,
                Math.max(0, (st - (pin - DOCK_WINDOW_PX)) / DOCK_WINDOW_PX),
              )
        setDockP(dock)
        // Fixed-bottom flip: the composer is fully above the viewport once
        // scrollTop passes the slot's bottom edge. The slot reserves its
        // height while docked, so the flip itself never moves content — the
        // threshold cannot flap by construction.
        if (slot && pin != null) {
          const exited = st > pin + slot.offsetHeight
          if (exited !== dockedRef.current) {
            dockedRef.current = exited
            if (exited) setSlotH(slot.offsetHeight)
            setDocked(exited)
          }
        }
      })
    }
    el.addEventListener("scroll", onScroll, { passive: true })
    return () => {
      el.removeEventListener("scroll", onScroll)
      cancelAnimationFrame(raf)
    }
  }, [measureRect])

  useEffect(() => {
    Promise.all([
      apiFetch("/api/v1/personas").then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetchChatSkills().catch(() => ({ items: [] })),
    ]).then(([personaRows, skills]) => {
      setPersonas((personaRows as Persona[]) || [])
      setSkillOptions(skills.items)
    })
  }, [])

  // Bring an in-flow composer back into view before asking the user to edit
  // the prefill. The home root never scrolls, so measure against the ONE
  // internal scrollport; a docked composer is already visible and needs no
  // camera move at all.
  const scrollComposerIntoView = useCallback(() => {
    const scroller = scrollRef.current
    const slot = slotRef.current
    if (!scroller || !slot) return
    const scrollerRect = scroller.getBoundingClientRect()
    const slotRect = slot.getBoundingClientRect()
    const top =
      slotRect.top -
      scrollerRect.top +
      scroller.scrollTop -
      (scroller.clientHeight - slotRect.height) / 2
    scroller.scrollTo({ top, behavior: "smooth" })
  }, [])

  // 卡片点击唯一归宿 (D5 禁则 8): composer 预填 — never a template editor.
  // 不静默覆盖 (home 内容扩展批): the draft is REPLACED only when it's empty
  // or still IS the previous card prefill verbatim (clicking between cards
  // swaps the template); a draft carrying the user's own text or @-mentions
  // is kept — the new prompt appends below on a blank line. Staged chips
  // never ride this path (they live outside the draft). A visible
  // placeholder is the recipe's only blank: insert it selected so paste
  // replaces it in one gesture; prompts without the blank simply skip the
  // selection (selectText no-ops on a missing needle).
  const lastPrefillRef = useRef<string | null>(null)
  const handlePrefill = useCallback(
    (prefillKey: string, skill?: SkillOption) => {
      const placeholder = t("recipes.shelf.urlPlaceholder")
      const text = t(prefillKey, { placeholder })
      const previousSkill = selectedSkill
      const draft = prompt.trim()
      const replaceable =
        mentions.length === 0 &&
        (draft === "" || draft === lastPrefillRef.current)
      if (replaceable) {
        editorRef.current?.clear({ preserveSkill: true })
        editorRef.current?.insertText(text)
      } else {
        editorRef.current?.insertText(`\n\n${text}`)
      }
      lastPrefillRef.current = text.trim()
      setSelectedSkill(skill ?? previousSkill)
      editorRef.current?.selectText(placeholder)
      if (!docked) scrollComposerIntoView()
    },
    [t, prompt, mentions, selectedSkill, docked, scrollComposerIntoView],
  )

  // A landing product card survives the login detour and resolves against the
  // live catalog here. Consumption is one-shot; it never sends the draft.
  useEffect(() => {
    if (skillOptions.length === 0) return
    const handoff = consumeLandingCreate()
    if (!handoff) return
    handlePrefill(
      handoff.promptKey,
      skillOptionForReference(handoff.skill, skillOptions),
    )
  }, [handlePrefill, skillOptions])

  return (
    // App-shell surface: the root is exactly the viewport tall and NEVER
    // scrolls (one inner scrollport holds everything). Below md the glass
    // MobileHeader occupies the 3.5rem above — the root pulls UP under it
    // (-mt-14) instead of yielding height: frosted glass only reads when
    // content scrolls UNDER it, and a stacked-below scrollport would give
    // the blur nothing to blur (white veil over white page = a solid white
    // bar). The pinned tabs bar compensates with max-md:top-14 below.
    <div className="h-svh max-md:-mt-14">
      <div ref={scrollRef} className="h-full overflow-x-hidden overflow-y-auto no-scrollbar">
        {/* Rest offset — anchors the hero cluster near the top (~15% of the
            viewport, the reference rhythm) while letting the shelf peek
            above the fold (the page's gravity cue that there is more
            below). */}
        <div className="h-[14vh]" />

        {/* Hero + composer — plain in-flow content: the cluster scrolls away
            as one body, nothing pins at the top. */}
        <div className="px-4 pt-3">
          <div className="mx-auto w-full max-w-2xl">
            {/* Studio hero: ONE question line whose only job is pointing at
                the composer below (the page's sole destination) — the
                rotating placeholder answers it with three example prompts.
                The brand name is NOT repeated here: it lives in the sidebar
                lockup and the composer placeholder prefix ("Ask Repurposer
                to …"). foreground + font-display, centered, STATIC — it
                scrolls away with the page. */}
            <h1 className="mb-8 text-center font-display text-2xl font-medium tracking-tight text-foreground sm:text-3xl">
              {t("home.heroQuestion")}
            </h1>

            {/* Composer slot: reserves the bar's height once the composer has
                flipped to the fixed bottom bar (dock = the SAME DOM, zero
                reparent — the MentionEditor never unmounts and the draft
                survives). The reserved height makes the flip scroll-neutral
                by construction; the entrance animation is transform/opacity
                only (a clock transition on a DISCRETE flip is legal — the
                scroll-linked morph itself never uses clocks). */}
            <div
              ref={slotRef}
              style={{ height: docked ? (slotH ?? undefined) : undefined }}
            >
              <div
                className={
                  docked
                    ? "home-dock-in fixed inset-x-0 bottom-[max(16px,env(safe-area-inset-bottom))] z-40"
                    : undefined
                }
                style={
                  docked && slotRect
                    ? { left: slotRect.left, width: slotRect.width }
                    : undefined
                }
              >
                {/* The fixed form's width/left come from the slot's measured
                    viewport rect (see slotRect) — a viewport-centered recipe
                    (mx-auto) would ignore the sidebar's displacement and
                    land off-center in the content area. In flow these
                    wrappers are transparent blocks. */}
                <div className={docked ? "w-full" : undefined}>
                  <HomeComposer
                    dockP={dockP}
                    dockedAtBottom={docked}
                    personas={personas}
                    prompt={prompt}
                    onPromptChange={setPrompt}
                    mentions={mentions}
                    onMentionsChange={setMentions}
                    selectedSkill={selectedSkill}
                    onSkillChange={setSelectedSkill}
                    editorRef={editorRef}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="min-h-[45vh]" />
      </div>
    </div>
  )
}
