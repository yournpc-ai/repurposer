import { useRef } from "react"
import { useTranslation } from "react-i18next"

import { apiGet } from "@/lib/api"
import { playSoundRecipePreview } from "@/lib/sound-preview"
import type { AudioPlaybackBlock } from "../timeline/types"
import { WaveformPlayer } from "./WaveformPlayer"

function AudioPlaybackItem({
  projectId,
  item,
}: {
  projectId: string
  item: AudioPlaybackBlock["items"][number]
}) {
  const { t } = useTranslation()
  const signed = useRef<{ url: string; expiresAt: number } | null>(null)
  const resolvePlaybackUrl = async (retry: boolean) => {
    if (!retry && signed.current && Date.now() < signed.current.expiresAt) {
      return signed.current.url
    }
    const requestedAt = Date.now()
    const response = await apiGet(
      `/api/v1/projects/${projectId}/audio/${item.snapshot_id}/playback`,
      { toast: false },
    )
    if (!response.ok) throw new Error("playback unavailable")
    const payload = await response.json()
    if (typeof payload.url !== "string" || !payload.url ||
        payload.snapshot_id !== item.snapshot_id || payload.digest !== item.digest) {
      throw new Error("stale audio")
    }
    signed.current = {
      url: payload.url,
      expiresAt: requestedAt + Math.max(0, Number(payload.expires_in) - 5) * 1000,
    }
    return payload.url
  }

  const hasMeasurements = Number.isFinite(item.duration_seconds) && item.duration_seconds > 0 &&
    Array.isArray(item.peaks) && item.peaks.length > 0 &&
    item.peaks.every((peak) => Number.isFinite(peak) && peak >= 0)
  const roleLabelKey =
    item.role === "music"
      ? "chat.audio.music"
      : item.role === "effect"
        ? "chat.audio.effect"
        : "chat.audio.narration"
  return (
    <div className="rounded-lg bg-card px-3 py-2.5">
      <div className="mb-1.5 flex min-w-0 items-baseline gap-2">
        <span className="shrink-0 text-xs text-muted-foreground">
          {t(roleLabelKey)}
        </span>
        {item.role === "narration" && (item.scene_label || item.scene_id) ? (
          <span className="shrink-0 text-xs text-muted-foreground">
            {item.scene_label || item.scene_id}
          </span>
        ) : null}
        {item.title ? (
          <span className="min-w-0 truncate text-sm text-foreground" title={item.title}>
            {item.title}
          </span>
        ) : null}
        {item.role === "effect" && item.sound_recipe?.recipe_id ? (
          <button
            type="button"
            onClick={() =>
              void playSoundRecipePreview({
                recipeId: item.sound_recipe!.recipe_id,
                params: item.sound_recipe!.params,
                tune: item.sound_recipe!.tune,
                seed: item.sound_recipe!.seed,
              })
            }
            className="ml-auto shrink-0 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            {t("chat.audio.audition")}
          </button>
        ) : null}
      </div>
      {hasMeasurements ? (
        <WaveformPlayer
          resolvePlaybackUrl={resolvePlaybackUrl}
          durationSeconds={item.duration_seconds}
          measuredPeaks={item.peaks}
        />
      ) : (
        <p className="text-xs text-muted-foreground">{t("chat.audio.unavailable")}</p>
      )}
    </div>
  )
}

export function AudioPlaybackSurface({ block }: { block: AudioPlaybackBlock }) {
  return (
    <div className="flex w-full max-w-2xl flex-col gap-2">
      {block.items.map((item) => (
        <AudioPlaybackItem
          key={JSON.stringify([block.project_id, item.role, item.scene_id, item.snapshot_id, item.digest])}
          projectId={block.project_id}
          item={item}
        />
      ))}
    </div>
  )
}
