"use client"

import { useEffect, useMemo, useState, type RefObject } from "react"
import { useTranslation } from "react-i18next"
import {
  ArrowUp,
  BrainCircuit,
  Paperclip,
  FileText,
  Mic2,
  User,
  Video,
  Image as ImageIcon,
} from "lucide-react"

import { useProjectLaunch } from "@/lib/useProjectLaunch"
import { fileKindOf, type ChatMention } from "@/lib/mentions"
import {
  MentionEditor,
  type MentionEditorHandle,
} from "@/components/mentions/MentionEditor"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  PersonaPickerModal,
  type PersonaPickerEntry,
} from "@/components/home/PersonaPickerModal"
import { AssetsModal } from "@/components/home/AssetsModal"
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

export function HomeComposer({
  personas,
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
  const [personaPickerOpen, setPersonaPickerOpen] = useState(false)
  const [assetsOpen, setAssetsOpen] = useState(false)
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

  const markTourSeen = () => {
    try {
      window.localStorage.setItem(TOUR_SEEN_KEY, TOUR_VERSION)
    } catch {
      // ignore — worst case the tour shows again next visit
    }
  }

  const fileIconFor = (file: File) => {
    if (file.type.startsWith("video/")) return Video
    if (file.type.startsWith("audio/")) return Mic2
    if (file.type.startsWith("image/")) return ImageIcon
    return FileText
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

  return (
    <>
    {/* Flat chrome, the same recipe as the sign-in modal (DialogContent):
        solid card + the base primitive's ring-foreground/10 hairline +
        shadow-xl (light only — dark shadows compile to transparent). NO
        backdrop-filter on this card: the home page behind is a uniform fill
        with nothing to blur. */}
    <Card className="overflow-visible rounded-2xl py-0 shadow-xl">
      <CardContent className="p-5 text-left">
        {/* Entity blocks (Assets = source materials, Persona = whose voice)
            ride the card's top edge via negative margin; the textarea fills
            the remaining width to their right. Both blocks open modals. */}
        <div className="flex items-start gap-3">
          <div className="-mt-9 flex flex-shrink-0 items-start gap-2">
            {/* Assets block — Opus anatomy: icon at the top, spacer, then
                title with the info line at the very bottom. Fill-first
                separation: the bg-subtle step (faintest ladder rung)
                distinguishes the block from the white card / page, so it
                takes NO ring (hairline is the fallback for same-fill
                boundaries only). The block STRADDLES the card's top edge,
                so its hover must stay SOLID — a translucent veil would
                reveal the page/card seam behind it. Light: one rung down to
                bg-muted; dark: a solid color-mix lift of the muted step. */}
            <button
              type="button"
              data-tour="composer-assets"
              onClick={() => setAssetsOpen(true)}
              className="relative flex h-24 w-20 flex-col rounded-lg bg-subtle p-2 text-left transition-colors hover:bg-muted dark:hover:bg-[color-mix(in_oklch,var(--muted),var(--foreground)_5%)]"
            >
              {files.length === 0 ? (
                <Paperclip className="h-4 w-4 text-muted-foreground" />
              ) : (
                (() => {
                  const Icon = fileIconFor(files[0])
                  return <Icon className="h-4 w-4 text-muted-foreground" />
                })()
              )}
              <span className="mt-auto">
                <span className="block text-xs">{t("composer.assets")}</span>
                <span className="block text-[10px] text-muted-foreground">
                  {files.length === 0
                    ? t("composer.optional")
                    : t("composer.assetsCount", { count: files.length })}
                </span>
              </span>
            </button>

            {/* Persona block — same anatomy: avatar/user-icon top, "Persona"
                title, current value at the very bottom. */}
            <button
              type="button"
              data-tour="composer-persona"
              onClick={() => setPersonaPickerOpen(true)}
              className="flex h-24 w-20 flex-col rounded-lg bg-subtle p-2 text-left transition-colors hover:bg-muted dark:hover:bg-[color-mix(in_oklch,var(--muted),var(--foreground)_5%)]"
            >
              {selectedPersona ? (
                <Avatar size="sm">
                  {selectedPersona.avatar_url ? (
                    <AvatarImage
                      src={selectedPersona.avatar_url}
                      alt={selectedPersona.name}
                    />
                  ) : null}
                  <AvatarFallback>{selectedPersona.name.slice(0, 1)}</AvatarFallback>
                </Avatar>
              ) : (
                <User className="h-4 w-4 text-muted-foreground" />
              )}
              <span className="mt-auto min-w-0">
                <span className="block text-xs">{t("composer.persona")}</span>
                <span className="block truncate text-[10px] text-muted-foreground">
                  {selectedPersona ? selectedPersona.name : t("composer.autoGenerate")}
                </span>
              </span>
            </button>
          </div>

          <div className="relative flex h-24 flex-1 flex-col" data-tour="composer-prompt">
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

        {/* One continuous bottom row: the persona block above is the single
            identity control (ADR-038 — the skin follows the persona); this
            row carries provider + send only — no separate action-bar strip. */}
        <div className="mt-2 flex items-center gap-2">
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
                    className="ml-auto h-9 gap-1.5 rounded-md px-2 text-xs font-normal"
                  >
                    <BrainCircuit className="h-3.5 w-3.5 text-muted-foreground" />
                    <span>{t("composer.aiModel")}</span>
                  </Button>
                }
              />
              <PopoverContent side="top" align="end" className="w-64 ring-0 shadow-xl">
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

            <Button
              className="h-9 w-9 rounded-full"
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
          </div>
      </CardContent>
    </Card>

    <PersonaPickerModal
      personas={personas}
      value={personaId}
      autoValue={AUTO_GENERATE}
      onSelect={setPersonaId}
      open={personaPickerOpen}
      onOpenChange={setPersonaPickerOpen}
    />
    <AssetsModal
      files={files}
      onAdd={addFiles}
      onRemove={removeFile}
      open={assetsOpen}
      onOpenChange={setAssetsOpen}
    />
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
