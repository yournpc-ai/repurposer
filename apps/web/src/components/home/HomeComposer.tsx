"use client"

import { useEffect, useMemo, useState, type RefObject } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Plus, Upload } from "lucide-react"

import { useProjectLaunch } from "@/lib/useProjectLaunch"
import { useStagingUploads } from "@/lib/stagingUploads"
import { acceptsStagedFile } from "@/lib/stagedFiles"
import { useFileDrop } from "@/lib/useFileDrop"
import { fileKindOf, type ChatMention } from "@/lib/mentions"
import type { SkillOption } from "@/lib/skills"
import { useSettingsDialog } from "@/components/settings/settings-dialog-context"
import { useAuth } from "@/lib/auth-context"
import {
  MentionEditor,
  type MentionEditorHandle,
} from "@/components/mentions/MentionEditor"

import { Card } from "@/components/ui/card-clean"
import { AssetChips } from "@/components/home/AssetChips"
import { ComposerPanelButton } from "@/components/composer/ComposerPanelButton"
import { ComposerSendButton } from "@/components/composer/ComposerSendButton"
import { AssetsPanel } from "@/components/composer/AssetsPanel"
import { Tour, type TourStep } from "@/components/ui/tour"
import {
  canOpenTour,
  shouldAutoOpenTour,
  tourCopy,
  tourVersionOf,
  type TourStepDef,
} from "@/lib/tour"


interface HomeComposerProps {
  onGenerateStart?: () => void
  /** The draft (prompt + mentions) is the editor's reported mirror — the DOM
   * owns the text (MentionEditor); Home keeps it only as the send payload. */
  prompt: string
  onPromptChange: (value: string) => void
  mentions: ChatMention[]
  onMentionsChange: (value: ChatMention[]) => void
  selectedSkill: SkillOption | null
  onSkillChange: (option: SkillOption | null) => void
  editorRef: RefObject<MentionEditorHandle | null>
}


/** First-visit composer tour: the seen flag stores the tour's content hash
 * (version = a pure function of content, lib/tour.ts) — any step or copy
 * change replays the tour exactly once per user, zero manual versioning.
 * Read/write inside effects only — localStorage is never touched during SSR. */
const TOUR_SEEN_KEY = "repurposer-tour-seen"

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
]

const TOUR_VERSION = tourVersionOf(COMPOSER_TOUR_STEPS, tourCopy.composer)

/** Rotating placeholder cadence (Lovart-style): one full example prompt
 * cycles every this-many ms — no prefix, the whole line rolls. */
const PLACEHOLDER_ROTATE_MS = 3500

export function HomeComposer({
  onGenerateStart,
  prompt,
  onPromptChange,
  mentions,
  onMentionsChange,
  selectedSkill,
  onSkillChange,
  editorRef,
}: HomeComposerProps) {
  const { t } = useTranslation()
  const { isAuthenticated, loginOpen } = useAuth()
  const { launching: isGenerating, launch } = useProjectLaunch()
  const { modalOpen } = useSettingsDialog()
  const tourAllowed = !modalOpen && canOpenTour(isAuthenticated, loginOpen)

  // Batch A (2026-09-18): picked files upload IMMEDIATELY into a pre-project
  // staging session (useStagingUploads) — Generate never waits on the wire;
  // the chips carry the upload lifecycle (spinner+% / retry / ×).
  const { staged, addFiles, removeStaged, retryStaged, clearStaged } = useStagingUploads()
  const [assetsOpen, setAssetsOpen] = useState(false)
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
      if (shouldAutoOpenTour(seenVersion, TOUR_VERSION, isAuthenticated, loginOpen)) setTourOpen(true)
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
  // Landing templates can leave an editable URL placeholder in the draft.
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
      skill: selectedSkill?.reference,
      skillOption: selectedSkill ?? undefined,
      staged,
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
  const promptEmpty = prompt.trim() === "" && mentions.length === 0 && !selectedSkill
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

  // Click-to-focus (the input-group addon contract): clicks on a band's
  // padding focus the editor; clicks on real buttons pass through. Native
  // clicks INSIDE the editable already place the caret — focusing again here
  // would run MentionEditor.focus() and force that caret to the end.
  const focusEditor = (e: React.MouseEvent<HTMLElement>) => {
    const target = e.target as HTMLElement
    if (target.closest("button") || target.closest("[contenteditable]")) return
    editorRef.current?.focus()
  }
  return (
    <>
      <Card
        role="group"
        className={dragging ? "relative w-full outline-2 outline-dashed outline-ring" : "relative w-full"}
        {...dropProps}
      >
        {/* Drop affordance — the floating pill (screenshot parity): centered
            over the card, pointer-events-none so the drop always lands on
            the shell. Frosted floating layer (overlay-surface family) with
            the subtle border; icon + plain-weight label per the pill law. */}
        {dragging && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
            <div className="overlay-surface flex items-center gap-2.5 rounded-2xl px-5 py-3 border border-subtle">
              <Upload className="size-4.5" />
              <span className="text-base">{t("composer.dropHint")}</span>
            </div>
          </div>
        )}
        {staged.length > 0 && !assetsOpen && (
          <AssetChips items={staged} onRemove={removeStaged} onRetry={retryStaged} />
        )}
        <div
          className="relative flex min-h-10 min-w-0 cursor-text flex-col"
          data-tour="composer-prompt"
          onClick={focusEditor}
        >
          {promptEmpty && (
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0 overflow-hidden text-sm text-meta-foreground"
            >
              <span className="relative block truncate">
                {placeholderRoll.prev !== null && (
                  <span
                    key={`out-${placeholderRoll.prev}`}
                    className="placeholder-roll-out absolute left-0 top-0"
                  >
                    {placeholderPrompts[placeholderRoll.prev]}
                  </span>
                )}
                <span key={`in-${placeholderRoll.idx}`} className="placeholder-roll-in inline-block">
                  {placeholderPrompts[placeholderRoll.idx]}
                </span>
              </span>
            </div>
          )}
          <MentionEditor
            ref={editorRef}
            disabled={isGenerating}
            mentionContext={mentionContext}
            selectedSkill={selectedSkill}
            onSkillChange={onSkillChange}
            className="max-h-36 p-0 text-sm"
            onChange={(text, ms) => {
              onPromptChange(text)
              onMentionsChange(ms)
            }}
            onSubmit={handleGenerate}
          />
        </div>
        <div className="flex items-center justify-between" onClick={focusEditor}>
          <ComposerPanelButton
            icon={Plus}
            label={t("composer.assets")}
            open={assetsOpen}
            onOpenChange={setAssetsOpen}
            popoverSide="bottom"
            align="start"
            data-tour="composer-assets"
          >
            <AssetsPanel items={staged} onAdd={addFiles} onRemove={removeStaged} onRetry={retryStaged} />
          </ComposerPanelButton>
          <ComposerSendButton
            data-tour="composer-send"
            disabled={isGenerating}
            generating={isGenerating}
            onClick={handleGenerate}
            label={t("chat.send")}
          />
        </div>
      </Card>

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
