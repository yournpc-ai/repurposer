"use client"

import { useEffect, useMemo, useState, type CSSProperties, type RefObject } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Box, Plus, Upload, User } from "lucide-react"

import { useProjectLaunch } from "@/lib/useProjectLaunch"
import { useStagingUploads } from "@/lib/stagingUploads"
import { acceptsStagedFile } from "@/lib/stagedFiles"
import { useFileDrop } from "@/lib/useFileDrop"
import { fileKindOf, type ChatMention } from "@/lib/mentions"
import { useAuth } from "@/lib/auth-context"
import {
  MentionEditor,
  type MentionEditorHandle,
} from "@/components/mentions/MentionEditor"

import { InputGroup, InputGroupAddon } from "@/components/ui/input-group"
import { AssetChips } from "@/components/home/AssetChips"
import { ComposerPanelButton } from "@/components/composer/ComposerPanelButton"
import { ComposerSendButton } from "@/components/composer/ComposerSendButton"
import { AssetsPanel } from "@/components/composer/AssetsPanel"
import { ModelsPanel } from "@/components/composer/ModelsPanel"
import {
  PersonaPanel,
  type PersonaPickerEntry,
} from "@/components/composer/PersonaPanel"
import { Tour, type TourStep } from "@/components/ui/tour"
import {
  canOpenTour,
  shouldAutoOpenTour,
  tourCopy,
  tourVersionOf,
  type TourStepDef,
} from "@/lib/tour"

type Persona = PersonaPickerEntry

interface HomeComposerProps {
  personas: Persona[]
  /** Scroll-LINKED morph (ADR-046 walkthrough pass 3): 0 = expanded hero
   * card, 1 = the docked one-line explore bar (stadium / half-radius). Every
   * morph property is an interpolation of this scroll progress — NEVER a
   * clock transition: the form always matches the scroll position exactly
   * (fast scroll = fast morph, zero lag, zero threshold flap). */
  dockP?: number
  /** The docked bar's viewport seat: at the BOTTOM (2026-10 bottom-dock
   * ruling — the composer flips to `fixed` once its flow slot scrolls out).
   * The bar's panels/tooltips open UPWARD from there (a side="bottom" panel
   * would leave the screen); the expanded card's panels always open down. */
  dockedAtBottom?: boolean
  onGenerateStart?: () => void
  /** The draft (prompt + mentions) is the editor's reported mirror — the DOM
   * owns the text (MentionEditor); Home keeps it only as the send payload. */
  prompt: string
  onPromptChange: (value: string) => void
  mentions: ChatMention[]
  onMentionsChange: (value: ChatMention[]) => void
  editorRef: RefObject<MentionEditorHandle | null>
}

const AUTO_GENERATE = "__auto_generate__"

/** First-visit composer tour: the seen flag stores the tour's content hash
 * (version = a pure function of content, lib/tour.ts) — any step or copy
 * change replays the tour exactly once per user, zero manual versioning.
 * Read/write inside effects only — localStorage is never touched during SSR. */
const TOUR_SEEN_KEY = "repurposer-tour-seen"

/** Persona entry hidden 2026-09-23 (user ruling): returns with the
 * positioning / memory ops-layer iteration (docs/POSITIONING.md). The
 * state machinery (personaId / launch payload) stays — only the button
 * and its tour step go away; the sidebar nav entry is hidden too. */
const SHOW_PERSONA = false

/** Composer teaching tour (3 steps while the persona entry is hidden):
 * assets → prompt (send folded in) → the recipe gallery's Use-prompt entry
 * (lands last; Tour skips the step if the cards haven't loaded yet). */
const COMPOSER_TOUR_STEPS: TourStepDef[] = [
  {
    target: "[data-tour='composer-assets']",
    titleKey: "tour.composer.assetsTitle",
    descKey: "tour.composer.assetsDesc",
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
// composer reference); the docked bar narrows the sides to 8px — the attach
// button and the send reserve already hold the bar's horizontal air. The
// docked bar is 56px tall — 16px pad + one 24px
// text-base line + 16px pad, so the single line self-centers by construction
// and the h-9 send rides with 10px air (MiniMax bar proportions: the button
// is ~2/3 of the bar height, never stuffed). The radius IS a morph property
// after all (2026-08-21 reversal): a scroll-linked 16px (rest — MiniMax's
// soft rectangle) → 40px (docked), where the CSS radius cap (≤ half the bar)
// turns it into the stadium. Still a pure function of dockP — never a clock
// transition. An inline style also sidesteps the stock
// has-data-[align=*]:rounded-md pins (their :has() specificity outranks any
// plain rounded-* class).
const EDITOR_H = 80 // rest band FLOOR (the empty/one-line MiniMax card look)
const EDITOR_MAX_H = 136 // growth cap: 2×20 pad + 4×24 lines — beyond it the
// editor's own overflow-y-auto scrolls (the band never exceeds four lines)
const BAR_EDITOR_H = 56 // bar band height (= the whole bar): 16 + 24 line + 16
const EDITOR_PAD_Y = 20 // pt-5
const BAR_EDITOR_PAD_Y = 16 // (56 − 24 line) / 2 — the bar line self-centers
const PAD_X = 20 // px-5 sides (expanded card)
const BAR_PAD_X = 8 // bar: the attach button + the row's send reserve already
// hold the horizontal air — the band's own 20px sides would be dead width
// (on a phone that's 40px of the text lane, the difference between the
// placeholder fitting and clipping).
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
const ATTACH_PAD_X = 10 // bar: the attach glyph's center mirrors the send's (28px)
const ATTACH_MAX_W = 96
/** Rotating placeholder cadence (Lovart-style): one full example prompt
 * cycles every this-many ms — no prefix, the whole line rolls. */
const PLACEHOLDER_ROTATE_MS = 3500

export function HomeComposer({
  personas,
  dockP = 0,
  dockedAtBottom = false,
  onGenerateStart,
  prompt,
  onPromptChange,
  mentions,
  onMentionsChange,
  editorRef,
}: HomeComposerProps) {
  const { t } = useTranslation()
  const { isAuthenticated, loginOpen } = useAuth()
  const { launching: isGenerating, launch } = useProjectLaunch()
  const tourAllowed = canOpenTour(isAuthenticated, loginOpen)

  const [personaId, setPersonaId] = useState(AUTO_GENERATE)
  // Batch A (2026-09-18): picked files upload IMMEDIATELY into a pre-project
  // staging session (useStagingUploads) — Generate never waits on the wire;
  // the chips carry the upload lifecycle (spinner+% / retry / ×).
  const { staged, addFiles, removeStaged, retryStaged, clearStaged } =
    useStagingUploads()
  const [assetsOpen, setAssetsOpen] = useState(false)
  const [personaOpen, setPersonaOpen] = useState(false)
  const [modelsOpen, setModelsOpen] = useState(false)
  const [tourOpen, setTourOpen] = useState(false)

  // Drag-drop upload (2026-09-24, user ruling — MiniMax/Lovart parity): the
  // shell IS the drop target in BOTH forms (expanded card / docked bar);
  // dropping is just a second entry into addFiles — the chips lifecycle
  // (spinner+% → done/error) rides unchanged. The gesture machinery
  // (depth-counted enter/leave, files-only arming, the browser-default
  // guard) is the shared useFileDrop — the dock rides the same hook.
  const { dragging, dropProps } = useFileDrop((files) => {
    const accepted = files.filter(acceptsStagedFile)
    if (accepted.length === 0) {
      if (files.length > 0) toast.error(t("composer.dropInvalid"))
      return
    }
    addFiles(accepted)
  }, isGenerating)

  // First-visit teaching: open the composer tour once per tour version, but
  // only behind the signed-in studio boundary. Read in an effect only —
  // localStorage is never touched during SSR.
  useEffect(() => {
    if (!tourAllowed) return
    try {
      const seenVersion = window.localStorage.getItem(TOUR_SEEN_KEY)
      if (
        shouldAutoOpenTour(seenVersion, TOUR_VERSION, isAuthenticated, loginOpen)
      )
        setTourOpen(true)
    } catch {
      // storage unavailable (private mode) — tour simply never auto-opens
    }
  }, [isAuthenticated, loginOpen, tourAllowed])

  // The tour never shares the screen with the login dialog: auth loss or a
  // reopened login flow closes it immediately (401 / logout mid-tour).
  useEffect(() => {
    if (!tourAllowed) setTourOpen(false)
  }, [tourAllowed])

  // Manual replay (account console → 帮助): two delivery paths — a
  // sessionStorage flag consumed on mount (covers the not-on-home case: the
  // console navigates here, this effect fires), and an event for when the
  // composer is already mounted. First consumer wins; both clear the flag.
  useEffect(() => {
    const consume = () => {
      if (!tourAllowed) return
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
  }, [tourAllowed])

  const markTourSeen = () => {
    try {
      window.localStorage.setItem(TOUR_SEEN_KEY, TOUR_VERSION)
    } catch {
      // ignore — worst case the tour shows again next visit
    }
  }

  // The asset mention's candidate feed (memoized — the picker reloads when
  // the identity changes, so it must track `staged`, not renders).
  const mentionContext = useMemo(
    () => ({
      files: staged.map((s) => ({ name: s.file.name, kind: fileKindOf(s.file.type) })),
    }),
    [staged],
  )

  // Mention chip laws (MENTIONS §4): visible (inline chip in the sentence,
  // MentionEditor), consumed on send (onSent clears the draft, before
  // navigating), × purifies (removing the chip removes every trace — no
  // residual pin).
  //
  // The send mechanism is the shared `useProjectLaunch`: picked files are
  // already uploaded (staging), so send = create project → attach → navigate
  // → first /chat message. A recipe launch is just its prompt template
  // (配方 = 提示词, 2026-08-11) — the composer never builds a prior
  // (MENTIONS §3).
  // The recipe prefill's visible blank is a launch gate in the same family
  // as the empty-prompt toast: the prompt stays the entire payload (no hidden
  // URL field), but an unresolved placeholder must never burn a chat turn.
  const urlPlaceholder = t("recipes.shelf.urlPlaceholder")
  const handleGenerate = () => {
    if (urlPlaceholder && prompt.includes(urlPlaceholder)) {
      toast.error(t("recipes.shelf.urlRequired"))
      editorRef.current?.selectText(urlPlaceholder)
      return
    }
    launch({
      prompt,
      mentions,
      staged,
      personaId: personaId === AUTO_GENERATE ? undefined : personaId || undefined,
      onStart: onGenerateStart,
      onSent: () => {
        editorRef.current?.clear()
        clearStaged()
      },
    })
  }

  // Rotating placeholder (Lovart-style): three first-person example prompts
  // cycling with NO prefix — each line is a complete request in the user's
  // own voice, i.e. an ANSWER to the hero question above ("What should we
  // make today?"): teaching by example, inside the placeholder (the tour
  // stays the how-to surface). Rendered as an overlay (React-rendered, so
  // it can animate — the CSS attr() placeholder can't); visible ONLY while
  // the editor is empty. The cycle runs on an interval gated on emptiness;
  // SSR and the first paint show example 0. The transition is a ROLLING
  // WINDOW (2026-08-31 user ruling — the first pass was a blink-swap): the
  // outgoing prompt rolls up and out while the incoming rolls in from
  // below, same direction, so the motion reads as one continuous scroll;
  // `prev` keeps the outgoing line mounted for the animation.
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
  // padding focus the editor; clicks on real buttons pass through. Native
  // clicks INSIDE the editable already place the caret — focusing again here
  // would run MentionEditor.focus() and force that caret to the end.
  const focusEditor = (e: React.MouseEvent<HTMLElement>) => {
    const target = e.target as HTMLElement
    if (target.closest("button") || target.closest("[contenteditable]")) return
    editorRef.current?.focus()
  }
  // Content-driven band target: re-measured after every content change
  // (typing / paste / recipe prefill / clear — all funnel through onChange
  // → the prompt prop) and on viewport rewraps. The rAF defers the read
  // past the DOM mutation. SSR and first paint = EDITOR_H.
  const [contentH, setContentH] = useState(EDITOR_H)
  useEffect(() => {
    const remeasure = () => {
      const h = editorRef.current?.getContentHeight()
      if (!h) return
      setContentH(
        Math.min(Math.max(h + 2 * EDITOR_PAD_Y, EDITOR_H), EDITOR_MAX_H),
      )
    }
    const id = requestAnimationFrame(remeasure)
    window.addEventListener("resize", remeasure)
    return () => {
      cancelAnimationFrame(id)
      window.removeEventListener("resize", remeasure)
    }
  }, [prompt, mentions, editorRef])
  // One-place law: the Assets panel IS the chips band's expanded form —
  // while it's open the band folds away, so the file list lives in exactly
  // one place. The fold interpolates maxHeight AND the one-sided padding in
  // the same style object: a flex item's padding SURVIVES max-height:0
  // (border-box does not clip it — the old "clips its padding for free"
  // belief leaked pt-5/pb-3 into the docked bar, 2026-08-21 headless probe),
  // so static padding classes on a fold addon are banned; the padding must
  // ride the interpolation.
  const chipsOpen = staged.length > 0 && !assetsOpen
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
  // air can morph: py 20→16 leaves exactly one line in the bar; px 20→8 —
  // in the docked bar the attach button (left) and the row's send reserve
  // (right) already hold the horizontal air.
  // The band's height is CONTENT-DRIVEN at rest (2026-10-15 mobile ruling):
  // a fixed 80px band left 40px for text = 1.67 lines, so every two-line
  // prompt on a phone clipped its second line ("下面被遮挡"). The band hugs
  // the draft between EDITOR_H (floor) and EDITOR_MAX_H (cap, then the
  // editor scrolls); the measured target only changes on content edits /
  // rewraps, so the morph stays a pure function of scrollTop — it
  // interpolates WHATEVER the current target is down to the 56px bar.
  const editorBandStyle: CSSProperties = {
    height: contentH + dockP * (BAR_EDITOR_H - contentH),
    padding: `${EDITOR_PAD_Y + dockP * (BAR_EDITOR_PAD_Y - EDITOR_PAD_Y)}px ${PAD_X + dockP * (BAR_PAD_X - PAD_X)}px`,
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
      className={`border-0 bg-card shadow-none dark:bg-card ${
        dragging
          ? "border-2 border-dashed border-foreground/30 ring-0"
          : "ring-1 ring-foreground/10"
      }`}
      style={shellStyle}
      {...dropProps}
    >
        {/* Drop affordance — the floating pill (screenshot parity): centered
            over the card, pointer-events-none so the drop always lands on
            the shell. Frosted floating layer (overlay-surface family) with
            the /10 hairline; icon + plain-weight label per the pill law. */}
        {dragging && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
            <div className="overlay-surface flex items-center gap-2.5 rounded-2xl px-5 py-3 ring-1 ring-foreground/10">
              <Upload className="size-4.5" />
              <span className="text-base">{t("composer.dropHint")}</span>
            </div>
          </div>
        )}
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
          <AssetChips items={staged} onRemove={removeStaged} onRetry={retryStaged} />
        </InputGroupAddon>

        {/* The input row: the bar's attach button (zero width when expanded)
            + the editor band. A plain row, not an addon — the inline-start
            addon only fits single-line shells. */}
        <div className="flex w-full items-center" style={editorRowStyle}>
          <div className="flex-none overflow-hidden" style={attachStyle}>
            {/* MiniMax-standard one-line layout: attach on the left. Panel
                direction follows the dock seat: the bar rides the viewport's
                BOTTOM (2026-10 bottom-dock ruling), so its panel opens
                UPWARD (side="top") — a downward panel would leave the
                screen. Pure circle icon + function tooltip, stateless
                (2026-08-30 icon-button ruling): the staged files themselves
                live in the panel. */}
            <ComposerPanelButton
              icon={Plus}
              label={t("composer.assets")}
              tooltipSide={dockedAtBottom ? "top" : "bottom"}
              popoverSide={dockedAtBottom ? "top" : "bottom"}
              align="start"
              tabIndex={dockP > 0.5 ? 0 : -1}
            >
              <AssetsPanel
                items={staged}
                onAdd={addFiles}
                onRemove={removeStaged}
                onRetry={retryStaged}
              />
            </ComposerPanelButton>
          </div>
          <div
            className="relative flex min-w-0 flex-1 cursor-text flex-col"
            style={editorBandStyle}
            data-tour="composer-prompt"
            onClick={focusEditor}
          >
            {/* Rotating placeholder overlay — pointer-events-none so clicks
                land on the band's focus handler. Padding mirrors the band's
                (the morph interpolation), so the text sits exactly where the
                editor's first line is. whitespace-nowrap + overflow-hidden =
                native-placeholder parity: a placeholder NEVER wraps — on
                narrow viewports the line clips at the edge instead of the
                nowrap line dropping to a second row and spilling out of the
                56px docked bar. The line is a rolling window: per cycle the
                outgoing line (absolute, so layout follows the incoming) rolls up-out while the incoming rolls in from below
                — styles.css `.placeholder-roll-*`. Color = the whisper tier
                (2026-09-23 user ruling, chat-dock parity: the MentionEditor's
                CSS placeholder reads --meta-foreground, this overlay was one
                tier brighter). */}
            {promptEmpty && (
              <div
                aria-hidden
                className="pointer-events-none absolute inset-0 overflow-hidden whitespace-nowrap text-base text-meta-foreground"
                style={{ padding: editorBandStyle.padding }}
              >
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
            The pr-12 reserves the send anchor's space. ONE HEIGHT for the
            whole row (2026-09-23 ruling, retiring the 2026-08-31 "32px
            buttons one register below the 36px send" size gap): circle
            buttons, the cost-confirm pill and the send all share h-9, so
            hover backgrounds align on the row's top/bottom edges by
            construction. The left group's -ml-[9px] pulls the first button
            9px left so its GLYPH's left edge lands on the editor text's
            left edge (the 18px glyph centers inside the 36px button with a
            9px offset — without the bleed the icons read indented under the
            text). */}
        <InputGroupAddon
          align="block-end"
          className="min-h-0 items-center gap-2 overflow-hidden px-5 py-0 pr-12 font-normal"
          style={controlRowStyle}
          onClick={focusEditor}
        >
          <div className="flex w-full items-center justify-between">
            <div className="-ml-[9px] flex items-center gap-1">
              <ComposerPanelButton
                icon={Plus}
                label={t("composer.assets")}
                open={assetsOpen}
                onOpenChange={setAssetsOpen}
                popoverSide="bottom"
                align="start"
                data-tour="composer-assets"
              >
                <AssetsPanel
                  items={staged}
                  onAdd={addFiles}
                  onRemove={removeStaged}
                  onRetry={retryStaged}
                />
              </ComposerPanelButton>

              {SHOW_PERSONA && (
                <ComposerPanelButton
                  icon={User}
                  label={t("composer.persona")}
                  open={personaOpen}
                  onOpenChange={setPersonaOpen}
                  popoverSide="bottom"
                  align="start"
                  data-tour="composer-persona"
                >
                  <PersonaPanel
                    personas={personas}
                    value={personaId}
                    autoValue={AUTO_GENERATE}
                    onSelect={(id) => {
                      setPersonaId(id)
                      setPersonaOpen(false)
                    }}
                  />
                </ComposerPanelButton>
              )}
            </div>

            {/* Right group — Models, the honest Auto panel
                (user-ruled 2026-08-30): the pipeline assigns models per
                modality and there is exactly one provider per modality, so
                this is a READ-ONLY display of the real assignments — no
                selectable rows, no fake SKU shelf. `mr-3` holds the group
                off the absolutely-anchored send button (measured gap was
                0px — the circles touched, 2026-08-31). */}
            <div className="mr-3 flex items-center gap-2">
              {/* Models (honest Auto panel) — PARKED: hidden until the panel
                  has something actionable to show; restore by ungating. */}
              {false && (
                <ComposerPanelButton
                  icon={Box}
                  label={t("composer.models")}
                  open={modelsOpen}
                  onOpenChange={setModelsOpen}
                  popoverSide="bottom"
                  align="end"
                  unpadded
                >
                  <ModelsPanel />
                </ComposerPanelButton>
              )}
            </div>
          </div>

        </InputGroupAddon>

        {/* Send — the absolute bottom-right anchor in BOTH forms (expanded:
            on the control row's line, its historical seat; docked: centered
            in the bar). Absolute so the control row's fold never takes it. */}
        <ComposerSendButton
          className="absolute"
          style={sendStyle}
          data-tour="composer-send"
          disabled={isGenerating}
          generating={isGenerating}
          onClick={handleGenerate}
          label={t("chat.send")}
        />
    </InputGroup>

    <Tour
      steps={tourSteps}
      open={tourOpen && tourAllowed}
      onOpenChange={setTourOpen}
      onComplete={markTourSeen}
      onSkip={markTourSeen}
    />
    </>
  )
}
