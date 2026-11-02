import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  AnimatePresence,
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
  useTransform,
} from "motion/react"
import { Pause, Play } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const PEAK_COUNT = 48
const PROGRESS_TRANSITION_SECONDS = 0.12

let activeAudio: HTMLAudioElement | null = null

function seedFromIdentity(identity: string): number {
  let hash = 2166136261
  for (let index = 0; index < identity.length; index += 1) {
    hash ^= identity.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

/** Stable voice-message bars: identity is the only seed, never Math.random,
 * mount time, playback time or remote PCM. The same candidate therefore keeps
 * the same silhouette across live, history and remounts. */
export function deterministicWaveform(identity: string, count = PEAK_COUNT): number[] {
  if (count <= 0) return []
  let state = seedFromIdentity(identity) || 0x9e3779b9
  const random = () => {
    state = (state + 0x6d2b79f5) >>> 0
    let value = state
    value = Math.imul(value ^ (value >>> 15), value | 1)
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61)
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296
  }
  const raw = Array.from({ length: count }, random)
  return raw.map((value, index) => {
    const previous = raw[Math.max(0, index - 1)]
    const next = raw[Math.min(count - 1, index + 1)]
    const smoothed = value * 0.5 + (previous + next) * 0.25
    return 0.18 + smoothed * 0.82
  })
}

function stamp(seconds: number): string {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0
  return `${Math.floor(safe / 60)}:${String(Math.floor(safe % 60)).padStart(2, "0")}`
}

/** Shared audio player. HTMLAudioElement exclusively owns transport and end
 * state; the MotionValue only eases the visual projection of real currentTime. */
export function WaveformPlayer({
  src,
  durationSeconds,
  waveformKey,
  className,
}: {
  src: string
  durationSeconds?: number | null
  /** Candidate identity for deterministic bars. Other audio uses src. */
  waveformKey?: string
  className?: string
}) {
  const { t } = useTranslation()
  const reduceMotion = useReducedMotion()
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(durationSeconds ?? 0)
  const [failed, setFailed] = useState(false)
  const progress = useMotionValue(0)
  const playedClip = useTransform(
    progress,
    (value) => `inset(0 ${Math.max(0, 100 - value * 100)}% 0 0)`,
  )
  const peaks = deterministicWaveform(waveformKey ?? src)
  const actualProgress = duration > 0 ? Math.min(Math.max(currentTime / duration, 0), 1) : 0

  useEffect(() => {
    const controls = animate(progress, actualProgress, {
      duration: reduceMotion ? 0 : PROGRESS_TRANSITION_SECONDS,
      ease: "linear",
    })
    return () => controls.stop()
  }, [actualProgress, progress, reduceMotion])

  useEffect(() => {
    const audio = new Audio()
    audio.preload = "metadata"
    audio.src = src
    audioRef.current = audio
    setPlaying(false)
    setCurrentTime(0)
    setDuration(durationSeconds ?? 0)
    setFailed(false)

    const onPlay = () => {
      if (activeAudio && activeAudio !== audio) activeAudio.pause()
      activeAudio = audio
      setPlaying(true)
    }
    const onPause = () => {
      if (activeAudio === audio) activeAudio = null
      setPlaying(false)
    }
    const onTime = () => setCurrentTime(audio.currentTime)
    const onMetadata = () => {
      if (Number.isFinite(audio.duration)) setDuration(audio.duration)
    }
    const onEnded = () => {
      if (activeAudio === audio) activeAudio = null
      setCurrentTime(Number.isFinite(audio.duration) ? audio.duration : durationSeconds ?? 0)
      setPlaying(false)
    }
    const onError = () => {
      if (activeAudio === audio) activeAudio = null
      setFailed(true)
      setPlaying(false)
    }
    audio.addEventListener("play", onPlay)
    audio.addEventListener("pause", onPause)
    audio.addEventListener("timeupdate", onTime)
    audio.addEventListener("loadedmetadata", onMetadata)
    audio.addEventListener("ended", onEnded)
    audio.addEventListener("error", onError)
    return () => {
      audio.pause()
      audio.removeEventListener("play", onPlay)
      audio.removeEventListener("pause", onPause)
      audio.removeEventListener("timeupdate", onTime)
      audio.removeEventListener("loadedmetadata", onMetadata)
      audio.removeEventListener("ended", onEnded)
      audio.removeEventListener("error", onError)
      if (audioRef.current === audio) audioRef.current = null
      if (activeAudio === audio) activeAudio = null
    }
  }, [src, durationSeconds])

  const toggle = () => {
    const audio = audioRef.current
    if (!audio || failed) return
    if (playing) {
      audio.pause()
      return
    }
    if (Number.isFinite(audio.duration) && audio.duration > 0 && audio.currentTime >= audio.duration) {
      audio.currentTime = 0
      setCurrentTime(0)
    }
    void audio.play().catch(() => {
      setFailed(true)
      setPlaying(false)
    })
  }

  const seek = (next: number) => {
    const audio = audioRef.current
    if (!audio || failed || !Number.isFinite(next)) return
    audio.currentTime = next
    setCurrentTime(next)
  }

  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <div className="flex min-w-0 items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="shrink-0 rounded-full"
          onClick={toggle}
          disabled={failed}
          aria-label={playing ? t("chat.sfx.pause") : t("chat.sfx.play")}
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={playing ? "pause" : "play"}
              initial={reduceMotion ? false : { opacity: 0, scale: 0.85 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={reduceMotion ? { opacity: 1 } : { opacity: 0, scale: 0.85 }}
              transition={{ duration: reduceMotion ? 0 : 0.1 }}
              className="flex items-center justify-center"
            >
              {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
            </motion.span>
          </AnimatePresence>
        </Button>
        <div className="relative h-8 min-w-0 flex-1 rounded-md focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-primary">
          <div className="absolute inset-0 flex items-center gap-0.5" aria-hidden="true">
            {peaks.map((peak, index) => (
              <span
                key={`base-${index}`}
                className="min-w-px flex-1 rounded-md bg-muted-foreground"
                style={{ height: `${Math.max(2, peak * 28)}px` }}
              />
            ))}
          </div>
          <motion.div
            className="absolute inset-0 flex items-center gap-0.5"
            style={{ clipPath: playedClip }}
            aria-hidden="true"
          >
            {peaks.map((peak, index) => (
              <span
                key={`played-${index}`}
                className="min-w-px flex-1 rounded-md bg-primary"
                style={{ height: `${Math.max(2, peak * 28)}px` }}
              />
            ))}
          </motion.div>
          <input
            type="range"
            min={0}
            max={Math.max(duration, 0.001)}
            step={0.01}
            value={Math.min(currentTime, duration || 0)}
            onChange={(event) => seek(Number(event.currentTarget.value))}
            disabled={!duration || failed}
            aria-label={t("chat.sfx.seek")}
            aria-valuetext={`${stamp(currentTime)} / ${stamp(duration)}`}
            className="absolute inset-0 z-10 size-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
          />
        </div>
        <span className="w-9 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
          {stamp(currentTime > 0 || playing ? currentTime : duration)}
        </span>
      </div>
      {failed ? (
        <span className="text-xs text-muted-foreground">
          {t("chat.sfx.previewUnavailable")}
        </span>
      ) : null}
    </div>
  )
}
