"use client"

import { useEffect, useMemo, useState, type CSSProperties, type RefObject } from "react"
import { useTranslation } from "react-i18next"
import { ArrowUp, Box, Paperclip, User } from "lucide-react"

import { useProjectLaunch } from "@/lib/useProjectLaunch"
import { fileKindOf, type ChatMention } from "@/lib/mentions"
import {
  MentionEditor,
  type MentionEditorHandle,
} from "@/components/mentions/MentionEditor"

import { Button } from "@/components/ui/button"
import { InputGroup, InputGroupAddon } from "@/components/ui/input-group"
import { AssetChips } from "@/components/home/AssetChips"
import { AssetsPanel } from "@/components/home/AssetsPanel"
import { ModelsPanel } from "@/components/home/ModelsPanel"
import {
  PersonaPanel,
  type PersonaPickerEntry,
} from "@/components/home/PersonaPanel"
import { Tour, type TourStep } from "@/components/ui/tour"
import { tourCopy, tourVersionOf, type TourStepDef } from "@/lib/tour"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

type Persona = PersonaPickerEntry

interface HomeComposerProps {
  personas: Persona[]
  /** Scroll-LINKED morph (ADR-046 walkthrough pass 3): 0 = expanded hero
   * card, 1 = the docked one-line explore bar (stadium / half-radius). Every
   * morph property is an interpolation of this scroll progress — NEVER a
   * clock transition: the form always matches the scroll position exactly
   * (fast scroll = fast morph, zero lag, zero threshold flap). */
  dockP?: number
  onGenerateStart?: () => void
  /** The draft (prompt + mentions) is the editor's reported mirror — the DOM
   * owns the text (MentionEditor); Home keeps it only as the send payload. */
  prompt: string
  onPromptChange: (value: string) => void
  mentions: ChatMention[]
  onMentionsChange: (value: ChatMention[]) => void
  editorRef: RefObject<MentionEditorHandle | null>
  /** Fired when the prompt band (or any descendant — the MentionEditor
   * contentEditable) gains focus via click or keyboard. The home route
   * uses this to scroll the band back into view if the page has been
   * scrolled past it — keeps the prompt always usable. */
  onFocus?: () => void
}

const AUTO_GENERATE = "__auto_generate__"

/** First-visit composer tour: the seen flag stores the tour's content hash
 * (version = a pure function of content, lib/tour.ts) — any step or copy
 * change replays the tour exactly once per user, zero manual versioning.
 * Read/write inside effects only — localStorage is never touched during SSR. */
const TOUR_SEEN_KEY = "repurposer-tour-seen"

/** Composer teaching (4 steps): assets → persona → prompt (send folded in)
 * → the recipe gallery as the alternative entry (lands last; Tour skips the
 * step if the cards haven't loaded yet). */
const COMPOSER_TOUR_STEPS: TourStepDef[] = [
  {
    target: "[data-tour='composer-assets']",
    titleKey: "tour.composer.assetsTitle",
    descKey: "tour.composer.assetsDesc",
    side: "bottom",
  },
  {
    target: "[data-tour='composer-persona']",
    titleKey: "tour.composer.personaTitle",
    descKey: "tour.composer.personaDesc",
    side: "bottom",
  },
  {
    target: "[data-tour='composer-prompt']",
    titleKey: "tour.composer.promptTitle",
    descKey: "tour.composer.promptDesc",
    side: "bottom",
  },
  {
    target: "[data-tour='home-recipes']",
    titleKey: "tour.composer.recipesTitle",
    descKey: "tour.composer.recipesDesc",
    side: "top",
  },
]

const TOUR_VERSION = tourVersionOf(COMPOSER_TOUR_STEPS, tourCopy.composer)

// Morph endpoints (expanded ↔ docked one-line bar). The shell is the shadcn
// InputGroup (2026-08-21 adoption — the layout converged to the canonical
// AI-composer anatomy: chips block-start / control / actions block-end), so
// the density recipe lives ON the addons and the editor band, never on the
// container: 20px sides / 20px top / 12px chin (measured off the MiniMax
// composer reference). The docked bar is 56px tall — 16px pad + one 24px
// text-base line + 16px pad, so the single line self-centers by construction
// and the h-9 send rides with 10px air (MiniMax bar proportions: the button
// is ~2/3 of the bar height, never stuffed). The radius IS a morph property
// after all (2026-08-21 reversal): a scroll-linked 16px (rest — MiniMax's
// soft rectangle) → 40px (docked), where the CSS radius cap (≤ half the bar)
// turns it into the stadium. Still a pure function of dockP — never a clock
// transition. An inline style also sidesteps the stock
// has-data-[align=*]:rounded-md pins (their :has() specificity outranks any
// plain rounded-* class).
const EDITOR_H = 96 // expanded band height
const BAR_EDITOR_H = 56 // bar band height (= the whole bar): 16 + 24 line + 16
const EDITOR_PAD_Y = 20 // pt-5
const BAR_EDITOR_PAD_Y = 16 // (56 − 24 line) / 2 — the bar line self-centers
const PAD_X = 20 // px-5 sides
const RADIUS_REST = 16 // rounded-2xl
const RADIUS_DOCK = 40 // ≥ half the 56px bar — the cap makes the stadium
const CHIPS_MAX_H = 160 // ~4 chip rows
const CHIPS_PAD_TOP = 20 // pt-5 — interpolated, never a class (see chipsStyle)
const CONTROL_ROW_H = 48 // h-9 content + pb-3 chin (the cap swallows the padding)
const CONTROL_PAD_BOTTOM = 12 // pb-3 chin — interpolated, never a class
const SEND_ANCHOR_X = 12 // right-3
const SEND_ANCHOR_Y = 12 // bottom-3 (on the control row's line)
const SEND_BAR_ANCHOR = 10 // (56 − 36) / 2 — centered in the bar
const BAR_SEND_RESERVE = 54 // 10 anchor + 36 send + 8 gap — bar input's right reserve
const ATTACH_PAD_X = 12 // bar: the attach glyph's center mirrors the send's
const ATTACH_MAX_W = 96
/** Rotating placeholder cadence (Lovart-style): the fixed prefix stays, the
 * example prompt behind it cycles every this-many ms. */
const PLACEHOLDER_ROTATE_MS = 3500

export function HomeComposer({
  personas,
  dockP = 0,
  onGenerateStart,
  prompt,
  onPromptChange,
  mentions,
  onMentionsChange,
  editorRef,
  onFocus,
}: HomeComposerProps) {
  const { t } = useTranslation()
  const { launching: isGenerating, launch } = useProjectLaunch()

  const [personaId, setPersonaId] = useState(AUTO_GENERATE)
  const [files, setFiles] = useState<File[]>([])
  const [assetsOpen, setAssetsOpen] = useState(false)
  const [personaOpen, setPersonaOpen] = useState(false)
  const [modelsOpen, setModelsOpen] = useState(false)
  const [tourOpen, setTourOpen] = useState(false)

  // First-visit teaching: open the composer tour once per tour version. Read
  // in an effect only — localStorage is never touched during SSR.
  useEffect(() => {
    try {
      if (window.localStorage.getItem(TOUR_SEEN_KEY) !== TOUR_VERSION)
        setTourOpen(true)
    } catch {
      // storage unavailable (private mode) — tour simply never auto-opens
    }
  }, [])

  // Manual replay (account console → 帮助): two delivery paths — a
  // sessionStorage flag consumed on mount (covers the not-on-home case: the
  // console navigates here, this effect fires), and an event for when the
  // composer is already mounted. First consumer wins; both clear the flag.
  useEffect(() => {
    const consume = () => {
      try {
        if (window.sessionStorage.getItem("repurposer-replay-tour") !== "1") return
        window.sessionStorage.removeItem("repurposer-replay-tour")
      } catch {
        return
      }
      setTourOpen(true)
    }
    consume()
    window.addEventListener("repurposer:replay-tour", consume)
    return () => window.removeEventListener("repurposer:replay-tour", consume)
  }, [])

  const markTourSeen = () => {
    try {
      window.localStorage.setItem(TOUR_SEEN_KEY, TOUR_VERSION)
    } catch {
      // ignore — worst case the tour shows again next visit
    }
  }

  const addFiles = (picked: File[]) => {
    if (picked.length === 0) return
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => `${f.name}:${f.size}`))
      const additions = picked.filter((f) => !existing.has(`${f.name}:${f.size}`))
      return [...prev, ...additions]
    })
  }

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  // The asset mention's candidate feed (memoized — the picker reloads when
  // the identity changes, so it must track `files`, not renders).
  const mentionContext = useMemo(
    () => ({ files: files.map((f) => ({ name: f.name, kind: fileKindOf(f.type) })) }),
    [files],
  )

  // Mention chip laws (MENTIONS §4): visible (inline chip in the sentence,
  // MentionEditor), consumed on send (onSent clears the draft, before
  // navigating), × purifies (removing the chip removes every trace — no
  // residual pin).
  //
  // The send mechanism is the shared `useProjectLaunch` (2026-08-08, D6 二次
  // 修订): composer and the recipe overlay's launch zone ride the identical
  // path (create project → upload → navigate → first /chat message). A
  // recipe launch is just its prompt template (配方 = 提示词, 2026-08-11) —
  // the composer never builds a prior (MENTIONS §3).
  const handleGenerate = () =>
    launch({
      prompt,
      mentions,
      files,
      personaId: personaId === AUTO_GENERATE ? undefined : personaId || undefined,
      onStart: onGenerateStart,
      onSent: () => editorRef.current?.clear(),
    })

  // Rotating placeholder (Lovart-style, 2026-08-30): a fixed prefix
  // ("Ask Repurposer to …") with the three most-common prompts cycling
  // behind it — teaching by example, inside the placeholder (the tour stays
  // the how-to surface). Rendered as an overlay (React-rendered, so it can
  // animate — the CSS attr() placeholder can't); visible ONLY while the
  // editor is empty. The cycle runs on an interval gated on emptiness; SSR
  // and the first paint show example 0. The transition is a ROLLING WINDOW
  // (2026-08-31 user ruling — the first pass was a blink-swap): the outgoing
  // prompt rolls up and out while the incoming rolls in from below, same
  // direction, so the motion reads as one continuous scroll; `prev` keeps
  // the outgoing line mounted for the animation.
  const placeholderPrompts = t("home.placeholderPrompts", {
    returnObjects: true,
  }) as string[]
  const promptEmpty = prompt.trim() === "" && mentions.length === 0
  const [placeholderRoll, setPlaceholderRoll] = useState<{
    idx: number
    prev: number | null
  }>({ idx: 0, prev: null })
  useEffect(() => {
    if (!promptEmpty || placeholderPrompts.length < 2) return
    const id = window.setInterval(
      () =>
        setPlaceholderRoll(({ idx }) => ({
          idx: (idx + 1) % placeholderPrompts.length,
          prev: idx,
        })),
      PLACEHOLDER_ROTATE_MS,
    )
    return () => window.clearInterval(id)
  }, [promptEmpty, placeholderPrompts.length])

  // Composer teaching tour: built per render from the static config so a
  // language switch re-labels the steps (Tour reads via ref).
  const tourSteps: TourStep[] = COMPOSER_TOUR_STEPS.map((step) => ({
    target: step.target,
    side: step.side,
    align: step.align,
    title: t(step.titleKey),
    description: t(step.descKey),
  }))

  // Scroll-linked morph interpolations (dockP is a pure function of
  // scrollTop; SSR renders dockP=0 = the expanded card).
  const docked = dockP >= 1
  const rest = dockP <= 0
  // Click-to-focus (the input-group addon contract): clicks on a band's
  // padding focus the editor; clicks on real buttons pass through.
  const focusEditor = (e: React.MouseEvent<HTMLElement>) => {
    if ((e.target as HTMLElement).closest("button")) return
    editorRef.current?.focus()
  }
  // One-place law: the Assets panel IS the chips band's expanded form —
  // while it's open the band folds away, so the file list lives in exactly
  // one place. The fold interpolates maxHeight AND the one-sided padding in
  // the same style object: a flex item's padding SURVIVES max-height:0
  // (border-box does not clip it — the old "clips its padding for free"
  // belief leaked pt-5/pb-3 into the docked bar, 2026-08-21 headless probe),
  // so static padding classes on a fold addon are banned; the padding must
  // ride the interpolation.
  const chipsOpen = files.length > 0 && !assetsOpen
  const chipsStyle: CSSProperties = {
    maxHeight: chipsOpen ? (1 - dockP) * CHIPS_MAX_H : 0,
    paddingTop: chipsOpen ? (1 - dockP) * CHIPS_PAD_TOP : 0,
    opacity: assetsOpen ? 0 : 1 - dockP,
    visibility: docked || assetsOpen ? "hidden" : undefined,
  }
  const attachStyle: CSSProperties = {
    maxWidth: dockP * ATTACH_MAX_W,
    paddingLeft: dockP * ATTACH_PAD_X,
    opacity: dockP,
    visibility: rest ? "hidden" : undefined,
  }
  const editorRowStyle: CSSProperties = { paddingRight: dockP * BAR_SEND_RESERVE }
  // The band owns the editor's padding (not the MentionEditor itself) so the
  // vertical air can morph: py 20→16 leaves exactly one line in the bar.
  const editorBandStyle: CSSProperties = {
    height: EDITOR_H + dockP * (BAR_EDITOR_H - EDITOR_H),
    padding: `${EDITOR_PAD_Y + dockP * (BAR_EDITOR_PAD_Y - EDITOR_PAD_Y)}px ${PAD_X}px`,
  }
  const controlRowStyle: CSSProperties = {
    maxHeight: (1 - dockP) * CONTROL_ROW_H,
    paddingBottom: (1 - dockP) * CONTROL_PAD_BOTTOM,
    marginTop: (1 - dockP) * 8,
    opacity: 1 - dockP,
    visibility: docked ? "hidden" : undefined,
    pointerEvents: dockP > 0.5 ? "none" : undefined,
  }
  // The shell radius rides dockP (inline style — beats the stock
  // has-data-[align=*]:rounded-md pins' :has() specificity for free).
  const shellStyle: CSSProperties = {
    borderRadius: RADIUS_REST + dockP * (RADIUS_DOCK - RADIUS_REST),
  }
  const sendStyle: CSSProperties = {
    right: SEND_ANCHOR_X + dockP * (SEND_BAR_ANCHOR - SEND_ANCHOR_X),
    bottom: SEND_ANCHOR_Y + dockP * (SEND_BAR_ANCHOR - SEND_ANCHOR_Y),
  }

  return (
    <>
    {/* Two forms, ONE DOM (the MentionEditor never unmounts — the DOM owns
        the draft). The shell is the shadcn InputGroup, re-skinned to the
        card law (2026-08-21 adoption): the stock `border-input` stroke and
        `bg-input/20` fill give way to the base hairline + bg-card + NO
        shadow; the focus-within ring machinery, cursor-text addons, and the
        block-start/block-end anatomy are what we came for. expanded = chips
        addon / editor band / control-row addon at a 16px radius (MiniMax's
        soft rectangle); docked = the one-line explore bar — the stadium
        emerges via the CSS radius cap as the inline-style radius rides dockP
        to 40px against the 56px bar (the user-ruled rounded-full exception).
        The morph between them is SCROLL-LINKED (dockP), never a clock
        transition. NO backdrop-filter (it would make the card the containing
        block for the portaled MentionPicker). */}
    <InputGroup
      className="border-0 bg-card shadow-none ring-1 ring-foreground/10 dark:bg-card"
      style={shellStyle}
    >
        {/* Block-start — staged asset chips. Always rendered (keeps the
            container h-auto), folds to zero when empty / docked / the Assets
            panel is open (the icon buttons are stateless — in the docked bar
            the files simply ride no display, per the 2026-08-30 ruling). */}
        <InputGroupAddon
          align="block-start"
          className="min-h-0 overflow-hidden px-5 py-0 font-normal"
          style={chipsStyle}
          onClick={focusEditor}
        >
          <AssetChips files={files} onRemove={removeFile} />
        </InputGroupAddon>

        {/* The input row: the bar's attach button (zero width when expanded)
            + the editor band. A plain row, not an addon — the inline-start
            addon only fits single-line shells. */}
        <div className="flex w-full items-center" style={editorRowStyle}>
          <div className="flex-none overflow-hidden" style={attachStyle}>
            {/* MiniMax-standard one-line layout: attach on the left. Opens
                DOWNWARD here (side="bottom") — docked at the viewport's top,
                a side="top" panel would leave the screen. Pure circle icon +
                function tooltip, stateless (2026-08-30 icon-button ruling):
                the staged files themselves live in the panel. */}
            <Popover>
              <Tooltip>
                <TooltipTrigger
                  render={
                    <PopoverTrigger
                      render={
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("composer.assets")}
                          className="h-8 w-8 rounded-full text-muted-foreground hover:text-foreground"
                          tabIndex={dockP > 0.5 ? 0 : -1}
                        >
                          <Paperclip className="size-4.5" />
                        </Button>
                      }
                    />
                  }
                />
                <TooltipContent side="bottom">{t("composer.assets")}</TooltipContent>
              </Tooltip>
              <PopoverContent side="bottom" align="start" className="w-80">
                <AssetsPanel files={files} onAdd={addFiles} onRemove={removeFile} />
              </PopoverContent>
            </Popover>
          </div>
          <div
            className="relative flex min-w-0 flex-1 cursor-text flex-col"
            style={editorBandStyle}
            data-tour="composer-prompt"
            onClick={focusEditor}
            onFocus={onFocus}
          >
            {/* Rotating placeholder overlay — pointer-events-none so clicks
                land on the band's focus handler. Padding mirrors the band's
                (the morph interpolation), so the text sits exactly where the
                editor's first line is; overflow-hidden clips whatever the
                one-line docked bar can't show. The suffix is a rolling
                window: per cycle the outgoing line (absolute, so layout
                follows the incoming) rolls up-out while the incoming rolls
                in from below — styles.css `.placeholder-roll-*`. */}
            {promptEmpty && (
              <div
                aria-hidden
                className="pointer-events-none absolute inset-0 overflow-hidden text-base break-words whitespace-pre-wrap text-muted-foreground"
                style={{ padding: editorBandStyle.padding }}
              >
                <span>{t("home.placeholderPrefix")}</span>
                <span className="relative inline-block whitespace-nowrap">
                  {placeholderRoll.prev !== null && (
                    <span
                      key={`out-${placeholderRoll.prev}`}
                      className="placeholder-roll-out absolute left-0 top-0"
                    >
                      {placeholderPrompts[placeholderRoll.prev]}
                    </span>
                  )}
                  <span
                    key={`in-${placeholderRoll.idx}`}
                    className="placeholder-roll-in inline-block"
                  >
                    {placeholderPrompts[placeholderRoll.idx]}
                  </span>
                </span>
              </div>
            )}
            <MentionEditor
              ref={editorRef}
              disabled={isGenerating}
              mentionContext={mentionContext}
              className="p-0"
              onChange={(text, ms) => {
                onPromptChange(text)
                onMentionsChange(ms)
              }}
              onSubmit={handleGenerate}
            />
          </div>
        </div>

        {/* Block-end — the control row (folds away into the bar; send is NOT
            here — it's the absolute anchor below so it survives the fold).
            Lovart-style pure circle icon buttons (2026-08-30 ruling): icon +
            function tooltip, completely STATELESS — no count, no Auto/name
            value text; the selection is read inside each frosted panel (the
            staged files themselves also ride the chips band, unchanged).
            The pr-12 reserves the send anchor's space. The ghost circle
            buttons mirror Lovart's measured anatomy: 32px button (h-8 w-8)
            + 18px glyph (size-4.5) — one register below the 36px send
            anchor. The left group's -ml-[7px] pulls the first one 7px left
            so its GLYPH's left edge lands on the editor text's left edge
            (the 18px glyph centers inside the 32px button with a 7px
            offset — without the bleed the icons read indented under the
            text). */}
        <InputGroupAddon
          align="block-end"
          className="min-h-0 items-center gap-2 overflow-hidden px-5 py-0 pr-12 font-normal"
          style={controlRowStyle}
          onClick={focusEditor}
        >
          <div className="flex w-full items-center justify-between">
            <div className="-ml-[7px] flex items-center gap-1">
              <Popover open={assetsOpen} onOpenChange={setAssetsOpen}>
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <PopoverTrigger
                        render={
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={t("composer.assets")}
                            className="h-8 w-8 rounded-full text-muted-foreground hover:text-foreground"
                            data-tour="composer-assets"
                          >
                            <Paperclip className="size-4.5" />
                          </Button>
                        }
                      />
                    }
                  />
                  <TooltipContent side="top">{t("composer.assets")}</TooltipContent>
                </Tooltip>
                <PopoverContent side="bottom" align="start" className="w-80">
                  <AssetsPanel files={files} onAdd={addFiles} onRemove={removeFile} />
                </PopoverContent>
              </Popover>

              <Popover open={personaOpen} onOpenChange={setPersonaOpen}>
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <PopoverTrigger
                        render={
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={t("composer.persona")}
                            className="h-8 w-8 rounded-full text-muted-foreground hover:text-foreground"
                            data-tour="composer-persona"
                          >
                            <User className="size-4.5" />
                          </Button>
                        }
                      />
                    }
                  />
                  <TooltipContent side="top">{t("composer.persona")}</TooltipContent>
                </Tooltip>
                <PopoverContent side="bottom" align="start" className="w-88">
                  <PersonaPanel
                    personas={personas}
                    value={personaId}
                    autoValue={AUTO_GENERATE}
                    onSelect={(id) => {
                      setPersonaId(id)
                      setPersonaOpen(false)
                    }}
                  />
                </PopoverContent>
              </Popover>
            </div>

            {/* Models — the honest Auto panel (user-ruled 2026-08-30): the
                pipeline assigns models per modality and there is exactly one
                provider per modality, so this is a READ-ONLY display of the
                real assignments — no selectable rows, no fake SKU shelf.
                `mr-3` holds it off the absolutely-anchored send button
                (measured gap was 0px — the circles touched, 2026-08-31). */}
            <div className="mr-3">
            <Popover open={modelsOpen} onOpenChange={setModelsOpen}>
              <Tooltip>
                <TooltipTrigger
                  render={
                    <PopoverTrigger
                      render={
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("composer.models")}
                          className="h-8 w-8 rounded-full text-muted-foreground hover:text-foreground"
                        >
                          <Box className="size-4.5" />
                        </Button>
                      }
                    />
                  }
                />
                <TooltipContent side="top">{t("composer.models")}</TooltipContent>
              </Tooltip>
              <PopoverContent side="bottom" align="end" className="w-88">
                <ModelsPanel />
              </PopoverContent>
            </Popover>
            </div>
          </div>

        </InputGroupAddon>

        {/* Send — the absolute bottom-right anchor in BOTH forms (expanded:
            on the control row's line, its historical seat; docked: centered
            in the bar). Absolute so the control row's fold never takes it. */}
        <Button
          className="absolute h-9 w-9 rounded-full transition-colors"
          style={sendStyle}
          size="icon"
          data-tour="composer-send"
          disabled={isGenerating}
          onClick={handleGenerate}
        >
          {isGenerating ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          ) : (
            <ArrowUp className="size-5" />
          )}
        </Button>
    </InputGroup>

    <Tour
      steps={tourSteps}
      open={tourOpen}
      onOpenChange={setTourOpen}
      onComplete={markTourSeen}
      onSkip={markTourSeen}
    />
    </>
  )
}
