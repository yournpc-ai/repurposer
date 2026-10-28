/** StoryboardCard — the video family's canonical storyboard presentation
 * (Video Project phase B): a message block carries only the REFERENCE
 * (composition_id + composition_version_id); the card resolves the SAVED
 * version's DTO from the server and renders the table — the server is the
 * truth, the LLM never re-transcribes it, and a stale block simply shows
 * its honest empty state (读容忍).
 *
 * Chrome: an in-flow bg-muted block (the chat's register parity — no
 * shadow, no border in a scroller), rounded-lg, token colors only. */

import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import { createTypewriter } from "@/lib/typewriter"
import { cn } from "@/lib/utils"
import type { VideoStoryboardBlock } from "../historyReplay"

interface StoryboardClip {
  clip_id: string
  object_kind: string
  track_role: string
  text?: string | null
  view_id?: string | null
  view?: { heading?: string } | null
  animations?: { property: string; text_part?: string | null }[]
  gain_db?: number
  muted?: boolean
  fit?: "cover" | "contain"
  layout?: { x: number; y: number; width: number; height: number }
  source_range_seconds?: { start: number; end: number }
  range_seconds?: { start: number; end: number }
  shape?: "rect" | "ellipse" | "path"
  fill?: string | null
  runtime?: "drawing-v1" | "image-v1"
  prompt?: string | null
  provider?: string | null
  model?: string | null
  voice_id?: string
  language?: string
}

interface GeneratorPreview {
  clip_id: string
  object_id: string
  program_digest: string
  video_url: string
  poster_url: string
  media_digest: string
}

interface StoryboardScene {
  scene_id: string
  number: number
  range_seconds: { start: number; end: number }
  intent?: string | null
  visual_description?: string | null
  narration?: string | null
  clips: StoryboardClip[]
}

interface VideoVersionRead {
  composition_id: string
  composition_name?: string | null
  composition_version_id: string
  version: number
  generator_previews?: GeneratorPreview[]
  storyboard: {
    duration_seconds: number
    settings: { width: number; height: number; fps: number; background: string }
    scenes: StoryboardScene[]
    sources?: { kind?: string | null; url?: string | null }[]
    unassigned_clips?: StoryboardClip[]
  }
}

/** mm:ss.s–mm:ss.s — one decimal, the scene window's display form. */
function formatWindow(start: number, end: number): string {
  const stamp = (s: number) => {
    const whole = Math.floor(s)
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}.${Math.floor((s - whole) * 10)}`
  }
  return `${stamp(start)}–${stamp(end)}`
}

export function StoryboardCard({ block, messageId, onRunStarted }: { block: VideoStoryboardBlock; messageId: string; onRunStarted?: (id: string) => void }) {
  const { t } = useTranslation()
  const [read, setRead] = useState<VideoVersionRead | null>(null)
  const [failed, setFailed] = useState(false)
  const [visibleChars, setVisibleChars] = useState(0)
  const [completedVersion, setCompletedVersion] = useState<string | null>(null)
  const [readyPreviews, setReadyPreviews] = useState<string[]>([])
  const [failedPreviews, setFailedPreviews] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    setRead(null)
    setFailed(false)
    setReadyPreviews([])
    setFailedPreviews([])
    apiFetch(
      `/api/v1/chat/video/versions/${block.composition_version_id}/storyboard`,
      { toast: false },
    )
      .then(async (res) => {
        if (!res.ok) throw new Error("Storyboard unavailable")
        const data = (await res.json()) as VideoVersionRead
        if (data.composition_id !== block.composition_id || data.composition_version_id !== block.composition_version_id) {
          throw new Error("Storyboard identity mismatch")
        }
        if (!cancelled) setRead(data)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [block.composition_id, block.composition_version_id])

  const prose = read?.storyboard.scenes.map((scene) =>
    [
      scene.intent ?? "",
      scene.visual_description ?? "",
      scene.clips.find((clip) => clip.object_kind === "generator")?.prompt ?? "",
      ...scene.clips.filter((c) => c.object_kind === "text" && c.text).map((c) => c.text ?? ""),
      scene.narration ?? "",
    ].join(""),
  ).join("") ?? ""
  const previews = read?.generator_previews ?? []
  const previewsReady = previews.every((preview) => readyPreviews.includes(preview.clip_id))
  const narrationClips = read?.storyboard.scenes.flatMap((scene) =>
    scene.clips.filter((clip) => clip.object_kind === "speech"),
  ) ?? []
  const narrationVoices = [...new Set(narrationClips.map((clip) =>
    `${clip.voice_id ?? clip.model ?? "speech"} · ${clip.language ?? "auto"}`,
  ))].join(", ")

  useEffect(() => {
    if (!read) return
    let cancelled = false
    setVisibleChars(0)
    setCompletedVersion(null)
    const writer = createTypewriter((chunk) => { if (!cancelled) setVisibleChars((n) => n + chunk.length) })
    writer.push(prose)
    void writer.drain().then(() => {
      if (!cancelled) setCompletedVersion(read.composition_version_id)
    })
    return () => { cancelled = true; writer.flush() }
  }, [read, prose])

  useEffect(() => {
    if (!read || completedVersion !== read.composition_version_id || !previewsReady) return
    let cancelled = false
    void new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))).then(async () => {
      if (cancelled || !messageId || !block.presentation_digest) return
      const response = await apiFetch(`/api/v1/chat/messages/${block.presented_message_id || messageId}/video-presentation`, {
        method: "POST", toast: false,
        body: { composition_version_id: block.composition_version_id, presentation_digest: block.presentation_digest },
      }).catch(() => {})
      if (response?.ok) {
        const result = await response.json()
        if (result.run_id && !cancelled) onRunStarted?.(result.run_id)
      }
    })
    return () => { cancelled = true }
  }, [read, completedVersion, previewsReady, messageId, block.presented_message_id, block.composition_version_id, block.presentation_digest, onRunStarted])

  let remaining = visibleChars
  const reveal = (value?: string | null) => {
    const text = value ?? ""
    const shown = text.slice(0, Math.max(0, remaining))
    remaining -= text.length
    return shown
  }

  return (
    <div className="mt-1 w-fit max-w-[85%] rounded-lg bg-muted px-3 py-2.5 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-300">
      <div className="flex items-baseline gap-2">
        <span className="text-sm font-medium text-foreground">
          {read?.composition_name?.trim() ||
            t("chat.videoStoryboard.title")}
        </span>
        <span className="text-xs text-meta">
          {t("chat.videoStoryboard.version", { n: block.version })}
          {read
            ? ` · ${t("chat.videoStoryboard.duration", {
                s: Math.round(read.storyboard.duration_seconds),
              })}`
            : ""}
        </span>
      </div>
      {failed ? (
        <p className="mt-1.5 text-xs text-muted-foreground">
          {t("chat.videoStoryboard.unavailable")}
        </p>
      ) : read == null ? (
        <p className="mt-1.5 text-xs text-muted-foreground">
          {t("chat.videoStoryboard.loading")}
        </p>
      ) : (
        <div>
        <p className="mt-1 text-xs text-meta">
          {read.storyboard.settings.width} × {read.storyboard.settings.height} · {read.storyboard.settings.fps} fps · {read.storyboard.settings.background}
        </p>
        <p className="mt-1 text-xs text-meta">
          {narrationClips.length === 0
            ? t("chat.videoStoryboard.noNarration")
            : t("chat.videoStoryboard.narrationOn", { voices: narrationVoices })} · {t(
            (read.storyboard.unassigned_clips ?? []).some((c) => c.object_kind === "audio" && c.track_role === "music") || read.storyboard.scenes.some((s) => s.clips.some((c) => c.object_kind === "audio" && c.track_role === "music"))
              ? "chat.videoStoryboard.musicOn" : "chat.videoStoryboard.musicOff",
          )}
        </p>
        {previews.map((preview) => (
          <div key={preview.clip_id} className="mt-2 max-w-lg">
            <p className="mb-1 text-xs text-meta">{t("chat.videoStoryboard.programPreview")}</p>
            <video
              className="w-full rounded-md bg-muted"
              controls
              playsInline
              preload="metadata"
              src={preview.video_url}
              poster={preview.poster_url}
              onCanPlay={() => setReadyPreviews((current) => current.includes(preview.clip_id) ? current : [...current, preview.clip_id])}
              onError={() => setFailedPreviews((current) => current.includes(preview.clip_id) ? current : [...current, preview.clip_id])}
            />
            {failedPreviews.includes(preview.clip_id) ? (
              <p className="mt-1 text-xs text-muted-foreground">{t("chat.videoStoryboard.programPreviewError")}</p>
            ) : null}
          </div>
        ))}
        {(read.storyboard.sources ?? []).map((source, index) => (
          <p key={index} className="mt-1 break-all text-xs text-meta">{source.url || t("chat.videoStoryboard.savedSource")}</p>
        ))}
        {(read.storyboard.unassigned_clips ?? []).filter((c) => c.object_kind === "audio").map((clip) => (
          <p key={clip.clip_id} className="mt-1 text-xs text-meta">
            {t("chat.videoStoryboard.audio")} · {clip.gain_db ?? 0} dB · {clip.range_seconds ? formatWindow(clip.range_seconds.start, clip.range_seconds.end) : ""}
          </p>
        ))}
        <ol className="mt-2 flex flex-col gap-2">
          {read.storyboard.scenes.map((scene) => {
            const texts = scene.clips.filter((c) => c.object_kind === "text" && c.text)
            const web = scene.clips.find((c) => c.object_kind === "web")
            const video = scene.clips.find((c) => c.object_kind === "video" && c.fit === "contain") ?? scene.clips.find((c) => c.object_kind === "video")
            const generator = scene.clips.find((c) => c.object_kind === "generator")
            const shapes = scene.clips.filter((c) => c.object_kind === "shape")
            return (
              <li key={scene.scene_id} className="flex flex-col gap-0.5">
                <div className="flex items-baseline gap-2">
                  <span className="text-xs font-medium tabular-nums text-foreground">
                    {String(scene.number).padStart(2, "0")}
                  </span>
                  <span className="text-xs tabular-nums text-meta">
                    {formatWindow(
                      scene.range_seconds.start,
                      scene.range_seconds.end,
                    )}
                  </span>
                  {scene.intent ? (
                    <span className="text-xs text-muted-foreground">
                      {reveal(scene.intent)}
                    </span>
                  ) : null}
                </div>
                <p className="pl-6 text-xs text-muted-foreground">
                  {scene.visual_description ? reveal(scene.visual_description) : t(generator ? "chat.videoStoryboard.generatorScene" : web ? "chat.videoStoryboard.webScene" : video ? "chat.videoStoryboard.mixedScene" : "chat.videoStoryboard.textScene")}
                </p>
                {web?.view?.heading ? (
                  <p className="pl-6 text-xs text-muted-foreground">
                    {t("chat.videoStoryboard.view", {
                      heading: web.view.heading,
                    })}
                  </p>
                ) : null}
                {video ? (
                  <p className="pl-6 text-xs text-muted-foreground">
                    {video.source_range_seconds ? `${formatWindow(video.source_range_seconds.start, video.source_range_seconds.end)} · ` : ""}{video.fit} · {t(video.muted ? "chat.videoStoryboard.originalAudioOff" : "chat.videoStoryboard.originalAudioOn")} · {video.gain_db ?? 0} dB
                  </p>
                ) : null}
                {shapes.map((clip) => (
                  <p key={`shape-${clip.clip_id}`} className="pl-6 text-xs text-meta">
                    {t("chat.videoStoryboard.shape")} · {clip.shape} · {clip.fill}
                  </p>
                ))}
                {generator?.provider && generator.model ? (
                  <p className="pl-6 text-xs text-meta">{generator.provider} / {generator.model}</p>
                ) : null}
                {generator?.prompt ? (
                  <p className="pl-6 text-xs text-muted-foreground">{reveal(generator.prompt)}</p>
                ) : null}
                {texts.map((clip) => (
                  <p
                    key={clip.clip_id}
                    className={cn(
                      "pl-6 text-xs text-foreground",
                      clip.track_role === "caption" &&
                        "text-muted-foreground",
                    )}
                  >
                    {clip.range_seconds ? `${formatWindow(clip.range_seconds.start, clip.range_seconds.end)} · ` : ""}{reveal(clip.text)}
                  </p>
                ))}
                {scene.clips.filter((c) => c.animations?.length).map((clip) => (
                  <p key={`motion-${clip.clip_id}`} className="pl-6 text-xs text-meta">
                    {t("chat.videoStoryboard.motion")} · {clip.animations?.map((a) => t(`chat.videoStoryboard.motionProperty.${a.property.replaceAll(".", "_")}`, { defaultValue: t("chat.videoStoryboard.motion") })).join(" / ")}
                  </p>
                ))}
                {/* Exact reviewed spoken copy; voice facts come from the
                    saved SpeechObjects, never from a client-side default. */}
                {scene.narration == null ? null : (
                  <p className="pl-6 text-xs text-muted-foreground">
                    {reveal(scene.narration)}
                  </p>
                )}
              </li>
            )
          })}
        </ol>
        </div>
      )}
    </div>
  )
}
