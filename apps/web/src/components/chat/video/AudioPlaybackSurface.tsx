import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { apiGet } from "@/lib/api"
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
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setSrc(null)
    setFailed(false)
    void apiGet(
      `/api/v1/projects/${projectId}/audio/${item.snapshot_id}/playback`,
      { toast: false, signal: controller.signal },
    ).then(async (response) => {
      if (!response.ok) throw new Error("playback unavailable")
      const payload = await response.json() as { url?: string; digest?: string }
      if (!payload.url || payload.digest !== item.digest) throw new Error("stale audio")
      if (!controller.signal.aborted) setSrc(payload.url)
    }).catch(() => {
      if (!controller.signal.aborted) setFailed(true)
    })
    return () => controller.abort()
  }, [projectId, item.snapshot_id, item.digest])

  return (
    <div className="rounded-lg bg-card px-3 py-2.5">
      <div className="mb-1.5 flex min-w-0 items-baseline gap-2">
        <span className="shrink-0 text-xs text-muted-foreground">
          {t(item.role === "music" ? "chat.audio.music" : "chat.audio.narration")}
        </span>
        {item.title ? (
          <span className="min-w-0 truncate text-sm text-foreground" title={item.title}>
            {item.title}
          </span>
        ) : null}
      </div>
      {src ? (
        <WaveformPlayer
          src={src}
          durationSeconds={item.duration_seconds}
          waveformKey={`${item.snapshot_id}:${item.digest}`}
          measuredPeaks={item.peaks}
        />
      ) : (
        <p className="text-xs text-muted-foreground">
          {t(failed ? "chat.audio.unavailable" : "chat.audio.loading")}
        </p>
      )}
    </div>
  )
}

export function AudioPlaybackSurface({ block }: { block: AudioPlaybackBlock }) {
  return (
    <div className="flex w-full max-w-2xl flex-col gap-2">
      {block.items.map((item) => (
        <AudioPlaybackItem
          key={`${item.snapshot_id}:${item.digest}`}
          projectId={block.project_id}
          item={item}
        />
      ))}
    </div>
  )
}
