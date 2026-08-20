"use client"

import { useEffect, useMemo, useState, type CSSProperties, type RefObject } from "react"
import { useTranslation } from "react-i18next"
import { ArrowUp, BrainCircuit, Paperclip, User } from "lucide-react"

import { useProjectLaunch } from "@/lib/useProjectLaunch"
import { fileKindOf, type ChatMention } from "@/lib/mentions"
import {
  MentionEditor,
  type MentionEditorHandle,
} from "@/components/mentions/MentionEditor"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { AssetChips } from "@/components/home/AssetChips"
import { AssetsPanel } from "@/components/home/AssetsPanel"
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

// Morph endpoints (expanded ↔ docked one-line bar). The radius is NOT one of
// them (2026-08-21 ruling, MiniMax parity): the card carries a CONSTANT 40px
// radius — big and soft at rest — and the docked bar (BAR_PAD*2 +
// BAR_EDITOR_H = 56px tall) lets the CSS radius cap do the stadium: adjacent
// radii (40+40 > 56) are scaled to half the bar height automatically. Zero
// interpolation, zero threshold — "full only when collapsed" falls out of the
// box model.
const CARD_RADIUS = 40 // constant; the browser caps it to 28px at dock height
const CONTENT_PAD_X = 20 // px-5
const CONTENT_PAD_T = 20 // pt-5
const CONTENT_PAD_B = 12 // pb-3 — a tight bottom chin (MiniMax anatomy)
const BAR_PAD = 8 // p-2
const EDITOR_H = 96 // h-24
const BAR_EDITOR_H = 40 // h-10
const CHIPS_MAX_H = 160 // ~4 chip rows
const CONTROL_ROW_H = 44 // h-9 + mt-2
const SEND_ANCHOR_X = 20 // right-5 (matches content padding)
const SEND_ANCHOR_Y = 12 // bottom-3 (on the control row's line)
const SEND_BAR_ANCHOR = 10 // right/bottom-2.5
const ATTACH_MAX_W = 96

export function HomeComposer({
  personas,
  dockP = 0,
  onGenerateStart,
  prompt,
  onPromptChange,
  mentions,
  onMentionsChange,
  editorRef,
}: HomeComposerProps) {
  const { t } = useTranslation()
  const { launching: isGenerating, launch } = useProjectLaunch()

  const [personaId, setPersonaId] = useState(AUTO_GENERATE)
  const [files, setFiles] = useState<File[]>([])
  const [assetsOpen, setAssetsOpen] = useState(false)
  const [personaOpen, setPersonaOpen] = useState(false)
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

  const selectedPersona =
    personaId === AUTO_GENERATE
      ? undefined
      : personas.find((p) => p.id === personaId)

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
  const cardStyle: CSSProperties = {
    borderRadius: CARD_RADIUS,
  }
  // Asymmetric padding (MiniMax anatomy): generous top/sides, a tight bottom
  // chin — the control row sits close to the card's bottom edge. All three
  // axes converge on BAR_PAD at dock.
  const contentStyle: CSSProperties = {
    padding: `${CONTENT_PAD_T + dockP * (BAR_PAD - CONTENT_PAD_T)}px ${
      CONTENT_PAD_X + dockP * (BAR_PAD - CONTENT_PAD_X)
    }px ${CONTENT_PAD_B + dockP * (BAR_PAD - CONTENT_PAD_B)}px`,
  }
  // One-place law: the Assets panel IS the chips band's expanded form —
  // while it's open the band folds away, so the file list lives in exactly
  // one place (the pill's count stays as the anchor).
  const chipsStyle: CSSProperties = {
    maxHeight: files.length && !assetsOpen ? (1 - dockP) * CHIPS_MAX_H : 0,
    opacity: assetsOpen ? 0 : 1 - dockP,
    visibility: docked || assetsOpen ? "hidden" : undefined,
  }
  const attachStyle: CSSProperties = {
    maxWidth: dockP * ATTACH_MAX_W,
    opacity: dockP,
    visibility: rest ? "hidden" : undefined,
  }
  const editorRowStyle: CSSProperties = { paddingRight: dockP * 48 }
  const editorBandStyle: CSSProperties = {
    height: EDITOR_H + dockP * (BAR_EDITOR_H - EDITOR_H),
  }
  const controlRowStyle: CSSProperties = {
    maxHeight: (1 - dockP) * CONTROL_ROW_H,
    marginTop: (1 - dockP) * 8,
    opacity: 1 - dockP,
    visibility: docked ? "hidden" : undefined,
    pointerEvents: dockP > 0.5 ? "none" : undefined,
  }
  const sendStyle: CSSProperties = {
    right: SEND_ANCHOR_X + dockP * (SEND_BAR_ANCHOR - SEND_ANCHOR_X),
    bottom: SEND_ANCHOR_Y + dockP * (SEND_BAR_ANCHOR - SEND_ANCHOR_Y),
  }

  return (
    <>
    {/* Two forms, ONE DOM (the MentionEditor never unmounts — the DOM owns
        the draft): expanded = three bands (chips / input / control row) with
        a CONSTANT 40px radius and asymmetric padding (px-5 pt-5 pb-3 — the
        tight bottom chin, MiniMax anatomy); docked = the one-line explore
        bar — the stadium emerges for free: the CSS radius cap scales 40px to
        half the 56px bar height (the full-radius look at dock is the
        user-ruled rounded-full exception, 2026-08-21). The morph between
        them is SCROLL-LINKED (dockP), never a clock transition. Flat chrome:
        the base primitive's ring-foreground/10 hairline only, NO shadow; NO
        backdrop-filter (it would make the card the containing block for the
        portaled MentionPicker). */}
    <Card className="relative py-0" style={cardStyle}>
      <CardContent className="text-left" style={contentStyle}>
        {/* Band 1 — staged asset chips. Folds away into the bar; the attach
            button's count carries the awareness there. */}
        <div className="overflow-hidden" style={chipsStyle}>
          <AssetChips files={files} onRemove={removeFile} />
        </div>

        {/* Band 2 — the input row: the bar's attach button (zero width when
            expanded) + the editor. */}
        <div className="flex items-center" style={editorRowStyle}>
          <div className="flex-none overflow-hidden" style={attachStyle}>
            {/* MiniMax-standard one-line layout: attach on the left. Opens
                DOWNWARD here (side="bottom") — docked at the viewport's top,
                a side="top" panel would leave the screen. */}
            <Popover>
              <PopoverTrigger
                render={
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={t("composer.assets")}
                    className="h-9 gap-1 rounded-full px-2 text-xs font-normal"
                    tabIndex={dockP > 0.5 ? 0 : -1}
                  >
                    <Paperclip className="h-3.5 w-3.5 text-muted-foreground" />
                    {files.length > 0 ? (
                      <span className="text-foreground">{files.length}</span>
                    ) : null}
                  </Button>
                }
              />
              <PopoverContent side="bottom" align="start" className="w-80">
                <AssetsPanel files={files} onAdd={addFiles} onRemove={removeFile} />
              </PopoverContent>
            </Popover>
          </div>
          <div
            className="relative flex min-w-0 flex-1 flex-col"
            style={editorBandStyle}
            data-tour="composer-prompt"
          >
            <MentionEditor
              ref={editorRef}
              placeholder={t("home.pastePlaceholder")}
              disabled={isGenerating}
              mentionContext={mentionContext}
              onChange={(text, ms) => {
                onPromptChange(text)
                onMentionsChange(ms)
              }}
              onSubmit={handleGenerate}
            />
          </div>
        </div>

        {/* Band 3 — the control row (folds away into the bar; send is NOT
            here — it's the absolute anchor below so it survives the fold).
            Pill value state law: rest value in meta-foreground, set value in
            foreground — that single color step is the whole state change (no
            fills, no accent color). The pr-12 reserves the send anchor's
            space. */}
        <div className="flex items-center gap-2 overflow-hidden" style={controlRowStyle}>
          <div className="flex items-center gap-1">
            <Popover open={assetsOpen} onOpenChange={setAssetsOpen}>
              <PopoverTrigger
                render={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-9 gap-1.5 rounded-md px-2 text-xs font-normal"
                    data-tour="composer-assets"
                  >
                    <Paperclip className="h-3.5 w-3.5 text-muted-foreground" />
                    <span>{t("composer.assets")}</span>
                    <span className={files.length > 0 ? "text-foreground" : "text-meta-foreground"}>
                      ·{" "}
                      {files.length > 0
                        ? t("composer.assetsCount", { count: files.length })
                        : t("composer.optional")}
                    </span>
                  </Button>
                }
              />
              <PopoverContent side="bottom" align="start" className="w-80">
                <AssetsPanel files={files} onAdd={addFiles} onRemove={removeFile} />
              </PopoverContent>
            </Popover>

            <Popover open={personaOpen} onOpenChange={setPersonaOpen}>
              <PopoverTrigger
                render={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-9 gap-1.5 rounded-md px-2 text-xs font-normal"
                    data-tour="composer-persona"
                  >
                    {selectedPersona ? (
                      <Avatar className="h-4 w-4">
                        {selectedPersona.avatar_url ? (
                          <AvatarImage
                            src={selectedPersona.avatar_url}
                            alt={selectedPersona.name}
                          />
                        ) : null}
                        <AvatarFallback className="text-[8px]">
                          {selectedPersona.name.slice(0, 1)}
                        </AvatarFallback>
                      </Avatar>
                    ) : (
                      <User className="h-3.5 w-3.5 text-muted-foreground" />
                    )}
                    <span>{t("composer.persona")}</span>
                    <span
                      className={`max-w-28 truncate ${selectedPersona ? "text-foreground" : "text-meta-foreground"}`}
                    >
                      · {selectedPersona ? selectedPersona.name : t("composer.autoGenerate")}
                    </span>
                  </Button>
                }
              />
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

          <div className="ml-auto flex items-center gap-2 pr-12">
            {/* AI model — display-only (single provider): hover reveals the
                provider breakdown. A picker lands only when a real second
                provider exists (provider abstraction, PROGRESS 需求池). */}
            <Popover>
              <PopoverTrigger
                openOnHover
                delay={150}
                render={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-9 gap-1.5 rounded-md px-2 text-xs font-normal"
                  >
                    <BrainCircuit className="h-3.5 w-3.5 text-muted-foreground" />
                    <span>{t("composer.aiModel")}</span>
                  </Button>
                }
              />
              <PopoverContent side="bottom" align="end" className="w-64 ring-0">
                <div className="flex flex-col gap-1.5 px-0.5 pb-0.5">
                  {(
                    [
                      [t("composer.aiModelRowText"), "MiniMax M3"],
                      [t("composer.aiModelRowVoice"), "MiniMax T2A"],
                      [t("composer.aiModelRowVisual"), "MiniMax"],
                    ] as const
                  ).map(([label, value]) => (
                    <div key={label} className="flex items-center justify-between gap-3">
                      <span className="text-muted-foreground">{label}</span>
                      <span>{value}</span>
                    </div>
                  ))}
                </div>
              </PopoverContent>
            </Popover>
          </div>
        </div>

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
            <ArrowUp className="h-4 w-4" />
          )}
        </Button>
      </CardContent>
    </Card>

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
