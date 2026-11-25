"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { Check, ChevronDown, Loader2, Pause, Play } from "lucide-react"

import { VoiceOrb, type VoiceOrbState } from "@/components/ui/voice-orb"
import { cn } from "@/lib/utils"
import type {
  CandidateMemberPayload,
  CandidateSurface,
} from "../timeline/types"
import { shouldAnimateEntrance } from "../timeline/reveal"
import {
  useStructureVisibilityRegistration,
  type RegisterStructureVisibility,
} from "../structureVisibility"

const VISIBLE_COUNT = 3

let activeVoiceAudio: HTMLAudioElement | null = null

export function isVoiceCandidateMember(member: CandidateMemberPayload): boolean {
  return typeof member.voice_id === "string" && member.voice_id.trim().length > 0
}

export function isVoiceCandidateSurface(surface: CandidateSurface): boolean {
  return (
    surface.kind === "voice_set" &&
    surface.members.length > 0 &&
    surface.members.every(isVoiceCandidateMember)
  )
}

function voiceDisplayTitle(member: CandidateMemberPayload): string {
  return (member.title ?? member.excerpt ?? member.voice_id ?? "").trim()
}

function formatScopeLabel(
  scope: string | null | undefined,
  sourceKind: string | null | undefined,
  t: (key: string) => string,
): string | null {
  const normalized = (scope ?? sourceKind ?? "").toLowerCase().trim()
  if (!normalized) return null
  if (normalized === "personal" || normalized === "cloned" || normalized === "user") {
    return t("chat.candidates.scopePersonal")
  }
  if (normalized === "curated" || normalized === "system" || normalized === "preset") {
    return t("chat.candidates.scopeCurated")
  }
  return null
}

function formatLanguageCode(lang: string): string {
  const trimmed = lang.trim()
  if (!trimmed) return ""
  const base = trimmed.split(/[-_]/)[0] ?? trimmed
  return base.toUpperCase()
}

export interface VoiceCandidateSurfaceProps {
  surface: CandidateSurface
  hydrated?: boolean
  serverMessageId?: string
  turnId?: string
  onStructureVisible?: RegisterStructureVisibility
  onSelectCandidate?: (message: string, memberIndex: number, surface: CandidateSurface) => void
  selectionDisabled?: boolean
}

export function VoiceCandidateSurface({
  surface,
  hydrated,
  serverMessageId,
  turnId,
  onStructureVisible,
  onSelectCandidate,
  selectionDisabled = false,
}: VoiceCandidateSurfaceProps) {
  const { t } = useTranslation()
  const reduceMotion = useReducedMotion()
  const [expanded, setExpanded] = useState(false)
  const [activeIndex, setActiveIndex] = useState<number | null>(null)
  const [orbState, setOrbState] = useState<VoiceOrbState>("idle")
  const [orbLevel, setOrbLevel] = useState<number | undefined>(undefined)
  const [failedIndex, setFailedIndex] = useState<number | null>(null)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const sourceAttachedRef = useRef(false)
  const meterFrameRef = useRef<number>(0)
  const activeIndexRef = useRef<number | null>(null)
  activeIndexRef.current = activeIndex

  useStructureVisibilityRegistration({
    open: surface.members.length > 0,
    history: hydrated,
    serverMessageId,
    turnId,
    register: onStructureVisible,
  })

  const stopMeter = useCallback(() => {
    if (meterFrameRef.current) {
      cancelAnimationFrame(meterFrameRef.current)
      meterFrameRef.current = 0
    }
    setOrbLevel(undefined)
  }, [])

  const startMeter = useCallback(() => {
    stopMeter()
    const analyser = analyserRef.current
    if (!analyser) {
      setOrbLevel(undefined)
      return
    }
    const buffer = new Uint8Array(analyser.fftSize)
    let silentFrames = 0
    const tick = () => {
      analyser.getByteTimeDomainData(buffer)
      let sum = 0
      for (let i = 0; i < buffer.length; i += 1) {
        const centered = (buffer[i] - 128) / 128
        sum += centered * centered
      }
      const rms = Math.sqrt(sum / buffer.length)
      if (rms > 0.004) {
        silentFrames = 0
        setOrbLevel(Math.min(1, rms * 3.4))
      } else {
        silentFrames += 1
        // If CORS or a mock audio element produces an all-zero buffer, fall back
        // to VoiceOrb's natural built-in speech envelope rather than freezing flat.
        if (silentFrames > 14) {
          setOrbLevel(undefined)
        } else {
          setOrbLevel(0.14)
        }
      }
      meterFrameRef.current = requestAnimationFrame(tick)
    }
    meterFrameRef.current = requestAnimationFrame(tick)
  }, [stopMeter])

  const ensureAudioElement = useCallback((): HTMLAudioElement => {
    if (audioRef.current) return audioRef.current
    const audio = new Audio()
    audio.preload = "none"
    audio.crossOrigin = "anonymous"

    const onPlaying = () => {
      if (activeVoiceAudio && activeVoiceAudio !== audio) {
        activeVoiceAudio.pause()
      }
      activeVoiceAudio = audio
      setFailedIndex(null)
      setOrbState("speaking")
      startMeter()
    }
    const onPause = () => {
      if (activeVoiceAudio === audio) activeVoiceAudio = null
      stopMeter()
      setOrbState("idle")
    }
    const onEnded = () => {
      if (activeVoiceAudio === audio) activeVoiceAudio = null
      stopMeter()
      setOrbState("idle")
    }
    const onError = () => {
      if (activeVoiceAudio === audio) activeVoiceAudio = null
      stopMeter()
      setOrbState("idle")
      setFailedIndex(activeIndexRef.current)
    }

    audio.addEventListener("playing", onPlaying)
    audio.addEventListener("pause", onPause)
    audio.addEventListener("ended", onEnded)
    audio.addEventListener("error", onError)
    audioRef.current = audio
    return audio
  }, [startMeter, stopMeter])

  const connectAnalyser = useCallback((audio: HTMLAudioElement) => {
    if (sourceAttachedRef.current || typeof window === "undefined") return
    const AudioContextCtor =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext
    if (!AudioContextCtor) return
    try {
      const ctx = audioCtxRef.current ?? new AudioContextCtor()
      audioCtxRef.current = ctx
      const source = ctx.createMediaElementSource(audio)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.78
      source.connect(analyser)
      analyser.connect(ctx.destination)
      analyserRef.current = analyser
      sourceAttachedRef.current = true
    } catch {
      // jsdom or restricted audio environment — graceful fallback to simulated envelope
      analyserRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => {
      stopMeter()
      const audio = audioRef.current
      if (audio) {
        audio.pause()
        if (activeVoiceAudio === audio) activeVoiceAudio = null
        audio.src = ""
        audioRef.current = null
      }
      if (audioCtxRef.current && typeof audioCtxRef.current.close === "function") {
        void audioCtxRef.current.close().catch(() => {})
        audioCtxRef.current = null
      }
    }
  }, [stopMeter])

  const toggleAudition = useCallback(
    async (index: number) => {
      const member = surface.members[index]
      if (!member) return
      const previewUrl = (member.preview_url ?? "").trim()
      if (!previewUrl) {
        setFailedIndex(index)
        return
      }

      const audio = ensureAudioElement()
      const isSameVoice = activeIndexRef.current === index
      if (isSameVoice && orbState !== "idle") {
        audio.pause()
        return
      }

      setActiveIndex(index)
      setFailedIndex(null)
      setOrbState("thinking")

      connectAnalyser(audio)
      if (audioCtxRef.current?.state === "suspended") {
        await audioCtxRef.current.resume().catch(() => {})
      }

      try {
        if (audio.src !== previewUrl && !audio.src.endsWith(previewUrl)) {
          audio.src = previewUrl
        }
        audio.currentTime = 0
        await audio.play()
        // In environments like jsdom where play() resolves without firing the
        // native `playing` event, transition cleanly into speaking state.
        setOrbState((prev) => (prev === "thinking" ? "speaking" : prev))
      } catch {
        stopMeter()
        setOrbState("idle")
        setFailedIndex(index)
      }
    },
    [connectAnalyser, ensureAudioElement, orbState, stopMeter, surface.members],
  )

  const handleOrbPress = useCallback(() => {
    const target = activeIndex ?? surface.selected[0] ?? 0
    void toggleAudition(target)
  }, [activeIndex, surface.selected, toggleAudition])

  const handleSelect = useCallback(
    (index: number) => {
      if (!onSelectCandidate || selectionDisabled) return
      const member = surface.members[index]
      if (!member) return
      const ordinal = String(index + 1).padStart(2, "0")
      const title = voiceDisplayTitle(member)
      const prompt = t("chat.candidates.selectVoiceMessage", {
        ordinal,
        title,
      })
      onSelectCandidate(prompt, index, surface)
    },
    [onSelectCandidate, selectionDisabled, surface, t],
  )

  const overflow = surface.members.length - VISIBLE_COUNT
  const shown = expanded ? surface.members : surface.members.slice(0, VISIBLE_COUNT)
  const stageIndex = activeIndex ?? surface.selected[0] ?? null
  const stageMember = stageIndex != null ? surface.members[stageIndex] : null
  const stageOrdinal =
    stageIndex != null ? String(stageIndex + 1).padStart(2, "0") : null

  const orbCaption =
    orbState === "speaking" && stageOrdinal
      ? t("chat.candidates.voiceAuditioning", { ordinal: stageOrdinal })
      : orbState === "thinking"
        ? t("chat.candidates.voiceLoading")
        : t("chat.candidates.voiceSelectPrompt")

  return (
    <div className="ui-th-message">
      <motion.div
        data-slot="voice-candidate-surface"
        layout={!reduceMotion}
        initial={
          shouldAnimateEntrance(hydrated) && !reduceMotion
            ? { opacity: 0, y: 4 }
            : false
        }
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduceMotion ? 0 : 0.18 }}
        className="w-full max-w-2xl rounded-2xl border border-border bg-card/85 p-4 shadow-sm"
      >
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
              {t("chat.candidates.voiceTitle")}
            </span>
            {surface.topic ? (
              <>
                <span aria-hidden="true" className="text-muted-foreground/40">
                  ·
                </span>
                <span className="truncate text-xs text-muted-foreground">
                  {surface.topic}
                </span>
              </>
            ) : null}
          </div>
          <span className="shrink-0 rounded-full border border-border/70 bg-muted/50 px-2 py-0.5 text-[11px] tabular-nums text-muted-foreground">
            {t("chat.candidates.voiceCount", { count: surface.members.length })}
          </span>
        </div>

        <div className="flex flex-col gap-3.5 sm:flex-row sm:items-stretch">
          <div
            data-slot="voice-orb-stage"
            className="flex shrink-0 flex-col items-center justify-center rounded-xl border border-border/70 bg-muted/35 px-4 py-4 text-center sm:w-[172px]"
          >
            <VoiceOrb
              state={orbState}
              level={orbState === "speaking" ? orbLevel : undefined}
              size={108}
              dots={460}
              label={false}
              onPress={handleOrbPress}
            />
            <p className="mt-2 max-w-full truncate text-xs font-medium text-foreground">
              {stageMember
                ? voiceDisplayTitle(stageMember)
                : t("chat.candidates.voiceTitle")}
            </p>
            <p className="mt-0.5 max-w-full truncate text-[11px] text-muted-foreground">
              {orbCaption}
            </p>
          </div>

          <div
            className={cn(
              "flex min-w-0 flex-1 flex-col gap-2",
              expanded && "max-h-96 overflow-y-auto thin-scroll",
            )}
          >
            <AnimatePresence initial={false} mode="popLayout">
              {shown.map((member, index) => {
                const selected = surface.selected.includes(index)
                const isActive = activeIndex === index
                const isPlaying = isActive && orbState === "speaking"
                const isLoading = isActive && orbState === "thinking"
                const isFailed = failedIndex === index
                const ordinal = String(index + 1).padStart(2, "0")
                const title = voiceDisplayTitle(member)
                const scopeLabel = formatScopeLabel(
                  member.scope,
                  member.source_kind,
                  t,
                )
                const languages = (member.languages ?? [])
                  .map(formatLanguageCode)
                  .filter(Boolean)
                  .slice(0, 3)
                const toneTags = (member.tone_tags ?? []).filter(Boolean).slice(0, 3)
                const styleTags = (member.compatible_styles ?? [])
                  .filter(Boolean)
                  .slice(0, 2)
                const hasPreview = Boolean(member.preview_url?.trim())

                return (
                  <motion.div
                    layout={!reduceMotion}
                    key={`${member.voice_id ?? "voice"}-${index}`}
                    data-slot="voice-candidate-row"
                    data-selected={selected ? "true" : undefined}
                    data-playing={isPlaying ? "true" : undefined}
                    initial={
                      shouldAnimateEntrance(hydrated) && !reduceMotion
                        ? { opacity: 0, y: 4 }
                        : false
                    }
                    animate={{ opacity: 1, y: 0 }}
                    exit={reduceMotion ? { opacity: 1 } : { opacity: 0, y: -4 }}
                    transition={{ duration: reduceMotion ? 0 : 0.16 }}
                    className={cn(
                      "rounded-xl border px-3 py-2.5 transition-colors",
                      selected
                        ? "border-foreground/25 bg-accent"
                        : isPlaying
                          ? "border-foreground/20 bg-accent/65"
                          : "border-border/70 bg-background/60 hover:bg-accent/40",
                    )}
                  >
                    <div className="flex items-start gap-2.5">
                      <span
                        className={cn(
                          "mt-1 shrink-0 text-[11px] font-medium tabular-nums",
                          selected || isPlaying
                            ? "text-foreground"
                            : "text-muted-foreground",
                        )}
                      >
                        {ordinal}
                      </span>

                      <button
                        type="button"
                        onClick={() => {
                          void toggleAudition(index)
                        }}
                        disabled={!hasPreview}
                        aria-label={t(
                          isPlaying
                            ? "chat.candidates.pauseVoice"
                            : "chat.candidates.playVoice",
                          { title },
                        )}
                        aria-pressed={isPlaying}
                        className={cn(
                          "mt-0.5 grid size-7 shrink-0 place-items-center rounded-full border transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40",
                          isPlaying || isLoading
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border bg-card text-foreground hover:bg-accent",
                        )}
                      >
                        {isLoading ? (
                          <Loader2 className="size-3.5 animate-spin" />
                        ) : isPlaying ? (
                          <Pause className="size-3.5 fill-current" />
                        ) : (
                          <Play className="size-3.5 translate-x-[0.5px] fill-current" />
                        )}
                      </button>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <p className="truncate text-sm font-medium text-foreground">
                            {title}
                          </p>
                          {scopeLabel ? (
                            <span className="shrink-0 rounded-full border border-border/70 bg-muted/60 px-1.5 py-px text-[10px] text-muted-foreground">
                              {scopeLabel}
                            </span>
                          ) : null}
                        </div>
                        {member.description ? (
                          <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
                            {member.description}
                          </p>
                        ) : null}
                      </div>

                      <button
                        type="button"
                        onClick={() => handleSelect(index)}
                        disabled={!onSelectCandidate || selectionDisabled}
                        className={cn(
                          "inline-flex h-7 shrink-0 items-center gap-1 rounded-full border px-2.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-55",
                          selected
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border bg-card text-foreground hover:bg-accent",
                        )}
                      >
                        {selected ? <Check className="size-3" /> : null}
                        <span>
                          {selected
                            ? t("chat.candidates.selected")
                            : t("chat.candidates.useVoice")}
                        </span>
                      </button>
                    </div>

                    {(languages.length > 0 ||
                      toneTags.length > 0 ||
                      styleTags.length > 0 ||
                      (member.use_count ?? 0) > 0 ||
                      isFailed) && (
                      <div className="mt-2 flex flex-wrap items-center gap-1.5 pl-12">
                        {languages.map((lang) => (
                          <span
                            key={`lang-${lang}`}
                            className="rounded-full border border-border/60 bg-muted/60 px-2 py-0.5 text-[10px] font-medium tracking-wide text-foreground/85"
                          >
                            {lang}
                          </span>
                        ))}
                        {toneTags.map((tag) => (
                          <span
                            key={`tone-${tag}`}
                            className="rounded-full border border-border/60 bg-muted/45 px-2 py-0.5 text-[11px] text-muted-foreground"
                          >
                            {tag}
                          </span>
                        ))}
                        {styleTags.map((style) => (
                          <span
                            key={`style-${style}`}
                            className="rounded-full border border-border/50 bg-background/80 px-2 py-0.5 text-[11px] text-muted-foreground"
                          >
                            {style}
                          </span>
                        ))}
                        {typeof member.use_count === "number" &&
                        member.use_count > 0 ? (
                          <span className="rounded-full border border-border/60 bg-muted/50 px-2 py-0.5 text-[11px] tabular-nums text-muted-foreground">
                            {t("chat.candidates.usedCount", {
                              count: member.use_count,
                            })}
                          </span>
                        ) : null}
                        {isFailed ? (
                          <span className="text-[11px] text-muted-foreground">
                            {t("chat.sfx.previewUnavailable")}
                          </span>
                        ) : null}
                      </div>
                    )}
                  </motion.div>
                )
              })}
            </AnimatePresence>

            {overflow > 0 ? (
              <button
                type="button"
                onClick={() => setExpanded((value) => !value)}
                className="flex w-full items-center gap-1.5 rounded-xl px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <ChevronDown
                  className={cn(
                    "size-3.5 transition-transform",
                    expanded && "rotate-180",
                  )}
                />
                {expanded
                  ? t("chat.candidates.less")
                  : t("chat.candidates.more", { count: overflow })}
              </button>
            ) : null}
          </div>
        </div>
      </motion.div>
    </div>
  )
}
