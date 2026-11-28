import { useEffect, useState } from "react"
import { Maximize2, Play, Video } from "@/components/ui/icons"
import { useTranslation } from "react-i18next"

import { anchorCardOf, anchorLabel, isChatVideoOutput } from "@/lib/anchorCards"
import { toAbsoluteUrl } from "@/lib/api"
import { useOutputPoster } from "@/lib/outputPoster"
import { outputAspect } from "@/lib/outputAspect"
import { cn, formatDuration } from "@/lib/utils"
import type { Output } from "@/lib/types"

export function OutputPosterImage({
  output,
  className,
}: {
  output: Output
  className?: string
}) {
  const poster = useOutputPoster(output)
  if (poster) {
    return <img src={poster} alt="" className={cn("h-full w-full object-contain", className)} />
  }
  return (
    <span className={cn("flex h-full w-full items-center justify-center bg-muted text-muted-foreground", className)}>
      <Video className="h-6 w-6" />
    </span>
  )
}

/** Playable hero delivery card in chat, with one-click popout to the Workbench. */
export function OutputDeliveryCard({
  output,
  onOpen,
}: {
  output: Output
  onOpen: (outputId: string) => void
}) {
  const { t } = useTranslation()
  const poster = useOutputPoster(output)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    setPlaying(false)
  }, [output.id])

  if (!isChatVideoOutput(output)) return null
  const card = anchorCardOf(output)
  const typeWord = t(`chat.anchorCards.types.${output.type}`, { defaultValue: output.type })
  const label = anchorLabel(card, typeWord, null)
  const aspect = outputAspect(output)
  const portrait = aspect < 1
  const videoUrl = toAbsoluteUrl(card.videoUrl)

  return (
    <div className={cn(portrait ? "w-fit max-w-full" : "w-full max-w-[520px]")}>
      <div
        data-output-id={output.id}
        className={cn(
          "group relative overflow-hidden rounded-xl border border-subtle bg-muted shadow-xs",
          portrait ? "h-80 max-w-full" : "w-full",
        )}
        style={{ aspectRatio: aspect }}
      >
        {playing && videoUrl ? (
          <video
            src={videoUrl}
            poster={poster ?? undefined}
            controls
            autoPlay
            playsInline
            className="h-full w-full bg-black object-contain"
          />
        ) : (
          <button
            type="button"
            aria-label={t(videoUrl ? "chat.anchorCards.play" : "chat.anchorCards.view", { name: label })}
            onClick={() => {
              if (videoUrl) {
                setPlaying(true)
              } else {
                onOpen(output.id)
              }
            }}
            className="relative block h-full w-full text-left focus-visible:outline-2 focus-visible:outline-ring/30"
          >
            <OutputPosterImage output={output} className="object-cover" />
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/55 via-black/10 to-transparent"
            />
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 flex items-center justify-center"
            >
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-black/55 text-white shadow-md ring-1 ring-white/25 backdrop-blur-md transition-transform group-hover:scale-105 group-focus-visible:scale-105 motion-reduce:transition-none">
                <Play className="ml-0.5 h-5 w-5 fill-current" />
              </span>
            </span>
            <span className="pointer-events-none absolute right-3 bottom-2.5 left-3 flex items-center justify-between gap-2">
              <span className="truncate text-[13px] font-medium text-white drop-shadow-xs">
                {label}
              </span>
              {card.durationSec != null ? (
                <span className="shrink-0 rounded-md bg-black/60 px-1.5 py-0.5 font-mono text-[11px] leading-4 text-white backdrop-blur-sm">
                  {formatDuration(card.durationSec)}
                </span>
              ) : null}
            </span>
          </button>
        )}
        <button
          type="button"
          aria-label={t("chat.anchorCards.openInWorkbench", { name: label })}
          title={t("chat.anchorCards.openInWorkbench", { name: label })}
          onClick={() => onOpen(output.id)}
          className="absolute right-2.5 top-2.5 z-10 flex h-7 w-7 items-center justify-center rounded-md border border-subtle bg-background/85 text-foreground shadow-xs backdrop-blur-sm transition-colors hover:bg-background focus-visible:outline-2 focus-visible:outline-ring/30"
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}
